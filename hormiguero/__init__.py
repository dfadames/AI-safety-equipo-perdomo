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

# `runner` NO se importa acá arriba: es un modulo que tambien se corre con
# `python -m hormiguero.runner`, y si el paquete ya lo importo antes de que
# runpy lo ejecute como __main__, Python tira un RuntimeWarning ("found in
# sys.modules... prior to execution"). `correr_episodio`/`barrido` se piden
# con `from hormiguero.runner import ...` en vez de `from hormiguero import ...`.

__version__ = "0.1.0"

__all__ = [
    "Config", "nombre_contenedor", "partes", "agentes",
    "Registro", "Canal", "Ventana", "NOTIFICAR_HUMANO_DESCRIPCION",
    "SesionAgente",
]
