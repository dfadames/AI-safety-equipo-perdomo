"""
proveedor_openai_compatible.py — Persona B

Un segundo `ProveedorLLM`, a propósito, para que "agnóstico al modelo" no
se quede en una promesa de un solo backend. Sirve para OpenAI real y para
cualquier servidor que hable el mismo protocolo de function calling
(vLLM, LM Studio, text-generation-webui, llama.cpp server con su flag de
API OpenAI, etc.) — solo cambia `base_url`.

No se probó contra un servidor en vivo en este entorno (no hay salida de
red a esos endpoints desde acá). El contrato de la API de tool calling
estilo OpenAI es estable y este archivo lo sigue tal cual, pero córranlo
una vez contra el suyo antes de confiar en él para una corrida real.

Requiere:
    pip install requests
"""

from __future__ import annotations

import json

import requests

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


class ProveedorOpenAICompatible(ProveedorLLM):
    def __init__(self, modelo: str, base_url: str = "https://api.openai.com/v1", api_key: str = ""):
        self.modelo = modelo
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _formatear_tools(self, herramientas: list[ToolSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {"name": h.nombre, "description": h.descripcion, "parameters": h.parametros},
            }
            for h in herramientas
        ]

    def _formatear_historial(self, historial: list[Turno]) -> list[dict]:
        """El protocolo OpenAI exige que cada tool_call tenga un `id`, y
        que el mensaje `tool` que responde a esa llamada repita el mismo
        `tool_call_id`. Nuestro historial interno no guarda esos ids (son
        un detalle del proveedor, no de la trazabilidad), así que se
        generan acá mismo, en orden: una cola FIFO por cada tool_call que
        declara un turno de asistente, consumida por los TurnoToolResult
        que le siguen -- que es exactamente el orden en que SesionAgente
        los produce."""
        mensajes: list[dict] = []
        cola_ids: list[str] = []
        contador = 0

        for t in historial:
            if isinstance(t, TurnoSistema):
                mensajes.append({"role": "system", "content": t.texto})

            elif isinstance(t, TurnoAsistente):
                msg: dict = {"role": "assistant", "content": t.texto}
                if t.tool_calls:
                    ids = [f"call_{contador + i}" for i in range(len(t.tool_calls))]
                    contador += len(t.tool_calls)
                    cola_ids.extend(ids)
                    msg["tool_calls"] = [
                        {
                            "id": tc_id,
                            "type": "function",
                            "function": {"name": tc.nombre, "arguments": json.dumps(tc.argumentos)},
                        }
                        for tc_id, tc in zip(ids, t.tool_calls)
                    ]
                mensajes.append(msg)

            elif isinstance(t, TurnoToolResult):
                tc_id = cola_ids.pop(0) if cola_ids else f"call_{contador}"
                mensajes.append({"role": "tool", "tool_call_id": tc_id, "content": t.contenido})

        return mensajes

    def llamar(self, historial: list[Turno], herramientas: list[ToolSpec]) -> RespuestaLLM:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        cuerpo = {
            "model": self.modelo,
            "messages": self._formatear_historial(historial),
            "tools": self._formatear_tools(herramientas),
        }
        r = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=cuerpo, timeout=60)
        r.raise_for_status()
        mensaje = r.json()["choices"][0]["message"]
        tool_calls = [
            LlamadaTool(tc["function"]["name"], json.loads(tc["function"]["arguments"]))
            for tc in (mensaje.get("tool_calls") or [])
        ]
        return RespuestaLLM(texto=mensaje.get("content"), tool_calls=tool_calls)