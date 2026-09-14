"""Attribution baselines for the paper: what the graph's origin span recovers
that a cheaper reading of the logs does not.

Three methods are scored part by part against the same oracle:

  graph    the origin span: containers with a root in the ancestry of the
           decisive action.
  sender   what an overseer gets from the validating agent's own trace: the
           containers of the agents that sent it the messages in its context.
  cut      the senders of the messages on the minimum cut only.

A method attributes part p correctly when the container set it names includes
some container that actually holds p. Precision counts the containers it names
that hold no part of the credential.

Read-only over the results folder:
    py paper/baseline_atribucion.py
    py paper/baseline_atribucion.py --resultados resultados_v1
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_REPO / "CS"))

import networkx as nx  # noqa: E402

from hormiguero.config import Config, partes_en  # noqa: E402
from hormiguero.grafo.agregar import cfgs_de, es_replica, por_episodio  # noqa: E402
from hormiguero.grafo.modelo import construir, nodo_decisivo  # noqa: E402
from hormiguero.grafo.preguntas import mensajes_criticos, span_de_origen  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--resultados", default="resultados")
ap.add_argument("--salida", default=None)
args = ap.parse_args()
RAIZ = Path(args.resultados)
if not RAIZ.is_absolute() and not RAIZ.exists():
    RAIZ = RAIZ_REPO / RAIZ
if args.salida:
    sys.stdout = open(args.salida, "w", encoding="utf-8")
else:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

with open(RAIZ / "resumen.csv", encoding="utf-8", newline="") as f:
    estado = {r["episodio"]: r.get("estado") or "" for r in csv.DictReader(f)}
fallidos = {e for e, s in estado.items() if s.startswith("error")}
eps = {k: v for k, v in por_episodio(str(RAIZ)).items() if not es_replica(k) and k not in fallidos}
cfgs = cfgs_de(str(RAIZ))


def cfg_de(ep, evs):
    e0 = evs[0]
    datos = {k: v for k, v in (cfgs.get(ep) or e0.get("config") or {}).items() if not k.startswith("dir_")}
    if datos.get("semilla") is None and e0.get("seed") is not None:
        datos["semilla"] = e0["seed"]
    datos.setdefault("condicion", e0.get("condition"))
    datos.setdefault("escenario", "benigno" if datos["condicion"] == "benigna" else "credencial")
    return Config.desde_dict(datos)


filas = []
for ep, evs in sorted(eps.items()):
    cfg = cfg_de(ep, evs)
    if cfg.n_partes < 2:
        continue                                  # el control de 1 parte no tiene origenes ajenos
    G = construir(evs)
    final = nodo_decisivo(G)
    if final is None:
        continue
    at = G.nodes[final]
    ps = list(cfg.partes)
    caja_de = {a["agent_id"]: a.get("source_container") for _, a in G.nodes(data=True)}
    agente_de = {c: a for a, c in caja_de.items()}
    # El oraculo: que contenedores tienen cada parte. Independiente del grafo.
    titular = defaultdict(set)
    for c, a in agente_de.items():
        titular[ps[cfg.indice_de_parte(a)]].add(c)
    usadas = set(partes_en(str(at.get("content")), ps, cfg.version_tarea))

    span, conts = span_de_origen(G, final)
    _, corte = mensajes_criticos(G, final)

    # Linea base por remitente: los contenedores de quienes le mandaron mensajes al
    # agente que valida, leidos de SU PROPIA traza, mas el suyo.
    anc = nx.ancestors(G, final) | {final}
    validador = at["agent_id"]
    remitentes = {caja_de[validador]}
    for u, v, d in G.edges(data=True):
        if d.get("kind") == "transfiere" and v in anc and G.nodes[v]["agent_id"] == validador:
            remitentes.add(caja_de[G.nodes[u]["agent_id"]])
    # Linea base por corte: solo los remitentes de los mensajes del corte minimo.
    del_corte = {caja_de[au] for _u, _v, au, _av in corte} | {caja_de[validador]}

    metodos = {"graph": set(conts), "sender": remitentes, "cut": del_corte}
    fila = dict(ep=ep, cond=evs[0]["condition"], N=cfg.n_agentes, P=cfg.n_partes,
                usadas=usadas, titular=dict(titular), relevo=False)
    for u, _v, au, _av in corte:
        llevadas = partes_en(str(G.nodes[u].get("content")), ps, cfg.version_tarea)
        propia = ps[cfg.indice_de_parte(au)]
        if any(p != propia for p in llevadas):
            fila["relevo"] = True
    for nombre, cajas in metodos.items():
        aciertos = sum(1 for p in usadas if cajas & titular[p])
        necesarias = {c for p in usadas for c in titular[p]}
        fila[nombre] = dict(cajas=cajas, aciertos=aciertos,
                            extra=len(cajas - necesarias), tam=len(cajas))
    filas.append(fila)

print(f"results: {RAIZ}")
print(f"escapes scored: {len(filas)}  (P>=2, decisive validation present)")
print(f"escapes with a relayed part on the minimum cut: {sum(f['relevo'] for f in filas)}")

NOMBRES = {"graph": "Origin span (graph)", "sender": "Senders in the validating agent's trace",
           "cut": "Senders on the minimum cut"}
print("\n== part-level attribution against the oracle ==")
print(f"{'method':42s} {'parts found':>13s} {'escapes complete':>17s} {'mean containers named':>22s}")
total_partes = sum(len(f["usadas"]) for f in filas)
for m in ("graph", "sender", "cut"):
    ac = sum(f[m]["aciertos"] for f in filas)
    completos = sum(f[m]["aciertos"] == len(f["usadas"]) for f in filas)
    tam = sum(f[m]["tam"] for f in filas) / len(filas)
    print(f"{NOMBRES[m]:42s} {ac:6d}/{total_partes:<6d} {completos:9d}/{len(filas):<7d} {tam:22.2f}")

print("\n== restricted to the escapes with a relay on the cut ==")
rel = [f for f in filas if f["relevo"]]
for m in ("graph", "sender", "cut"):
    ac = sum(f[m]["aciertos"] for f in rel)
    tp = sum(len(f["usadas"]) for f in rel)
    completos = sum(f[m]["aciertos"] == len(f["usadas"]) for f in rel)
    print(f"  {NOMBRES[m]:40s} {ac}/{tp} parts, {completos}/{len(rel)} escapes complete")

print("\n== where the methods differ, escape by escape ==")
distintos = 0
for f in filas:
    if f["graph"]["cajas"] == f["sender"]["cajas"] and f["graph"]["aciertos"] == f["sender"]["aciertos"]:
        continue
    distintos += 1
    print(f"  {f['ep']:40s} relay={f['relevo']} "
          f"graph={sorted(f['graph']['cajas'])} ({f['graph']['aciertos']}/{len(f['usadas'])}) "
          f"sender={sorted(f['sender']['cajas'])} ({f['sender']['aciertos']}/{len(f['usadas'])})")
if not distintos:
    print("  none: the span and the senders in the trace name the same containers in every escape")
print(f"\nescapes where graph and sender differ: {distintos}/{len(filas)}")
print("channel is broadcast, so every post reaches every agent:",
      "this is why the sender baseline is strong here")
