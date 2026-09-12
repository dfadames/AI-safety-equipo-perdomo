"""
test_trazas.py — Persona B

Pruebas de la trazabilidad, no del contenido del episodio. Cada una
corresponde a un punto concreto de la revisión:

  - test_ventana_no_crece_sin_limite       -> el bug de PLAN.md §0.2
  - test_ejecutar_es_idempotente           -> hueco #3 de la revisión
  - test_receive_un_evento_por_mensaje     -> el requisito no negociable
                                               de EXPERIMENTOS.md §3
  - test_span_de_origen_sobrevive_al_resumen -> el riesgo de sub-conteo
                                               por compactación (hueco #1)
  - test_escrituras_concurrentes_no_corrompen_el_log -> el canal por
                                               agente resuelve la "nota
                                               sobre concurrencia" del plan
  - test_exact_parts_used                  -> ancestría exacta del nodo decisivo

Corre:  python test_trazas.py
"""

import json
import shutil
import threading
from pathlib import Path

from arnes_host import Canal, PARTES_VALIDAS, Registro, Ventana

TMP = Path("logs/_test")


def runner_simulado(contenedor: str, comando: str) -> str:
    """Reemplaza `docker exec` en las pruebas — no hay contenedores acá."""
    return f"(simulado) {comando} en {contenedor}"


def cargar(ruta_log: Path) -> list[dict]:
    with open(ruta_log, "r", encoding="utf-8") as f:
        return [json.loads(linea) for linea in f if linea.strip()]


def ancestros_de(eventos_por_id: dict[str, dict], evt_id: str) -> set[str]:
    """BFS manual sobre `ancestors` — el mismo cálculo que nx.ancestors()
    hará en grafo.py, sin necesitar la dependencia acá. Sirve como
    referencia de qué debe devolver C, y para probar mi propio generador."""
    vistos: set[str] = set()
    pendientes = list(eventos_por_id[evt_id]["ancestors"])
    while pendientes:
        actual = pendientes.pop()
        if actual in vistos or actual not in eventos_por_id:
            continue
        vistos.add(actual)
        pendientes.extend(eventos_por_id[actual]["ancestors"])
    return vistos


def test_ventana_no_crece_sin_limite():
    registro = Registro(TMP / "cap.jsonl", episode="ep_t1", seed=1, condition="instruida")
    v = Ventana(registro, "A", "contenedor_A", cap=3, runner=runner_simulado)
    v.ejecutar("caja_a", "echo hola")  # root
    for i in range(10):
        # escribir_canal no requiere contenedor real; forzamos eventos sin canal
        v._agregar(registro.escribir(
            agent_id="A", source_container="contenedor_A", type_="write_channel",
            content=f"msg {i}", ancestors=v.snapshot(),
        ))
    assert len(v.snapshot()) <= 3, (
        f"la ventana creció a {len(v.snapshot())} eventos con cap=3 — "
        "está reintroduciendo la bolsa monotónica"
    )
    print("OK  test_ventana_no_crece_sin_limite")


def test_ejecutar_es_idempotente():
    registro = Registro(TMP / "idem.jsonl", episode="ep_t2", seed=1, condition="instruida")
    v = Ventana(registro, "A", "contenedor_A", runner=runner_simulado)
    _, evt1 = v.ejecutar("caja_a", "grep cred /etc/config")
    _, evt2 = v.ejecutar("caja_a", "grep cred /etc/config")
    eventos = {e["event_id"]: e for e in cargar(TMP / "idem.jsonl")}
    assert eventos[evt1]["ancestors"] == [], "la primera ejecución debe ser raíz"
    assert evt2 != evt1, "la segunda llamada sí genera su propio evento..."
    assert eventos[evt2]["ancestors"] == [evt1], (
        "...pero debe heredar la ventana, no volver a ser raíz — si no, "
        "un mismo contenedor infla el span de origen sin cruzar ningún borde"
    )
    print("OK  test_ejecutar_es_idempotente")


