"""
Carga de configuracion — Proyecto Hormiguero.

Lee .env sin depender de nada externo. Usalo en vez de escribir llaves en el codigo.

    from entorno import cfg, LLAVE_OPENAI

    cliente = OpenAI(api_key=LLAVE_OPENAI)
    pasos   = cfg("HORMIGUERO_MAX_PASOS", 10, int)

Si falta la llave, avisa claro en vez de fallar con un 401 diez minutos despues.
"""

import os
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent
_CARGADO = False


def _cargar_env():
    """Lee .env y lo mete en os.environ. Lo que ya este en el entorno gana."""
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
    _cargar_env()
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
            f"  1. cp .env.example .env\n"
            f"  2. abre .env y pon el valor\n"
            f"  .env esta ignorado por git, asi que no se sube.\n"
        )
    return valor


# Atajos de uso frecuente. Son perezosos: solo fallan si de verdad los usas.
class _Perezoso:
    def __init__(self, nombre):
        self._nombre = nombre

    def __str__(self):
        return llave(self._nombre)

    def __repr__(self):
        return f"<llave {self._nombre}: oculta>"   # que no se imprima en un traceback


LLAVE_OPENAI = _Perezoso("OPENAI_API_KEY")
LLAVE_ANTHROPIC = _Perezoso("ANTHROPIC_API_KEY")


if __name__ == "__main__":
    _cargar_env()
    print("Configuracion visible (los secretos NO se imprimen):")
    for k in sorted(os.environ):
        if k.startswith("HORMIGUERO_"):
            print(f"  {k} = {os.environ[k]}")
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        estado = "definida" if os.environ.get(k) else "FALTA"
        print(f"  {k} = <{estado}>")
