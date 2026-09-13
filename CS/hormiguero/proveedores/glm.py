"""
GLM (Z.ai / Zhipu) — el segundo modelo del barrido.

Mismo caso que DeepSeek: la API es compatible con la de OpenAI, asi que esto es
`ProveedorOpenAICompatible` apuntado a otro `base_url` — incluido el arreglo del
historial (`_mensajes`), que hace falta igual aca.

Con la llave en el .env no hay nada mas que configurar:

    GLM_API_KEY=...              en CS/.env (o en el .env de la raiz)
    python -m hormiguero.plan --proveedor glm

Para comprobar que la llave y el modelo responden, sin gastar un barrido entero:

    python -m hormiguero.proveedores.glm
"""

from __future__ import annotations

import os

from ..entorno import cargar_env
from .openai_compat import ProveedorOpenAICompatible


class ProveedorGLM(ProveedorOpenAICompatible):
    NOMBRE = "glm"
    VARIABLE_LLAVE = "GLM_API_KEY"
    VARIABLES_MODELO = ("GLM_MODELO",)
    MODELO_POR_DEFECTO = "glm-5.3"

    # El endpoint compatible con OpenAI. Z.ai publica varios (el estandar
    # `/api/paas/v4`, el del plan de coding): si el de ustedes es otro, se cambia
    # con GLM_BASE_URL en el .env, sin tocar codigo.
    BASE_URL = "https://api.z.ai/api/openai/v1"

    # No damos por hecho que acepte `seed`, y mandarlo seria arriesgar un 400 a
    # mitad de un barrido de horas.
    #
    # Lo que se pierde: que la corrida se repita bit a bit — que ya no teniamos.
    # Lo que NO se pierde: la replica contrafactual. Bloquea por contenido y
    # remitente, asi que no depende de que el modelo repita palabra por palabra.
    SOPORTA_SEED = False

    # Con temperatura 0 la varianza entre episodios del mismo punto baja, que es
    # lo mas cerca de reproducible que se puede estar sin semilla.
    TEMPERATURA_POR_DEFECTO = 0.0

    def __init__(self, *args, **kw):
        # El .env puede mandar otro endpoint. Se lee ANTES de construir el
        # cliente, porque el de la clase padre ya no se puede cambiar despues.
        cargar_env()
        if not kw.get("base_url"):
            kw["base_url"] = os.environ.get("GLM_BASE_URL") or self.BASE_URL
        self.base_url = kw["base_url"]
        super().__init__(*args, **kw)


def comprobar() -> int:
    """Una llamada minima, para saber si la llave y el modelo responden."""
    from .base import TurnoSistema

    try:
        p = ProveedorGLM()
    except RuntimeError as e:
        print(f"\n{e}\n")
        return 1

    print(f"  proveedor: glm | modelo: {p.modelo} | {p.base_url}")
    try:
        r = p.llamar([TurnoSistema("Responde exactamente con la palabra: listo")], [])
    except Exception as e:  # la SDK envuelve 401/404/429 en tipos propios
        print(f"  FALLA: {type(e).__name__}: {e}\n")
        print("  401 -> la llave esta mal o no tiene saldo")
        print(f"  404 -> el modelo '{p.modelo}' no existe en este endpoint.")
        print("         Revisa GLM_MODELO y GLM_BASE_URL en el .env: el nombre exacto")
        print("         del modelo sale de la consola de Z.ai.\n")
        return 1

    print(f"  respuesta: {(r.texto or '').strip()[:60]!r} | tokens: {r.tokens}")
    print("\n  OK: GLM responde. Ya puedes correr el barrido.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(comprobar())
