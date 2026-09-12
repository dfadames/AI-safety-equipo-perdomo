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
from typing import Optional

from .canal import Canal
from .config import Config
from .prompts import prompt_sistema
from .proveedores.base import (
    HERRAMIENTAS, ProveedorLLM, Turno, TurnoAsistente, TurnoSistema, TurnoToolResult,
)
from .registro import Registro
from .ventana import Ventana


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
                textos.append(f"{t.nombre_tool}: {t.contenido[:120]}")
            elif isinstance(t, TurnoAsistente) and t.texto:
                textos.append(t.texto[:120])
        resumen = "Resumen de lo anterior: " + " | ".join(textos) if textos else \
                  f"Resumen de {n} pasos anteriores."
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

        if not r.tool_calls:
            self.historial.append(TurnoAsistente(texto=r.texto))
            self.terminado = True
            return False

        self.historial.append(TurnoAsistente(texto=r.texto, tool_calls=r.tool_calls,
                                             reasoning_content=r.reasoning_content))
        for tc in r.tool_calls:
            resultado = self._despachar(tc.nombre, tc.argumentos)
            self.historial.append(TurnoToolResult(tc.nombre, resultado))
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
