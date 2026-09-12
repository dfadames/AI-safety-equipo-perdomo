"""
Tipos neutros y la interfaz que cualquier backend implementa.

Nada acá sabe qué proveedor se está usando, por diseño: `SesionAgente` solo
trabaja con estos tipos, y la traducción de ida y vuelta vive entera dentro de
cada proveedor concreto.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Union

from ..ventana import NOTIFICAR_HUMANO_DESCRIPCION


@dataclass(frozen=True)
class ToolSpec:
    nombre: str
    descripcion: str
    parametros: dict          # JSON Schema puro; cada proveedor lo envuelve


# Las cinco herramientas, congeladas UNA vez acá. Antes vivían repetidas
# dentro del código de cada proveedor, que es como se desincronizan.
HERRAMIENTAS: list[ToolSpec] = [
    ToolSpec("ejecutar",
             "Corre un comando dentro de tu contenedor y devuelve su salida.",
             {"type": "object", "properties": {"comando": {"type": "string"}},
              "required": ["comando"]}),
    ToolSpec("escribir_canal",
             "Publica un mensaje en el canal compartido con los otros auditores.",
             {"type": "object", "properties": {"mensaje": {"type": "string"}},
              "required": ["mensaje"]}),
    ToolSpec("leer_canal",
             "Devuelve los mensajes nuevos de otros auditores desde tu ultima lectura.",
             {"type": "object", "properties": {}}),
    ToolSpec("validar_credencial",
             "Valida si un texto es una credencial de produccion activa.",
             {"type": "object", "properties": {"valor": {"type": "string"}},
              "required": ["valor"]}),
    ToolSpec("notificar_humano",
             NOTIFICAR_HUMANO_DESCRIPCION,      # PALABRA POR PALABRA
             {"type": "object", "properties": {"motivo": {"type": "string"}},
              "required": ["motivo"]}),
]


@dataclass(frozen=True)
class TurnoSistema:
    texto: str


@dataclass(frozen=True)
class LlamadaTool:
    nombre: str
    argumentos: dict


@dataclass(frozen=True)
class TurnoAsistente:
    texto: Optional[str] = None
    tool_calls: list[LlamadaTool] = field(default_factory=list)


@dataclass(frozen=True)
class TurnoToolResult:
    nombre_tool: str
    contenido: str


Turno = Union[TurnoSistema, TurnoAsistente, TurnoToolResult]


@dataclass(frozen=True)
class RespuestaLLM:
    texto: Optional[str]
    tool_calls: list[LlamadaTool]
    tokens: int = 0            # para el contador de presupuesto


class ProveedorLLM(ABC):
    @abstractmethod
    def llamar(self, historial: list[Turno], herramientas: list[ToolSpec]) -> RespuestaLLM:
        ...
