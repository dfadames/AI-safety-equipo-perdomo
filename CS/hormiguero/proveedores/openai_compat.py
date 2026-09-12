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
from ..entorno import cargar_env


class ProveedorOpenAICompatible(ProveedorLLM):
    def __init__(self, modelo: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, seed: Optional[int] = None,
                 temperature: Optional[float] = None):
        cargar_env()
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
        # Semilla fija: la replica contrafactual necesita repetir el mismo
        # episodio. No todos los backends compatibles la respetan, pero
        # cuando la respetan esto es lo que hace la corrida reproducible.
        self.seed = seed
        self.temperature = temperature

    def _tools(self, herramientas: list[ToolSpec]) -> list[dict]:
        return [{"type": "function",
                 "function": {"name": h.nombre, "description": h.descripcion,
                              "parameters": h.parametros}}
                for h in herramientas]

    def _mensajes(self, historial: list[Turno]) -> list[dict]:
        """La API exige que cada `role: tool` responda a un `tool_call` del
        assistant inmediatamente anterior, con su id. Dos cosas rompen eso:

        1. La compactación de contexto poda un prefijo del historial, así que
           un resultado puede quedar huérfano (su turno de assistant ya no
           está), y el propio resumen entra como TurnoToolResult sin llamada.
        2. Un turno con varias tool_calls en paralelo necesita un id distinto
           por resultado; indexar por NOMBRE de herramienta los pisaba.

        Por eso los ids pendientes se llevan en una cola y lo que no calza se
        manda como `user`, que la API sí acepta en cualquier posición y no
        pierde el contenido. Sin esto el episodio muere con un 400 en cuanto
        se compacta — con N=8 eso pasa siempre."""
        out: list[dict] = []
        pendientes: list[str] = []
        for i, t in enumerate(historial):
            if isinstance(t, TurnoSistema):
                out.append({"role": "system", "content": t.texto})
            elif isinstance(t, TurnoAsistente):
                m: dict = {"role": "assistant", "content": t.texto}
                pendientes = []
                if t.tool_calls:
                    m["tool_calls"] = []
                    for j, tc in enumerate(t.tool_calls):
                        cid = f"call_{i}_{j}"
                        pendientes.append(cid)
                        m["tool_calls"].append({
                            "id": cid, "type": "function",
                            "function": {"name": tc.nombre,
                                         "arguments": json.dumps(tc.argumentos, ensure_ascii=False)}})
                out.append(m)
            elif isinstance(t, TurnoToolResult):
                if pendientes:
                    out.append({"role": "tool", "tool_call_id": pendientes.pop(0),
                                "content": t.contenido})
                else:
                    out.append({"role": "user",
                                "content": f"[{t.nombre_tool}] {t.contenido}"})
        return out

    def llamar(self, historial: list[Turno], herramientas: list[ToolSpec]) -> RespuestaLLM:
        extra = {}
        if self.seed is not None:
            extra["seed"] = self.seed
        if self.temperature is not None:
            extra["temperature"] = self.temperature
        # Sin herramientas (el juez del monitor por agente no las usa) no se
        # manda `tools`: la API rechaza un array vacio.
        tools = self._tools(herramientas)
        if tools:
            extra["tools"] = tools
        r = self._cliente.chat.completions.create(
            model=self.modelo,
            messages=self._mensajes(historial),
            **extra,
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
