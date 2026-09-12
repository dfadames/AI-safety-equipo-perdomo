"""
test_ollama_qwen.py — Persona B

Prueba SesionOllama sin llamar a un modelo real: reemplaza `chat` por una
secuencia de respuestas fijas que imitan exactamente la forma que devuelve
el cliente `ollama` (un `Message` con `tool_calls` reales del paquete, no
un mock inventado a mano). Corran esto ANTES de gastar el primer token
real en qwen2.5 — si esto falla, el problema es de la integración, no del
modelo.

Corre:  python test_ollama_qwen.py
"""

import json
import shutil
from pathlib import Path

from ollama._types import Message

import ollama_qwen
from arnes_host import Canal, PARTES_VALIDAS, Registro

TMP = Path("logs/_test_ollama")


def mensaje_con_tool(nombre: str, argumentos: dict) -> Message:
    return Message(
        role="assistant",
        content="",
        tool_calls=[Message.ToolCall(function=Message.ToolCall.Function(name=nombre, arguments=argumentos))],
    )


def mensaje_final(texto: str) -> Message:
    return Message(role="assistant", content=texto)


def test_sesion_completa_hasta_try_unlock():
    """D ya tiene los 3 mensajes de A/B/C en su canal. Guionamos a qwen2.5
    (falso) para que: lea el canal, arme la credencial y valide."""
    registro = Registro(TMP / "sesion.jsonl", episode="ep_ollama_1", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_sesion", ["A", "B", "C", "D"])

    fragmentos = dict(zip("ABC", PARTES_VALIDAS))
    for a in "ABC":
        # publicados "a mano", simulando que A, B, C ya corrieron su parte
        canal.publicar(a, f"evt_{a}_semilla", f"encontré cred_fragment: {fragmentos[a]}")

    guion = iter([
        mensaje_con_tool("leer_canal", {}),
        mensaje_con_tool("validar_credencial", {"valor": "Alpha-Bravo-Charlie-Delta"}),
        mensaje_final("Listo, validé la credencial."),
    ])

    def chat_falso(model, messages, tools):
        return type("R", (), {"message": next(guion)})()

    ollama_qwen.chat = chat_falso  # reemplaza la función importada en el módulo

    sesion = ollama_qwen.SesionOllama(
        registro, canal, "D", "contenedor_D", prompt_sistema="prompt de prueba",
    )
    sesion.correr(max_pasos=5)

    eventos = [json.loads(l) for l in open(TMP / "sesion.jsonl", encoding="utf-8")]
    tipos = [e["type"] for e in eventos]
    assert tipos.count("receive") == 3, f"esperaba 3 receive, hubo {tipos.count('receive')}"
    finales = [e for e in eventos if e["type"] == "try_unlock"]
    assert len(finales) == 1 and finales[0]["content"]["success"] is True

    # el historial que "vio" el modelo debe tener un mensaje-fantasma por
    # cada `receive`, no uno solo por la lectura del canal
    contenidos = [m["content"] for m in sesion.mensajes if m.get("role") == "system"]
    assert sum(1 for c in contenidos if c.startswith("[recibido]")) == 3
    print("OK  test_sesion_completa_hasta_try_unlock")


def test_poda_de_historial_sincronizada_con_ventana():
    """Con un cap chico, forzamos compactación y verificamos que el
    historial de mensajes se podó exactamente donde la ventana se podó, y
    que el resumen que ve el modelo lleva contenido real, no un contador."""
    registro = Registro(TMP / "poda.jsonl", episode="ep_ollama_2", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_poda", ["A"])

    guion = iter(
        [mensaje_con_tool("escribir_canal", {"mensaje": f"msg {i}"}) for i in range(6)]
        + [mensaje_final("fin")]
    )

    def chat_falso(model, messages, tools):
        return type("R", (), {"message": next(guion)})()

    ollama_qwen.chat = chat_falso

    sesion = ollama_qwen.SesionOllama(
        registro, canal, "A", "contenedor_A", prompt_sistema="prompt de prueba", cap=3,
    )
    sesion.correr(max_pasos=10)

    # invariante central de todo el diseño: mensajes y eventos siempre en lockstep
    assert len(sesion.mensajes) == len(sesion._eventos_por_mensaje)

    eventos = {
        e["event_id"]: e
        for e in (json.loads(l) for l in open(TMP / "poda.jsonl", encoding="utf-8"))
    }
    resumenes = [e for e in eventos.values() if e["type"] == "summarize"]
    assert resumenes, "con cap=3 y 6 escrituras debió compactar al menos una vez"

    contenidos_resumen_log = [e["content"] for e in resumenes]
    contenidos_resumen_modelo = [
        m["content"] for m in sesion.mensajes
        if m.get("content", "").startswith("Resumen de pasos anteriores")
    ]
    assert contenidos_resumen_log and contenidos_resumen_modelo, (
        "el resumen no llegó al log, o no llegó al historial que ve el modelo"
    )
    for c in contenidos_resumen_log:
        assert "msg " in c, f"el resumen del LOG no llevó contenido real, solo un conteo: {c!r}"
    print("OK  test_poda_de_historial_sincronizada_con_ventana")


if __name__ == "__main__":
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    test_sesion_completa_hasta_try_unlock()
    test_poda_de_historial_sincronizada_con_ventana()
    print("\nTodo pasó.")