def test_receive_un_evento_por_mensaje():
    registro = Registro(TMP / "receive.jsonl", episode="ep_t3", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_receive", ["A", "B", "C"])
    va, vb, vc = (Ventana(registro, a, f"contenedor_{a}", runner=runner_simulado) for a in "ABC")

    _, evtA = va.escribir_canal(canal, "encontré cred_fragment: Alpha")
    _, evtB = vb.escribir_canal(canal, "encontré cred_fragment: Bravo")
    recibidos, ids = vc.leer_canal(canal)

    assert len(recibidos) == 2 and len(ids) == 2, "dos mensajes nuevos -> dos eventos receive"
    eventos = {e["event_id"]: e for e in cargar(TMP / "receive.jsonl")}
    for rcv_id, esperado in zip(ids, (evtA, evtB)):
        assert eventos[rcv_id]["type"] == "receive"
        assert eventos[rcv_id]["ancestors"] == [esperado], (
            "cada receive debe tener EXACTAMENTE un ancestro: el write_channel "
            "de quien lo mandó — es la arista que C corta con capacidad 1"
        )

    # segunda lectura sin nada nuevo -> se registra la llamada igual, sin receive
    recibidos2, ids2 = vc.leer_canal(canal)
    assert recibidos2 == [] and ids2 == []
    tipos = [e["type"] for e in cargar(TMP / "receive.jsonl")]
    assert tipos.count("read_channel") == 1, (
        "una lectura vacía debe quedar registrada (type=read_channel), "
        "para distinguir 'no miró' de 'miró y no había nada'"
    )
    print("OK  test_receive_un_evento_por_mensaje")


def test_span_de_origen_sobrevive_al_resumen():
    """El caso que motivó agregar `summarize`: con una ventana chica que
    fuerza compactación, el span de origen medido desde el evento final
    debe seguir siendo 4 — la procedencia no se puede perder al comprimir."""
    ruta = TMP / "compactado.jsonl"
    registro = Registro(ruta, episode="ep_t4", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_compactado", ["A", "B", "C", "D"])
    fragmentos = dict(zip("ABCD", PARTES_VALIDAS))
    ventanas = {a: Ventana(registro, a, f"contenedor_{a}", cap=2, runner=runner_simulado) for a in "ABCD"}  # cap chico a propósito

    for a in "ABCD":
        ventanas[a].ejecutar(f"caja_{a.lower()}", "grep cred /etc")
        ventanas[a].escribir_canal(canal, f"encontré cred_fragment: {fragmentos[a]}")

    ventanas["D"].leer_canal(canal)  # esto solo, con cap=2, ya fuerza compactación en D
    credencial = "-".join(fragmentos.values())
    _, evt_final = ventanas["D"].validar_credencial(credencial)

    eventos = {e["event_id"]: e for e in cargar(ruta)}
    assert any(e["type"] == "summarize" for e in eventos.values()), (
        "con cap=2 debería haber ocurrido al menos una compactación — "
        "si no la hubo, la prueba no está probando lo que dice probar"
    )
    ancestros = ancestros_de(eventos, evt_final)
    contenedores_de_origen = {
        eventos[e]["source_container"] for e in ancestros if eventos[e]["type"] == "ejecutar"
    }
    assert len(contenedores_de_origen) == 4, (
        f"el span de origen dio {len(contenedores_de_origen)} tras la "
        "compactación — la procedencia se perdió en el resumen en vez de "
        "quedar colgada de él"
    )
    print("OK  test_span_de_origen_sobrevive_al_resumen")


def test_escrituras_concurrentes_no_corrompen_el_log():
    registro = Registro(TMP / "concurrencia.jsonl", episode="ep_t5", seed=1, condition="instruida")
    canal = Canal(TMP / "shared_concurrencia", ["A", "B", "C", "D"])
    # cap grande a propósito: esta prueba aísla la concurrencia de la
    # compactación (que ya se prueba aparte). Con el cap por defecto (8),
    # 50 escrituras por agente disparan `summarize` de sobra — real y
    # correcto, pero mezclaría dos cosas distintas en una sola prueba.
    ventanas = {
        a: Ventana(registro, a, f"contenedor_{a}", cap=10_000, runner=runner_simulado)
        for a in "ABCD"
    }

    def trabajo(agent_id):
        v = ventanas[agent_id]
        for i in range(50):
            v.escribir_canal(canal, f"{agent_id} mensaje {i}")

    hilos = [threading.Thread(target=trabajo, args=(a,)) for a in "ABCD"]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    lineas = (TMP / "concurrencia.jsonl").read_text(encoding="utf-8").splitlines()
    eventos = [json.loads(l) for l in lineas]  # explota si alguna línea quedó corrupta a la mitad
    ids = [e["event_id"] for e in eventos]
    pasos = [e["step"] for e in eventos]

    assert len(eventos) == 4 * 50, "se perdieron o duplicaron eventos bajo concurrencia"
    assert len(set(ids)) == len(ids), "hay event_id repetidos"
    assert sorted(pasos) == list(range(1, len(pasos) + 1)), (
        "el contador de step no es una secuencia sin huecos ni repetidos "
        "bajo escritura concurrente"
    )
    print("OK  test_escrituras_concurrentes_no_corrompen_el_log")


def test_exact_parts_used():
    registro = Registro(TMP / "partes.jsonl", episode="ep_t6", seed=1, condition="instruida")
    v = Ventana(registro, "D", "contenedor_D", runner=runner_simulado)
    _, evt = v.validar_credencial("Alpha-Bravo-INCOMPLETO")
    eventos = {e["event_id"]: e for e in cargar(TMP / "partes.jsonl")}
    assert eventos[evt]["exact_parts_used"] == ["Alpha", "Bravo"]
    assert eventos[evt]["content"]["success"] is False
    print("OK  test_exact_parts_used")


if __name__ == "__main__":
    # limpio antes de cada corrida: el Canal solo hace touch() de sus
    # archivos, no los trunca, así que restos de una corrida anterior
    # contaminarían leer_canal() con mensajes que no son de esta corrida.
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)
    test_ventana_no_crece_sin_limite()
    test_ejecutar_es_idempotente()
    test_receive_un_evento_por_mensaje()
    test_span_de_origen_sobrevive_al_resumen()
    test_escrituras_concurrentes_no_corrompen_el_log()
    test_exact_parts_used()
    print("\nTodo pasó.")