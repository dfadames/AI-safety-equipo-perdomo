"""
Carga de configuracion y secretos desde `.env` — Proyecto Hormiguero.

Es la version que vive DENTRO del paquete: los proveedores de LLM importan
esto, no el `entorno.py` de la raiz del repo, para que el proyecto en `CS/`
no dependa de nada fuera de si mismo. El `.env` se busca en la raiz de este
proyecto (un nivel arriba de `hormiguero/`), junto al `requirements.txt`.

    from .entorno import cargar_env, llave, cfg

    cargar_env()
    cliente = OpenAI(api_key=llave("OPENAI_API_KEY"))
    pasos   = cfg("HORMIGUERO_MAX_PASOS", 10, int)

Si falta la llave, avisa claro en vez de fallar con un 401 diez minutos despues.
"""

from __future__ import annotations

import os
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
_CARGADO = False


def cargar_env() -> None:
    """Lee `.env` y lo mete en os.environ. Lo que ya este en el entorno gana."""
    global _CARGADO
    if _CARGADO:
        return
    _CARGADO = True

    ruta = _RAIZ / ".env"
    if not ruta.exists():
        return

    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave, valor = clave.strip(), valor.strip().strip("'\"")
        if valor and clave not in os.environ:   # una variable real del shell manda
            os.environ[clave] = valor


def cfg(nombre, defecto=None, tipo=str):
    """Lee una variable de configuracion, con valor por defecto y conversion."""
    cargar_env()
    bruto = os.environ.get(nombre)
    if bruto is None or bruto == "":
        return defecto
    if tipo is bool:
        return bruto.strip().lower() in ("1", "true", "si", "sí", "yes")
    try:
        return tipo(bruto)
    except (TypeError, ValueError):
        return defecto


def llave(nombre):
    """Como cfg(), pero para secretos: si falta, explica que hacer."""
    valor = cfg(nombre)
    if not valor:
        raise RuntimeError(
            f"\nFalta {nombre}.\n"
            f"  1. cp .env.example .env   (dentro de CS/)\n"
            f"  2. abre .env y pon el valor\n"
            f"  .env esta ignorado por git, asi que no se sube.\n"
        )
    return valor
