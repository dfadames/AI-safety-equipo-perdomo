"""
Un agente: su ventana de procedencia, su historial y su bucle.

El historial que se le manda al modelo y la ventana de procedencia se podan
EN EL MISMO MOMENTO y con los MISMOS event_id. Si el modelo ve menos de lo que
dice `ancestors`, estamos inflando el grafo; si ve más, lo estamos desinflando.
Tiene que ser el mismo número en los dos lugares — por eso `cap` sale de la
config y no se pasa suelto.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .canal import Canal
from .config import Config
from .prompts import INSISTENCIA, prompt_sistema
from .proveedores.base import (
    HERRAMIENTAS, ProveedorLLM, Turno, TurnoAsistente, TurnoSistema, TurnoToolResult,
    TurnoUsuario,
)
from .registro import Registro
from .ventana import Ventana

# Cuantas veces seguidas se empuja a un agente de `imposible` que no avanza
# (se rinde, o solo duerme / relee el canal vacio) antes de dejarlo terminar.
# Sin este tope, un agente estancado quemaba los 30 turnos en `sleep` y cada
# turno es una llamada al modelo: casi todo el costo del episodio se iba en
# nada. Se lo insiste unas pocas veces y, si sigue sin producir, se detiene.
MAX_SIN_AVANCE = 3

# El resumen de contexto se mantiene PLANO y acotado. Antes cada compactacion
# reincrustaba el resumen anterior ("summarize: Resumen de: summarize: ...")
# y el texto crecia sin fin: el episodio N=2 gasto 287k tokens, casi todo en
# ese relleno anidado que se reenvia en cada llamada.
PREFIJO_RESUMEN = "Resumen de lo anterior: "
MAX_RESUMEN = 800


class SesionAgente:
    def __init__(self, proveedor: ProveedorLLM, registro: Registro, canal: Canal,
                 cfg: Config, agent_id: str, runner=None):
        self.proveedor = proveedor
        self.registro = registro
        self.canal = canal
        self.cfg = cfg
        self.agent_id = agent_id
        self.historial: list[Turno] = [TurnoSistema(prompt_sistema(cfg, agent_id))]
        self.ventana = Ventana(registro, cfg, agent_id, runner=runner,
                               resumen_fn=self._resumir_y_podar)
        self.terminado = False
        self.turnos = 0   # turnos del modelo: es lo que cuesta tokens
        self._sin_avance = 0   # turnos seguidos sin producir nada (solo `imposible`)

    # -- compactación sincronizada -----------------------------------------

    def _resumir_y_podar(self, viejos_evt_ids: list[str]) -> str:
        """Lo llama Ventana al compactar. Poda el historial del modelo en el
        mismo acto, para que las dos memorias coincidan."""
        n = len(viejos_evt_ids)
        sistema, resto = self.historial[0], self.historial[1:]
        a_comprimir, quedan = resto[:n], resto[n:]
        textos = []
        for t in a_comprimir:
            if isinstance(t, TurnoToolResult):
                # Un resumen previo entra PLANO, sin el prefijo ni la etiqueta
                # `summarize:`: reincrustarlos era lo que encadenaba el texto.
                if t.nombre_tool == "summarize":
                    c = t.contenido
                    textos.append(c[len(PREFIJO_RESUMEN):] if c.startswith(PREFIJO_RESUMEN) else c)
                else:
                    textos.append(f"{t.nombre_tool}: {t.contenido[:120]}")
            elif isinstance(t, TurnoAsistente) and t.texto:
                textos.append(t.texto[:120])
        resumen = PREFIJO_RESUMEN + " | ".join(textos) if textos else \
                  f"Resumen de {n} pasos anteriores."
        if len(resumen) > MAX_RESUMEN:
            resumen = resumen[:MAX_RESUMEN] + " […]"
        self.historial = [sistema, TurnoToolResult("summarize", resumen)] + quedan
        return resumen

    # -- un paso ------------------------------------------------------------

    def _registrar_razonamiento(self, texto: Optional[str]) -> None:
        """El esquema congelado pide `razonamiento` además de las acciones, y
        el monitor por agente tiene que leerlo: si juzgara solo acciones
        estaríamos debilitando la línea base a propósito, que es la primera
        objeción que haría un jurado.

        Va al registro pero NO a la ventana: meterlo ahí correría el tope de
        `cap_ventana` y desincronizaría las dos memorias, que es justo lo que
        `_resumir_y_podar` existe para evitar. Queda como hoja del grafo —
        con ancestros, sin descendientes— así que no altera la procedencia
        medida (ver TIPOS_NO_RAIZ en grafo/modelo.py)."""
        if not (texto and texto.strip()):
            return
        self.registro.escribir(
            agent_id=self.agent_id, source_container=self.ventana.contenedor,
            type_="razonamiento", content=texto, ancestors=self.ventana.snapshot(),
        )

    def paso(self) -> bool:
        """Devuelve False cuando el episodio de este agente terminó."""
        if self.terminado:
            return False
        if self.turnos >= self.cfg.max_pasos:
            return False            # tope duro, en código y sobre TURNOS

        self.turnos += 1
        r = self.proveedor.llamar(self.historial, HERRAMIENTAS)
        self.registro.sumar_tokens(r.tokens)
        self._registrar_razonamiento(r.texto)

        # Un turno que NO se rinde y NO es solo `sleep`/canal vacio cuenta como
        # avance. En las demas condiciones no se mide esto: rendirse termina el
        # episodio (como antes) y un turno ocioso simplemente gasta su turno.
        if not r.tool_calls:
            self.historial.append(TurnoAsistente(texto=r.texto,
                                                 reasoning_content=r.reasoning_content))
            if self.cfg.es_imposible:
                return self._sin_progreso()
            self.terminado = True
            return False

        self.historial.append(TurnoAsistente(texto=r.texto, tool_calls=r.tool_calls,
                                             reasoning_content=r.reasoning_content))
        avance = False
        for tc in r.tool_calls:
            resultado = self._despachar(tc.nombre, tc.argumentos)
            self.historial.append(TurnoToolResult(tc.nombre, resultado))
            if self._es_avance(tc.nombre, tc.argumentos, resultado):
                avance = True

        if self.cfg.es_imposible and not avance:
            return self._sin_progreso()
        self._sin_avance = 0
        return True

    @staticmethod
    def _es_avance(nombre: str, args: dict, resultado: str) -> bool:
        """Un `sleep` no hace nada (los agentes actuan por turnos, esperar no
        adelanta a nadie) y releer el canal vacio tampoco: no cuentan como
        avance. Lo demas si."""
        if nombre == "ejecutar":
            return re.match(r"\s*sleep\b", args.get("comando", "")) is None
        if nombre == "leer_canal":
            return bool(resultado) and resultado != "Sin mensajes nuevos."
        return True   # escribir_canal, validar_credencial, notificar_humano

    def _sin_progreso(self) -> bool:
        """Solo `imposible`: el agente se rindio o no hizo nada util este turno.
        Se lo empuja a seguir (INSISTENCIA, que queda en el log como hoja suelta
        del grafo, igual que `razonamiento`, sin alterar la procedencia). Tras
        MAX_SIN_AVANCE empujones sin producir, se lo deja terminar en vez de
        quemar el resto del presupuesto."""
        self._sin_avance += 1
        if self._sin_avance > MAX_SIN_AVANCE or self.turnos >= self.cfg.max_pasos:
            self.terminado = True
            return False
        self.registro.escribir(
            agent_id=self.agent_id, source_container=self.ventana.contenedor,
            type_="insistencia", content=INSISTENCIA, ancestors=[],
        )
        self.historial.append(TurnoUsuario(INSISTENCIA))
        return True

    def _despachar(self, nombre: str, args: dict) -> str:
        v = self.ventana
        try:
            if nombre == "ejecutar":
                salida, _ = v.ejecutar(args.get("comando", ""))
                return salida or "(sin salida)"
            if nombre == "escribir_canal":
                res, _ = v.escribir_canal(self.canal, args.get("mensaje", ""),
                                          para=args.get("para"))
                return res
            if nombre == "leer_canal":
                recibidos, _ = v.leer_canal(self.canal)
                return "\n".join(recibidos) if recibidos else "Sin mensajes nuevos."
            if nombre == "validar_credencial":
                res, _ = v.validar_credencial(args.get("valor", ""),
                                              cited_by_agent=args.get("cited_by_agent"))
                return res
            if nombre == "notificar_humano":
                res, _ = v.notificar_humano(args.get("motivo", ""))
                return res
        except Exception as e:                      # nunca tragar en silencio
            raise RuntimeError(f"herramienta {nombre} falló: {e}") from e
        return f"Herramienta desconocida: {nombre}"
