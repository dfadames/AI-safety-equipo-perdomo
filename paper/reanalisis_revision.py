"""Re-analysis of the 37 released episodes for the paper revision.
Read-only over resultados/. Run from CS/:  py -3.11 <this file>"""
import itertools, json, re, statistics, sys
from collections import defaultdict
from pathlib import Path

import networkx as nx

sys.path.insert(0, ".")
from hormiguero.config import Config, IDS_AGENTE
from hormiguero.grafo.agregar import por_episodio, es_replica, conducta
from hormiguero.grafo.modelo import construir, nodo_decisivo, raices, TIPOS_RESTRINGIDOS, contenedor
from hormiguero.grafo.preguntas import span_de_origen, mensajes_criticos

# The paper's 37 episodes (task v1) were moved out of resultados/ when the v2 batch started.
RAIZ = Path("..") / "resultados_v1"
eps = {k: v for k, v in por_episodio(str(RAIZ)).items() if not es_replica(k)}
print(f"\nepisodes (non-replica): {len(eps)}")


def cfg_de(evs):
    c = evs[0]["config"]; cond = evs[0]["condition"]
    return Config(n_agentes=c["n_agentes"], n_partes=c["n_partes"], peldano=c["peldano"],
                  condicion=cond, escenario="benigno" if cond == "benigna" else "credencial")


def parte_de_caja(cfg, caja):
    agente = IDS_AGENTE[int(caja.split("_")[1]) - 1]
    return cfg.partes[cfg.indice_de_parte(agente)]


rows = []
import time
for ep, evs in sorted(eps.items()):
    t0 = time.time()
    print(f"  .. {ep} ({len(evs)} events)", flush=True)
    cfg = cfg_de(evs)
    G = construir(evs)
    cajas = {a["source_container"] for _, a in G.nodes(data=True)}
    agentes = {a["agent_id"] for _, a in G.nodes(data=True)}
    r = dict(ep=ep, cond=evs[0]["condition"], rung=cfg.peldano, N=cfg.n_agentes, P=cfg.n_partes,
             n_events=G.number_of_nodes(), n_boxes=len(cajas), n_agents=len(agentes))
    final = nodo_decisivo(G)
    if final is not None:
        span, conts = span_de_origen(G, final)
        cut, corte = mensajes_criticos(G, final)
        used = set(G.nodes[final]["exact_parts_used"])
        held = defaultdict(set)
        for c in conts:
            held[parte_de_caja(cfg, c)].add(c)
        # identity-level check: every used part is held by some container in the span
        ident_ok = used <= set(held)
        dup = sum(len(v) - 1 for v in held.values())
        cut_msgs = []
        for u, v, au, av in corte:
            txt = str(G.nodes[u]["content"])
            cut_msgs.append((au, [p for p in cfg.partes if p in txt]))
        r.update(escape=True, span=span, cut=cut, used=len(used), ident_ok=ident_ok,
                 dup_containers=dup, validator=G.nodes[final]["agent_id"], step=G.nodes[final]["step"],
                 n_anc=len(nx.ancestors(G, final)),
                 cut_senders=len({a for a, _ in cut_msgs}),
                 cut_msg_parts=cut_msgs,
                 cited=bool(G.nodes[final].get("cited_by_agent")))
    else:
        r.update(escape=False)
    # every restricted action with span>1 (the map's alarm)
    alarms = []
    for n, a in G.nodes(data=True):
        if a.get("type") in TIPOS_RESTRINGIDOS:
            s, _ = span_de_origen(G, n)
            alarms.append((a["step"], a["agent_id"], s, bool(a.get("success"))))
    r["restricted"] = sorted(alarms)
    beh = conducta(evs)
    r["n_cmds"] = sum(1 for e in evs if e.get("type") == "ejecutar")
    r.update(beh)
    rows.append(r)

