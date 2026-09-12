"""
El unico archivo que sabe que existe Ollama.

    pip install ollama
    ollama pull qwen2.5
"""

from __future__ import annotations

import json
from typing import Optional

from .base import (
    LlamadaTool, ProveedorLLM, RespuestaLLM, ToolSpec,
    Turno, TurnoAsistente, TurnoSistema, TurnoToolResult,
)


class ProveedorOllama(ProveedorLLM):
    def __init__(self, modelo: str = "qwen2.5", host: Optional[str] = None,
                 seed: Optional[int] = None, temperature: Optional[float] = None):
        from ollama import Client, chat as chat_default
        self.modelo = modelo
        self._chat = Client(host=host).chat if host else chat_default
        # Semilla fija: la replica contrafactual necesita repetir el mismo
        # episodio. Van en `options`, que es como Ollama recibe estos parametros.
        self.opciones: dict = {}
        if seed is not None:
            self.opciones["seed"] = seed
        if temperature is not None:
            self.opciones["temperature"] = temperature

    def _tools(self, herramientas: list[ToolSpec]) -> list[dict]:
        return [{"type": "function",
                 "function": {"name": h.nombre, "description": h.descripcion,
                              "parameters": h.parametros}}
                for h in herramientas]

    def _mensajes(self, historial: list[Turno]) -> list[dict]:
        out: list[dict] = []
        for t in historial:
            if isinstance(t, TurnoSistema):
                out.append({"role": "system", "content": t.texto})
            elif isinstance(t, TurnoAsistente):
                m: dict = {"role": "assistant", "content": t.texto or ""}
                if t.tool_calls:
                    m["tool_calls"] = [
                        {"function": {"name": tc.nombre, "arguments": tc.argumentos}}
                        for tc in t.tool_calls]
                out.append(m)
            elif isinstance(t, TurnoToolResult):
                out.append({"role": "tool", "tool_name": t.nombre_tool, "content": t.contenido})
        return out

    def llamar(self, historial: list[Turno], herramientas: list[ToolSpec]) -> RespuestaLLM:
        # Sin herramientas (el juez del monitor por agente no las usa) no se
        # manda `tools` del todo: una lista vacia confunde a algunos backends.
        extra = {}
        tools = self._tools(herramientas)
        if tools:
            extra["tools"] = tools
        r = self._chat(model=self.modelo,
                       messages=self._mensajes(historial),
                       options=self.opciones or None,
                       **extra)
        msg = r.get("message", {}) if isinstance(r, dict) else getattr(r, "message", {})
        texto = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)

        crudas = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
        llamadas = []
        for tc in crudas or []:
            fn = tc.get("function", {}) if isinstance(tc, dict) else getattr(tc, "function", {})
            nombre = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", "")
            args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            llamadas.append(LlamadaTool(nombre, args or {}))

        # La libreria moderna devuelve un objeto `ChatResponse`, no un dict:
        # `isinstance(r, dict)` daba False siempre y el contador quedaba en 0.
        if isinstance(r, dict):
            tokens = (r.get("prompt_eval_count") or 0) + (r.get("eval_count") or 0)
        else:
            tokens = ((getattr(r, "prompt_eval_count", 0) or 0)
                     + (getattr(r, "eval_count", 0) or 0))
        return RespuestaLLM(texto=texto, tool_calls=llamadas, tokens=tokens)
