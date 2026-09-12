"""El mapa de procedencia: de los logs del arnes a las curvas del paper."""

from .modelo import cargar, construir, leer_eventos, normalizar, nodo_decisivo, raices, contenedor
from .preguntas import (
    span_de_origen, mensajes_criticos, lista_de_bloqueo,
    visibilidad, visto_por, verificar_ancestria, span_acotado,
    linea_base_conteo, alarma_del_mapa, responder,
)
# `exportar` no se importa acá: tambien corre como `python -m
# hormiguero.grafo.exportar` y el import eager dispara un RuntimeWarning de
# runpy. Se pide con `from hormiguero.grafo.exportar import exportar_dot`.

__all__ = [
    "cargar", "construir", "leer_eventos", "normalizar", "nodo_decisivo",
    "raices", "contenedor", "span_de_origen", "mensajes_criticos",
    "lista_de_bloqueo", "visibilidad", "visto_por", "verificar_ancestria",
    "span_acotado", "linea_base_conteo", "alarma_del_mapa", "responder",
]
