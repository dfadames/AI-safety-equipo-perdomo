"""
sesion_agente.py — Persona B

La versión agnóstica al proveedor de lo que antes era `SesionOllama`. Todo
lo que sabía específicamente de Ollama se movió a `proveedor_ollama.py`;
esta clase solo conoce los tipos neutros de `proveedores_llm.py`.

Para usar otro backend: escriban un `ProveedorLLM` nuevo (ver
`proveedor_ollama.py` y `proveedor_openai_compatible.py` como ejemplos) y
pásenlo acá. `SesionAgente` no cambia una línea.
"""

from __future__ import annotations

import json
from typing import Optional

from arnes_host import Canal, Registro, Ventana
from proveedores_llm import (
    HERRAMIENTAS,
    ProveedorLLM,
    Turno,
    TurnoAsistente,
    TurnoSistema,
    TurnoToolResult,
)


class SesionAgente:
    """
    Un agente, un contenedor, una Ventana de procedencia, un historial
    interno (`Turno*`, neutro) que se compacta EN EL MISMO MOMENTO y con
    los MISMOS event_id que la Ventana usa para compactar — sin importar
    a qué proveedor esté hablando.
    """

    def __init__(
        self,
        proveedor: ProveedorLLM,
        registro: Registro,
        canal: Canal,
        agent_id: str,
        contenedor: str,
        prompt_sistema: str,
        cap: int = 50,
        runner=None,
    ):
        self.proveedor = proveedor
        self.agent_id = agent_id
        self.canal = canal
        self.historial: list[Turno] = [TurnoSistema(prompt_sistema)]

        self.ventana = Ventana(
            registro, agent_id, contenedor, cap=cap, runner=runner,
            resumen_fn=self._resumir_y_podar,
        )
        # leer_canal se despacha aparte en `paso()` porque puede generar
        # 0..N eventos, no exactamente uno como las demás.
        self._despachadores = {
            "ejecutar": lambda comando: self.ventana.ejecutar(contenedor, comando),
            "escribir_canal": lambda mensaje: self.ventana.escribir_canal(self.canal, mensaje),
            "validar_credencial": lambda valor: self.ventana.validar_credencial(valor),
            "notificar_humano": lambda motivo: self.ventana.notificar_humano(motivo),
        }

    # -- compactación, sincronizada con Ventana --

    def _resumir_y_podar(self, viejos_evt_ids: list[str]) -> str:
        """Lo llama Ventana al compactar (ver arnes_host.py). Devuelve el
        texto que queda como `content` del evento `summarize`, y de paso
        poda del historial interno los turnos que ese resumen reemplaza —
        para que `cap` y lo que el modelo realmente ve sean lo mismo, sin
        importar el proveedor."""
        viejos = set(viejos_evt_ids)
        fragmentos = [self._texto_de(t) for t in self.historial if t.evt_id in viejos]
        resumen = "Resumen de pasos anteriores: " + " · ".join(f for f in fragmentos if f)

        self.historial = [t for t in self.historial if t.evt_id not in viejos]
        self.historial.insert(1, TurnoSistema(resumen))  # justo después del prompt de sistema
        return resumen

    @staticmethod
    def _texto_de(turno: Turno) -> str:
        if isinstance(turno, TurnoToolResult):
            return turno.contenido
        if isinstance(turno, TurnoSistema):
            return turno.texto
        if isinstance(turno, TurnoAsistente):
            return turno.texto or ""
        return ""

    @staticmethod
    def _texto_resultado(nombre: str, args: dict, resultado) -> str:
        """El texto que queda en el historial (y que puede terminar
        resumido) tiene que llevar la INFORMACIÓN, no la confirmación
        genérica de la herramienta."""
        if nombre == "escribir_canal":
            return f"Envié al canal: {args.get('mensaje', '')}"
        if nombre == "validar_credencial":
            return f"Intenté validar '{args.get('valor', '')}' → {resultado}"
        if nombre == "notificar_humano":
            return f"Notifiqué al humano: {args.get('motivo', '')}"
        # `ejecutar` ya devuelve la salida real del comando -- ahí el
        # resultado ES la información.
        return resultado if isinstance(resultado, str) else json.dumps(resultado, ensure_ascii=False)

    # -- el turno --

    def paso(self) -> bool:
        """Un turno. Devuelve False cuando el modelo no pide ninguna
        tool — se toma como el fin del episodio para este agente."""
        respuesta = self.proveedor.llamar(self.historial, HERRAMIENTAS)
        self.historial.append(TurnoAsistente(respuesta.texto, list(respuesta.tool_calls)))

        if not respuesta.tool_calls:
            return False

        for llamada in respuesta.tool_calls:
            nombre = llamada.nombre
            args = dict(llamada.argumentos or {})

            if nombre == "leer_canal":
                recibidos, ids_recibidos = self.ventana.leer_canal(self.canal)
                texto = "\n".join(recibidos) if recibidos else "sin mensajes nuevos"
                self.historial.append(TurnoToolResult("leer_canal", texto))
                # cada mensaje recibido es su PROPIO turno, ligado a su
                # propio evento -- igual que cada uno es su propio nodo
                # `receive` en el grafo.
                for texto_msg, evt_id in zip(recibidos, ids_recibidos):
                    self.historial.append(TurnoSistema(f"[recibido] {texto_msg}", evt_id=evt_id))
                continue

            despachador = self._despachadores.get(nombre)
            if despachador is None:
                self.historial.append(TurnoToolResult(nombre, f"herramienta desconocida: {nombre}"))
                continue

            resultado, evt_id = despachador(**args)
            texto = self._texto_resultado(nombre, args, resultado)
            self.historial.append(TurnoToolResult(nombre, texto, evt_id=evt_id))

        return True

    def correr(self, max_pasos: int = 10) -> None:
        for _ in range(max_pasos):
            if not self.paso():
                break