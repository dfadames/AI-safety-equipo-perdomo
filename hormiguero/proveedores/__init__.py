"""Backends de LLM. Agregar uno nuevo no toca ningun otro archivo."""

from .base import (
    HERRAMIENTAS, LlamadaTool, ProveedorLLM, RespuestaLLM, ToolSpec,
    Turno, TurnoAsistente, TurnoSistema, TurnoToolResult,
)
from .simulado import ProveedorSimulado, guion_benigno, guion_escape

__all__ = [
    "HERRAMIENTAS", "LlamadaTool", "ProveedorLLM", "RespuestaLLM", "ToolSpec",
    "Turno", "TurnoAsistente", "TurnoSistema", "TurnoToolResult",
    "ProveedorSimulado", "guion_escape", "guion_benigno",
]
