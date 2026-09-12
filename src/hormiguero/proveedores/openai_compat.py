"""
Cualquier backend con API compatible con OpenAI (OpenAI, vLLM, LM Studio,
Groq, Together...). La llave sale de .env vía entorno.py — nunca del codigo.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .base import (
    LlamadaTool, ProveedorLLM, RespuestaLLM, ToolSpec,
    Turno, TurnoAsistente, TurnoSistema, TurnoToolResult,
)


class ProveedorOpenAICompatible(ProveedorLLM):
    def __init__(self, modelo: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None):
        from openai import OpenAI
        self.modelo = modelo or os.environ.get("HORMIGUERO_MODELO", "gpt-4o-mini")
        clave = api_key or os.environ.get("OPENAI_API_KEY")
        if not clave:
            raise RuntimeError(
                "Falta OPENAI_API_KEY.\n"
                "  1. cp .env.example .env\n"
                "  2. abre .env y pon el valor\n"
                ".env esta en .gitignore, no se sube.")
        self._cliente = OpenAI(api_key=clave, base_url=base_url)

    def _tools(self, herramientas: list[ToolSpec]) -> list[dict]:
        return [{"type": "function",
                 "function": {"name": h.nombre, "description": h.descripcion,
                              "parameters": h.parametros}}
                for h in herramientas]

    def _mensajes(self, historial: list[Turno]) -> list[dict]:
        out: list[dict] = []
        ultimo_id = {}
        for i, t in enumerate(historial):
            if isinstance(t, TurnoSistema):
                out.append({"role": "system", "content": t.texto})
            elif isinstance(t, TurnoAsistente):
                m: dict = {"role": "assistant", "content": t.texto}
                if t.tool_calls:
                    m["tool_calls"] = []
                    for j, tc in enumerate(t.tool_calls):
                        cid = f"call_{i}_{j}"
                        ultimo_id[tc.nombre] = cid
                        m["tool_calls"].append({
                            "id": cid, "type": "function",
                            "function": {"name": tc.nombre,
                                         "arguments": json.dumps(tc.argumentos, ensure_ascii=False)}})
                out.append(m)
            elif isinstance(t, TurnoToolResult):
                out.append({"role": "tool",
                            "tool_call_id": ultimo_id.get(t.nombre_tool, "call_0_0"),
                            "content": t.contenido})
        return out

    def llamar(self, historial: list[Turno], herramientas: list[ToolSpec]) -> RespuestaLLM:
        r = self._cliente.chat.completions.create(
            model=self.modelo,
            messages=self._mensajes(historial),
            tools=self._tools(herramientas),
        )
        msg = r.choices[0].message
        llamadas = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            llamadas.append(LlamadaTool(tc.function.name, args))
        tokens = getattr(r, "usage", None)
        return RespuestaLLM(texto=msg.content, tool_calls=llamadas,
                            tokens=(tokens.total_tokens if tokens else 0))
