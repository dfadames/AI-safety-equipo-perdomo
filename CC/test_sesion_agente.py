"""
test_sesion_agente.py — Persona B

Prueba SesionAgente contra un ProveedorLLM de mentira — ni Ollama, ni
OpenAI, ni ninguno. Es justo el punto: si esto pasa, la trazabilidad y la
compactación funcionan sin importar qué proveedor conecten después.
Corran esto antes de gastar el primer token real en cualquier modelo.

Corre:  python test_sesion_agente.py
"""

import json
import shutil
from pathlib import Path

from arnes_host import Canal, PARTES_VALIDAS, Registro
from proveedores_llm import LlamadaTool, ProveedorLLM, RespuestaLLM
from sesion_agente import SesionAgente

TMP = Path("logs/_test_sesion")


class ProveedorFalso(ProveedorLLM):
    """Un ProveedorLLM que reproduce un guion fijo de respuestas, para no
    depender de ningún backend real en la prueba."""

    def __init__(self, guion: list[RespuestaLLM]):
        self._guion = iter(guion)

    def llamar(self, historial, herramientas) -> RespuestaLLM:
        return next(self._guion)


def tool(nombre: str, **argumentos) -> RespuestaLLM:
    return RespuestaLLM(texto="", tool_calls=[LlamadaTool(nombre, argumentos)])


def final(texto: str) -> RespuestaLLM:
    return RespuestaLLM(texto=texto, tool_calls=[])


def test_sesion_completa_hasta_try_unlock():
    registro = Registro(TMP / "sesion.jsonl", episode="ep_sesion_1", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_sesion", ["A", "B", "C", "D"])

    fragmentos = dict(zip("ABC", PARTES_VALIDAS))
    for a in "ABC":
        canal.publicar(a, f"evt_{a}_semilla", f"encontré cred_fragment: {fragmentos[a]}")

    proveedor = ProveedorFalso([
        tool("leer_canal"),
        tool("validar_credencial", valor="Alpha-Bravo-Charlie-Delta"),
        final("Listo, validé la credencial."),
    ])

    sesion = SesionAgente(proveedor, registro, canal, "D", "contenedor_D", prompt_sistema="prompt de prueba")
    sesion.correr(max_pasos=5)

    eventos = [json.loads(l) for l in open(TMP / "sesion.jsonl", encoding="utf-8")]
    tipos = [e["type"] for e in eventos]
    assert tipos.count("receive") == 3, f"esperaba 3 receive, hubo {tipos.count('receive')}"
    finales = [e for e in eventos if e["type"] == "try_unlock"]
    assert len(finales) == 1 and finales[0]["content"]["success"] is True

    contenidos = [t.texto if hasattr(t, "texto") else None for t in sesion.historial]
    assert sum(1 for c in contenidos if c and c.startswith("[recibido]")) == 3
    print("OK  test_sesion_completa_hasta_try_unlock")


def test_poda_de_historial_sincronizada_con_ventana():
    registro = Registro(TMP / "poda.jsonl", episode="ep_sesion_2", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_poda", ["A"])

    proveedor = ProveedorFalso(
        [tool("escribir_canal", mensaje=f"msg {i}") for i in range(6)] + [final("fin")]
    )

    sesion = SesionAgente(
        proveedor, registro, canal, "A", "contenedor_A", prompt_sistema="prompt de prueba", cap=3,
    )
    sesion.correr(max_pasos=10)

    eventos = {
        e["event_id"]: e
        for e in (json.loads(l) for l in open(TMP / "poda.jsonl", encoding="utf-8"))
    }
    resumenes = [e for e in eventos.values() if e["type"] == "summarize"]
    assert resumenes, "con cap=3 y 6 escrituras debió compactar al menos una vez"

    contenidos_resumen_log = [e["content"] for e in resumenes]
    contenidos_resumen_modelo = [
        getattr(t, "texto", "") for t in sesion.historial
        if getattr(t, "texto", "").startswith("Resumen de pasos anteriores")
    ]
    assert contenidos_resumen_log and contenidos_resumen_modelo, (
        "el resumen no llegó al log, o no llegó al historial que ve el modelo"
    )
    for c in contenidos_resumen_log:
        assert "msg " in c, f"el resumen del LOG no llevó contenido real, solo un conteo: {c!r}"
    print("OK  test_poda_de_historial_sincronizada_con_ventana")


def test_dos_proveedores_distintos_mismo_resultado():
    """El punto central de este archivo: cambiar el ProveedorLLM no debe
    cambiar ni una línea de SesionAgente ni del log producido."""
    def runner_simulado(contenedor, comando):
        return "cred_fragment: Alpha"

    resultados = {}
    for nombre_proveedor in ("falso_1", "falso_2"):
        ruta = TMP / f"agnostico_{nombre_proveedor}.jsonl"
        registro = Registro(ruta, episode=f"ep_{nombre_proveedor}", seed=1, condition="instruida")
        canal = Canal(TMP / f"shared_{nombre_proveedor}", ["A"])
        # dos INSTANCIAS de ProveedorFalso, simulando dos backends distintos
        proveedor = ProveedorFalso([
            tool("ejecutar", comando="grep cred /etc"),
            tool("validar_credencial", valor="Alpha"),
            final("no tengo las otras partes"),
        ])
        sesion = SesionAgente(
            proveedor, registro, canal, "A", "contenedor_A",
            prompt_sistema="p", runner=runner_simulado,
        )
        sesion.correr(max_pasos=5)
        eventos = [json.loads(l) for l in open(ruta, encoding="utf-8")]
        resultados[nombre_proveedor] = [(e["type"], e["content"]) for e in eventos]

    assert resultados["falso_1"] == resultados["falso_2"], (
        "dos proveedores con el mismo guion produjeron logs distintos -- "
        "algo en SesionAgente está acoplado a un proveedor específico"
    )
    print("OK  test_dos_proveedores_distintos_mismo_resultado")


if __name__ == "__main__":
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    test_sesion_completa_hasta_try_unlock()
    test_poda_de_historial_sincronizada_con_ventana()
    test_dos_proveedores_distintos_mismo_resultado()
    print("\nTodo pasó.")