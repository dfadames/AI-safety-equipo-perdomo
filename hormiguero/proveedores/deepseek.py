"""
DeepSeek.

La API es compatible con la de OpenAI, asi que esto es `ProveedorOpenAICompatible`
apuntado a otro `base_url` — incluido el arreglo del historial (`_mensajes`), que
hace falta igual aca: en cuanto se compacta el contexto, un `role: tool` sin su
`tool_call` da 400.

    DEEPSEEK_API_KEY=sk-...      en el .env de la raiz
    python -m hormiguero.runner barrido --proveedor deepseek

Para comprobar que la llave sirve, sin gastar un barrido entero:

    python -m hormiguero.proveedores.deepseek
"""

from __future__ import annotations

from .openai_compat import ProveedorOpenAICompatible


class ProveedorDeepSeek(ProveedorOpenAICompatible):
    NOMBRE = "deepseek"
    VARIABLE_LLAVE = "DEEPSEEK_API_KEY"
    VARIABLES_MODELO = ("DEEPSEEK_MODELO",)
    MODELO_POR_DEFECTO = "deepseek-flash"
    BASE_URL = "https://api.deepseek.com"

    # DeepSeek no expone `seed`. Mandarlo seria arriesgar un 400 a mitad de un
    # barrido de horas, asi que no se manda.
    #
    # Lo que se pierde: la corrida no es reproducible bit a bit.
    # Lo que NO se pierde: la replica contrafactual. Esa no depende de que el
    # modelo repita palabra por palabra — vuelve a correr el episodio con los
    # event_id del corte bloqueados y mide si el escape sigue ocurriendo. Por
    # eso el barrido corre VARIOS episodios por punto y no uno: sin semilla, un
    # episodio suelto no dice nada.
    SOPORTA_SEED = False

    # Con temperatura 0 la varianza entre episodios del mismo punto baja, que
    # es lo mas cerca de reproducible que se puede estar sin semilla.
    TEMPERATURA_POR_DEFECTO = 0.0


def comprobar() -> int:
    """Una llamada minima, para saber si la llave y el modelo responden."""
    from .base import TurnoSistema

    try:
        p = ProveedorDeepSeek()
    except RuntimeError as e:
        print(f"\n{e}\n")
        return 1

    print(f"  proveedor: deepseek | modelo: {p.modelo} | {p.BASE_URL}")
    try:
        r = p.llamar([TurnoSistema("Responde exactamente con la palabra: listo")], [])
    except Exception as e:  # la SDK envuelve 401/404/429 en tipos propios
        print(f"  FALLA: {type(e).__name__}: {e}\n")
        print("  401 -> la llave esta mal o no tiene saldo")
        print(f"  404 -> el modelo '{p.modelo}' no existe; revisa DEEPSEEK_MODELO en .env\n")
        return 1

    print(f"  respuesta: {(r.texto or '').strip()[:60]!r} | tokens: {r.tokens}")
    print("\n  OK: DeepSeek responde. Ya puedes correr el barrido.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(comprobar())
