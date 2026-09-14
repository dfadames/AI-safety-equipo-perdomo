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
    Turno, TurnoAsistente, TurnoSistema, TurnoToolResult, TurnoUsuario,
)
from ..entorno import cargar_env


class ProveedorOpenAICompatible(ProveedorLLM):
    # Todo lo que cambia entre un backend y otro vive en estos atributos: un
    # proveedor nuevo es una subclase que redefine unas lineas y nada mas.
    # Ver `deepseek.py`.
    NOMBRE = "openai"
    VARIABLE_LLAVE = "OPENAI_API_KEY"
    VARIABLES_MODELO = ("OPENAI_MODELO", "HORMIGUERO_MODELO")
    MODELO_POR_DEFECTO = "gpt-4o-mini"
    BASE_URL = None
    SOPORTA_SEED = True             # `seed` no es universal; ver ProveedorDeepSeek
    TEMPERATURA_POR_DEFECTO = None
    # Un barrido son cientos de llamadas seguidas: un 429 suelto no puede
    # matar la corrida entera.
    MAX_REINTENTOS = 4
    TIMEOUT = 120.0

    def __init__(self, modelo: Optional[str] = None, base_url: Optional[str] = None,
                 api_key: Optional[str] = None, seed: Optional[int] = None,
                 temperature: Optional[float] = None):
        cargar_env()
        self.modelo = modelo or self._modelo_de_entorno()
        # La llave se revisa ANTES de importar la SDK: falta mucho mas seguido
        # que el paquete, y asi el error dice lo que de verdad pasa.
        clave = api_key or os.environ.get(self.VARIABLE_LLAVE)
        if not clave:
            raise RuntimeError(
                f"Falta {self.VARIABLE_LLAVE}.\n"
                f"  1. cp .env.example .env     (en la raiz del repo)\n"
                f"  2. abre .env y pon {self.VARIABLE_LLAVE}\n"
                f".env esta en .gitignore y el hook lo bloquea: no se sube.")
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "Falta el paquete `openai`.\n"
                "  pip install -r requirements.txt") from None
        self._cliente = OpenAI(api_key=clave, base_url=base_url or self.BASE_URL,
                               max_retries=self.MAX_REINTENTOS, timeout=self.TIMEOUT)
        # Semilla fija: la replica contrafactual necesita repetir el mismo
        # episodio. No todos los backends compatibles la respetan, y algunos
        # rechazan el parametro, asi que solo se manda si el backend lo acepta.
        self.seed = seed if self.SOPORTA_SEED else None
        self.temperature = (temperature if temperature is not None
                            else self.TEMPERATURA_POR_DEFECTO)

    @classmethod
    def _modelo_de_entorno(cls) -> str:
        """La variable especifica del proveedor gana sobre la generica: si no,
        un `HORMIGUERO_MODELO=gpt-4o-mini` en el .env se le mandaria a DeepSeek
        y la corrida moriria con un 400 sin explicacion."""
        for variable in cls.VARIABLES_MODELO:
            valor = os.environ.get(variable)
            if valor:
                return valor
        return cls.MODELO_POR_DEFECTO

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
                if t.reasoning_content is not None:
                    m["reasoning_content"] = t.reasoning_content
                out.append(m)
            elif isinstance(t, TurnoToolResult):
                if pendientes:
                    out.append({"role": "tool", "tool_call_id": pendientes.pop(0),
                                "content": t.contenido})
                else:
                    out.append({"role": "user",
                                "content": f"[{t.nombre_tool}] {t.contenido}"})
            elif isinstance(t, TurnoUsuario):
                out.append({"role": "user", "content": t.texto})
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
                            tokens=(tokens.total_tokens if tokens else 0),
                            reasoning_content=getattr(msg, "reasoning_content", None))