# P=1 is the legitimate-validation control, not an escape
esc = [r for r in rows if r["escape"] and r["P"] > 1]
print(f"escapes: {len(esc)}")
print("\n== per-escape ==")
print("ep | cond rung N P | span cut used | span-1 cut-(span-1) | ident_ok dup | validator step anc/events | cut senders | cut msg parts")
for r in esc:
    print(f"{r['ep']:42s} {r['cond'][:5]} {r['rung']} N={r['N']} P={r['P']} | span={r['span']} cut={r['cut']} used={r['used']} "
          f"| d={r['cut']-(r['span']-1)} | ident={r['ident_ok']} dup={r['dup_containers']} "
          f"| {r['validator']}@{r['step']} {r['n_anc']}/{r['n_events']} | snd={r['cut_senders']} | {r['cut_msg_parts']} | cited={r['cited']}")

print("\n== summaries ==")
print("boxes==agents in all eps:", all(r["n_boxes"] == r["n_agents"] == r["N"] for r in rows))
print("identity-level under-attribution:", sum(not r["ident_ok"] for r in esc))
print("count verdicts exact/over/under:",
      sum(r["span"] == r["P"] for r in esc), sum(r["span"] > r["P"] for r in esc), sum(r["span"] < r["P"] for r in esc))
print("over-attribution == duplicate-part containers in all over cases:",
      all(r["span"] - r["P"] == r["dup_containers"] for r in esc))
for lab, g in [("N==P", [r for r in esc if r["N"] == r["P"]]), ("N>P", [r for r in esc if r["N"] > r["P"]])]:
    print(f"  {lab}: n={len(g)} exact={sum(r['span']==r['P'] for r in g)} over={sum(r['span']>r['P'] for r in g)}")
print("cut == span-1:", sum(r["cut"] == r["span"] - 1 for r in esc), "/", len(esc),
      "; cut >= span-1 always:", all(r["cut"] >= r["span"] - 1 for r in esc))
print("cut == P-1:", sum(r["cut"] == r["P"] - 1 for r in esc), " cut==P:", sum(r["cut"] == r["P"] for r in esc),
      " cut==P+1:", sum(r["cut"] == r["P"] + 1 for r in esc))
print("cut > distinct senders (a sender contributes >1 route):",
      sum(r["cut"] > r["cut_senders"] for r in esc))
multi = sum(1 for r in esc for _, ps in r["cut_msg_parts"] if len(ps) > 1)
tot = sum(len(r["cut_msg_parts"]) for r in esc)
nopart = sum(1 for r in esc for _, ps in r["cut_msg_parts"] if len(ps) == 0)
print(f"cut messages: {tot}; carrying >1 part name: {multi}; carrying no part name: {nopart}")
print("decisive validations with cited_by_agent filled:", sum(r["cited"] for r in esc), "/", len(esc))


# ---- association: exact permutation Spearman within each arm ----
def ranks(x):
    s = sorted(x)
    return [sum(i + 1 for i, v in enumerate(s) if v == xi) / s.count(xi) for xi in x]


def pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((u - ma) * (v - mb) for u, v in zip(a, b))
    den = (sum((u - ma) ** 2 for u in a) * sum((v - mb) ** 2 for v in b)) ** 0.5
    return num / den


def spearman_exact(x, y):
    rx, ry = ranks(x), ranks(y)
    obs = pearson(rx, ry)
    cnt = tot = 0
    for p in itertools.permutations(ry):
        tot += 1
        if abs(pearson(rx, p)) >= abs(obs) - 1e-12:
            cnt += 1
    return obs, cnt / tot


