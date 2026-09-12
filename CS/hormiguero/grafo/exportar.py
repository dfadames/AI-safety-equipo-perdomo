"""Exportacion del mapa para la figura principal (graphviz .dot)."""

from __future__ import annotations

import networkx as nx

from .modelo import nodo_decisivo

COLOR = {"A": "#1f77b4", "B": "#2ca02c", "C": "#9467bd", "D": "#d62728",
         "E": "#ff7f0e", "F": "#8c564b", "G": "#e377c2", "H": "#7f7f7f"}


def exportar_dot(G, ruta_salida):
    """Las transferencias van gruesas y rojas: son las que cruzan contenedores
    y las unicas que se pueden bloquear. Se renderiza con graphviz o pegandolo
    en dreampuf.github.io/GraphvizOnline."""
    final = nodo_decisivo(G)
    ancestros = (nx.ancestors(G, final) | {final}) if final else set(G.nodes)

    L = ["digraph mapa {", "  rankdir=BT;",
         '  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=10];',
         '  edge [fontname="Helvetica" fontsize=8];']

    for ag in sorted({G.nodes[n]["agent_id"] for n in ancestros}):
        L.append(f"  subgraph cluster_{ag} {{")
        L.append(f'    label="contenedor {ag}"; style=dashed; color="#999999";')
        for n in sorted(ancestros):
            if G.nodes[n]["agent_id"] != ag:
                continue
            a = G.nodes[n]
            txt = str(a.get("content", ""))[:24].replace('"', "'")
            etiqueta = f'{a.get("type","?")}\n{txt}'
            borde = ' penwidth=3 color="#000000"' if n == final else ""
            L.append(f'    "{n}" [label="{etiqueta}" fillcolor="{COLOR.get(ag,"#888888")}22"{borde}];')
        L.append("  }")

    for u, v, d in G.edges(data=True):
        if u not in ancestros or v not in ancestros:
            continue
        if d["kind"] == "transfiere":
            L.append(f'  "{u}" -> "{v}" [color="#d62728" penwidth=2.5 label="canal"];')
        else:
            L.append(f'  "{u}" -> "{v}" [color="#999999"];')

    L.append("}")
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return str(ruta_salida)


def main(argv=None):
    """    python -m hormiguero.grafo.exportar logs/ep_x.jsonl --salida mapa.dot"""
    import argparse
    from .modelo import cargar
    ap = argparse.ArgumentParser(prog="hormiguero.grafo.exportar")
    ap.add_argument("rutas", nargs="+", help="log de UN episodio")
    ap.add_argument("--salida", default="mapa.dot")
    a = ap.parse_args(argv)
    print(exportar_dot(cargar(*a.rutas), a.salida))


if __name__ == "__main__":
    main()
