"""
proveedor_ollama.py — Persona B

El único archivo de todo el proyecto que sabe que existe Ollama. Si mañana
cambian de modelo o de backend, este es el archivo que se reemplaza — ni
`sesion_agente.py` ni `arnes_host.py` se enteran.

Requiere:
    pip install ollama
    ollama pull qwen2.5      # o el tamaño que aguante su máquina
"""

from __future__ import annotations

from typing import Optional

from ollama import Client, chat as _chat_default

from proveedores_llm import (
    LlamadaTool,
    ProveedorLLM,
    RespuestaLLM,
    ToolSpec,
    Turno,
    TurnoAsistente,
    TurnoSistema,
    TurnoToolResult,
)


class ProveedorOllama(ProveedorLLM):
    def __init__(self, modelo: str = "qwen2.5", host: Optional[str] = None):
        self.modelo = modelo
        # sin `host`, usa la función `chat()` de conveniencia (localhost
        # por default); con `host`, un Client apuntando a otra máquina —
        # útil si Ollama corre en otro equipo del equipo.
        self._chat = Client(host=host).chat if host else _chat_default

    def _formatear_tools(self, herramientas: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": h.nombre,
                    "description": h.descripcion,
                    "parameters": h.parametros,
                },
            }
            for h in herramientas
        ]

    def _formatear_historial(self, historial: list[Turno]) -> list[dict]:
        mensajes: list[dict] = []
        for t in historial:
            if isinstance(t, TurnoSistema):
                mensajes.append({"role": "system", "content": t.texto})
            elif isinstance(t, TurnoAsistente):
                msg: dict = {"role": "assistant", "content": t.texto or ""}
                if t.tool_calls:
                    msg["tool_calls"] = [
                        {"function": {"name": tc.nombre, "arguments": tc.argumentos}}
                        for tc in t.tool_calls
                    ]
                mensajes.append(msg)
            elif isinstance(t, TurnoToolResult):
                mensajes.append({"role": "tool", "tool_name": t.nombre_tool, "content": t.contenido})
        return mensajes

    def llamar(self, historial: list[Turno], herramientas: list[ToolSpec]) -> RespuestaLLM:
        respuesta = self._chat(
            model=self.modelo,
            messages=self._formatear_historial(historial),
            tools=self._formatear_tools(herramientas),
        )
        tool_calls = [
            LlamadaTool(tc.function.name, dict(tc.function.arguments or {}))
            for tc in (respuesta.message.tool_calls or [])
        ]
        return RespuestaLLM(texto=respuesta.message.content, tool_calls=tool_calls)