def ols(X, y):
    """Normal equations, 3x3, pure python."""
    k = len(X[0])
    XtX = [[sum(r[i] * r[j] for r in X) for j in range(k)] for i in range(k)]
    Xty = [sum(r[i] * yy for r, yy in zip(X, y)) for i in range(k)]
    # Gauss-Jordan inverse
    A = [row[:] + [1.0 if i == j else 0.0 for j in range(k)] for i, row in enumerate(XtX)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(A[r][c])); A[c], A[piv] = A[piv], A[c]
        d = A[c][c]; A[c] = [v / d for v in A[c]]
        for r in range(k):
            if r != c:
                f = A[r][c]; A[r] = [vr - f * vc for vr, vc in zip(A[r], A[c])]
    inv = [row[k:] for row in A]
    b = [sum(inv[i][j] * Xty[j] for j in range(k)) for i in range(k)]
    resid = [yy - sum(bi * xi for bi, xi in zip(b, r)) for r, yy in zip(X, y)]
    s2 = sum(e * e for e in resid) / (len(y) - k)
    se = [(s2 * inv[i][i]) ** 0.5 for i in range(k)]
    return b, se, len(y) - k


instr = [r for r in esc if r["cond"] == "instruida"]
armP = [r for r in instr if r["N"] == 4]
armN = [r for r in instr if r["P"] == 4]
for lab, g, key in [("P-sweep (N=4)", armP, "P"), ("N-sweep (P=4)", armN, "N")]:
    x = [r[key] for r in g]; y = [r["cut"] for r in g]
    rho, p = spearman_exact(x, y)
    print(f"{lab}: n={len(g)} x={x} cut={y} spearman={rho:.3f} exact two-sided p={p:.4f}")

X = [[1.0, float(r["N"]), float(r["P"])] for r in instr]; y = [float(r["cut"]) for r in instr]
b, se, dof = ols(X, y)
t = 2.228  # t_{0.975, 10}
print(f"OLS on 13 instructed escapes: cut = {b[0]:.2f} + {b[1]:.3f} N + {b[2]:.3f} P ; dof={dof}")
for nm, bi, si in zip(["int", "N", "P"], b, se):
    print(f"   {nm}: {bi:.3f}  SE={si:.3f}  95%CI=[{bi-t*si:.2f}, {bi+t*si:.2f}]")

# ---- 1-part control ----
print("\n== 1-part control ==")
for r in rows:
    if r["P"] == 1:
        print(r["ep"], "restricted (step, agent, span, success):", r["restricted"])

# ---- no-escape episodes: any restricted action? ----
print("\n== restricted actions in non-escape, non-impossible, non-control eps ==")
for r in rows:
    if not r["escape"] and r["cond"] != "imposible" and r["P"] != 1:
        print(f"  {r['ep']}: {len(r['restricted'])}")

# ---- impossible task normalised ----
print("\n== behaviour, per command ==")
for lab, g in [("impossible", [r for r in rows if r["cond"] == "imposible"]),
               ("others", [r for r in rows if r["cond"] != "imposible"])]:
    cm = sum(r["n_cmds"] for r in g); oo = sum(r["comandos_fuera_de_alcance"] for r in g)
    gs = sum(r["busquedas_globales"] for r in g)
    at = sum(r["N"] for r in g)
    print(f"{lab}: eps={len(g)} cmds/ep={cm/len(g):.1f} out-of-scope/ep={oo/len(g):.2f} global/ep={gs/len(g):.2f} "
          f"| out-of-scope per 100 cmds={100*oo/cm:.2f} global per 100 cmds={100*gs/cm:.2f} | cmds per agent={cm/at:.1f}")
    print(f"   eps with >=1 out-of-scope: {sum(r['comandos_fuera_de_alcance']>0 for r in g)}/{len(g)}")

# ---- Figure-1 episode and R3 anecdote ----
print("\n== Fig 1 episode ==")
for r in esc:
    if r["ep"] == "ep_instruida_P4_N4_42":
        print(r["validator"], r["step"], r["n_anc"], r["n_events"], r["span"], r["cut"])
print("\n== R3 181913 ==")
evs = eps["ep_emergente_P4_N4_42_181913"]
for e in sorted(evs, key=lambda e: e["step"]):
    if e["type"] in ("write_channel", "notify_human", "try_unlock") or (e["type"] == "razonamiento" and e["agent_id"] == "A"):
        print(f"  {e['step']:3d} {e['agent_id']} {e['type']:14s} {str(e['content'])[:230]!r} success={e.get('success')}")
