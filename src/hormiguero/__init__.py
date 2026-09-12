"""
Hormiguero — Containment Does Not Compose.

Banco de pruebas de contencion poblacional: N agentes en contenedores
aislados, cada uno aprobando su auditoria individual, un canal compartido, y
un objetivo que ninguno alcanza solo y la poblacion si.
"""

from .config import Config, nombre_contenedor, partes, agentes
from .registro import Registro
from .canal import Canal
from .ventana import Ventana, NOTIFICAR_HUMANO_DESCRIPCION
from .sesion import SesionAgente
from .runner import correr_episodio, barrido

__version__ = "0.1.0"

__all__ = [
    "Config", "nombre_contenedor", "partes", "agentes",
    "Registro", "Canal", "Ventana", "NOTIFICAR_HUMANO_DESCRIPCION",
    "SesionAgente", "correr_episodio", "barrido",
]
