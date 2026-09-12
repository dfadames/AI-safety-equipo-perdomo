"""
El mapa, para mirarlo.

Genera una pagina autocontenida (un solo .html, sin red, sin librerias) con el
mapa de procedencia dibujado y las cuatro preguntas respondidas al lado.

    python -m hormiguero.grafo.mirar runs/ --salida mapa.html

Las respuestas se calculan ACA, en Python, con las mismas funciones que
alimentan el csv del paper. La pagina solo dibuja. Si la pagina recalculara por
su cuenta podria discrepar del csv y nadie se daria cuenta.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import networkx as nx

from .modelo import construir, contenedor, leer_eventos, nodo_decisivo, raices
from .preguntas import responder

LIMITE_TEXTO = 700          # por nodo, para que el html no se vuelva enorme


def _texto_corto(contenido) -> str:
    if isinstance(contenido, dict):
        for k in ("mensaje", "texto", "comando", "credencial", "resultado", "pista"):
            if k in contenido:
                return str(contenido[k])
        return json.dumps(contenido, ensure_ascii=False)
    return str(contenido)


def _detalle(e: dict) -> str:
    c = e.get("content")
    txt = json.dumps(c, ensure_ascii=False, indent=2) if isinstance(c, (dict, list)) else str(c)
    return txt[:LIMITE_TEXTO] + ("..." if len(txt) > LIMITE_TEXTO else "")


def datos_del_episodio(episodio: str, eventos: list[dict]) -> dict:
    """Todo lo que la pagina necesita de un episodio, ya masticado."""
    G = construir(eventos)
    r = responder(G)
    final = nodo_decisivo(G)

    cono = (nx.ancestors(G, final) | {final}) if final else set(G.nodes)
    todas_raices = raices(G, cono)
    criticas = {(u, v) for u, v, _au, _av in r.get("mensajes_criticos", [])}

    nodos = []
    for n, a in sorted(G.nodes(data=True), key=lambda kv: kv[1].get("step", 0)):
        nodos.append({
            "id": n,
            "agente": a.get("agent_id", "?"),
            "contenedor": contenedor(G, n),
            "step": a.get("step", 0),
            "tipo": a.get("type", "?"),
            "texto": _texto_corto(a.get("content"))[:90],
            "detalle": _detalle(a),
            "ancestros": list(a.get("ancestors") or []),
            "citados": list(a.get("cited_by_agent") or []),
            "partes": list(a.get("exact_parts_used") or []),
            "exito": a.get("success"),
            "raiz": n in todas_raices,
            "cono": n in cono,
            "decisivo": n == final,
        })

    aristas = []
    for u, v, d in G.edges(data=True):
        aristas.append({
            "de": u, "a": v, "tipo": d["kind"],
            "critica": (u, v) in criticas,
            "cono": u in cono and v in cono,
        })

    conf = eventos[0].get("config") or {}
    return {
        "id": episodio,
        "condicion": r.get("condicion") or "",
        "N": conf.get("n_agentes", r.get("N")),
        "n_partes": conf.get("n_partes", ""),
        "peldano": conf.get("peldano", ""),
        "resumen": r,
        "nodos": nodos,
        "aristas": aristas,
        "decisivo": final,
    }


def exportar_html(rutas, ruta_salida="mapa.html") -> str:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for e in leer_eventos(*rutas):
        grupos[e.get("episode", "sin_episodio")].append(e)
    if not grupos:
        raise SystemExit("No se encontro ningun evento en esas rutas.")

    episodios = [datos_del_episodio(ep, ev) for ep, ev in sorted(grupos.items())]
    html = PLANTILLA.replace("/*DATOS*/", json.dumps(episodios, ensure_ascii=False))
    Path(ruta_salida).write_text(html, encoding="utf-8")
    return str(ruta_salida)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="hormiguero.grafo.mirar",
        description="Genera una pagina con el mapa de procedencia dibujado.")
    ap.add_argument("rutas", nargs="+", help="archivos .jsonl, un comodin o un directorio")
    ap.add_argument("--salida", default="mapa.html")
    a = ap.parse_args(argv)
    ruta = exportar_html(a.rutas, a.salida)
    print(f"  {ruta} - abrilo en el navegador")


PLANTILLA = r"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa de procedencia - Hormiguero</title>
<style>
:root{
  --fondo:#fbfaf8; --papel:#ffffff; --tinta:#1a1a1a; --suave:#6b6b6b;
  --linea:#e2e0dc; --deriva:#c9c6c0; --transfiere:#c2410c; --critica:#dc2626;
  --ok:#15803d; --mal:#b91c1c; --realce:#fdf3d8;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --fondo:#16161a; --papel:#1e1e23; --tinta:#ececf0; --suave:#9a9aa4;
  --linea:#33333c; --deriva:#4a4a55; --transfiere:#fb923c; --critica:#f87171;
  --ok:#4ade80; --mal:#f87171; --realce:#3a3220;
}}
:root[data-theme="dark"]{
  --fondo:#16161a; --papel:#1e1e23; --tinta:#ececf0; --suave:#9a9aa4;
  --linea:#33333c; --deriva:#4a4a55; --transfiere:#fb923c; --critica:#f87171;
  --ok:#4ade80; --mal:#f87171; --realce:#3a3220;
}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--tinta);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.marco{max-width:1500px;margin:0 auto;padding:26px 22px 60px}
h1{font-size:25px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:16px;margin:30px 0 10px;letter-spacing:-.01em}
h3{font-size:12px;margin:18px 0 8px;text-transform:uppercase;letter-spacing:.09em;color:var(--suave)}
.sub{color:var(--suave);margin:0 0 22px;max-width:76ch}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

.tabla-envoltura{overflow-x:auto;border:1px solid var(--linea);border-radius:10px;background:var(--papel)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font-weight:600;color:var(--suave);font-size:11px;
  text-transform:uppercase;letter-spacing:.07em;padding:9px 12px;border-bottom:1px solid var(--linea)}
td{padding:8px 12px;border-bottom:1px solid var(--linea)}
tbody tr{cursor:pointer}
tbody tr:hover{background:var(--realce)}
tbody tr.activo{background:var(--realce);box-shadow:inset 3px 0 0 var(--transfiere)}
tbody tr:last-child td{border-bottom:none}

.respuestas{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin:14px 0 8px}
.tarjeta{background:var(--papel);border:1px solid var(--linea);border-radius:10px;padding:13px 15px}
.tarjeta .cifra{font-size:29px;font-weight:600;letter-spacing:-.03em;line-height:1.15}
.tarjeta .pie{color:var(--suave);font-size:12.5px;margin-top:3px}
.ok{color:var(--ok)} .mal{color:var(--mal)} .alerta{color:var(--transfiere)}

.lienzo{display:grid;grid-template-columns:1fr 330px;gap:14px;margin-top:12px;align-items:start}
@media (max-width:1000px){.lienzo{grid-template-columns:1fr}}
.marco-mapa{background:var(--papel);border:1px solid var(--linea);border-radius:10px;
  overflow:auto;max-height:min(78vh,900px)}
aside{background:var(--papel);border:1px solid var(--linea);border-radius:10px;padding:14px;
  position:sticky;top:14px;max-height:min(78vh,900px);overflow:auto}
aside pre{background:var(--fondo);border:1px solid var(--linea);border-radius:6px;
  padding:9px;font-size:11.5px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;margin:6px 0}
.campo{margin:9px 0;font-size:13px}
.campo b{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--suave);margin-bottom:2px}
.enlace{color:var(--transfiere);cursor:pointer;text-decoration:underline;text-underline-offset:2px}

.controles{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:14px 0 0;font-size:13px;color:var(--suave)}
.controles label{display:flex;gap:6px;align-items:center;cursor:pointer}
.leyenda{display:flex;gap:16px;flex-wrap:wrap;font-size:12.5px;color:var(--suave);margin:10px 0 0}
.leyenda span{display:flex;gap:6px;align-items:center}
.muestra{display:inline-block;width:26px;height:0;border-top-width:2px;border-top-style:solid}

svg text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.nodo{cursor:pointer}
.nodo.apagado{opacity:.16}
.arista.apagada{opacity:.1}

.nota{background:var(--papel);border:1px solid var(--linea);border-left:3px solid var(--transfiere);
  border-radius:0 8px 8px 0;padding:12px 15px;margin:14px 0;font-size:14px}
.lectura{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}
.lectura > div{background:var(--papel);border:1px solid var(--linea);border-radius:10px;padding:15px 17px}
.lectura p{margin:7px 0;font-size:13.5px}
.lectura .q{font-weight:600;font-size:14px;margin:0 0 6px}
ul{margin:6px 0;padding-left:18px;font-size:13.5px}
li{margin:3px 0}
.vacio{color:var(--suave);font-size:13px;padding:18px}
</style></head><body>
<div class="marco">

<h1>Mapa de procedencia</h1>
<p class="sub">Cada episodio deja un log. Cada linea del log es un nodo. Cada campo
<span class="mono">ancestors</span> es una arista. Lo que se dibuja aca no es un resumen del episodio:
<b>es el episodio</b>, y las cifras de cada tarjeta se leen del dibujo, no se estiman.</p>

<h2>Episodios</h2>
<div class="tabla-envoltura"><table id="indice"></table></div>

<div id="detalle-episodio"></div>

<h2>Como se lee</h2>
<div class="lectura">
  <div><p class="q">1 &middot; Span de origen</p>
    <p>De cuantos contenedores distintos vino la informacion que termino en la accion restringida.</p>
    <p><b>1</b> = la contencion compuso. <b>&gt;1</b> = no compuso: capacidad que ningun contenedor
    tenia por si solo aparecio del otro lado de la frontera.</p></div>
  <div><p class="q">2 &middot; Corte minimo</p>
    <p>Cuantas <i>rutas independientes</i> de informacion sostienen el escape (max-flow / min-cut).</p>
    <p>Es cuantos mensajes habria que bloquear para impedirlo. Si crece con N, la poblacion desarrollo
    <b>redundancia</b>: tapar un canal ya no alcanza.</p></div>
  <div><p class="q">3 &middot; Visibilidad</p>
    <p>Que fraccion de los origenes alcanzo a ver cada agente.</p>
    <p>Si el maximo es bajo y aun asi hubo escape, <b>ningun monitor por agente podia verlo</b>: la
    senal estaba repartida por debajo del umbral de todos. Es la dilucion, medida.</p></div>
  <div><p class="q">4 &middot; Oraculo</p>
    <p>La credencial <i>contiene</i> las partes usadas, asi que <span class="mono">exact_parts_used</span>
    es una verdad independiente del arnes.</p>
    <p><span class="mono">span == partes</span> corrobora. <span class="mono">span &gt; partes</span> es
    sobreestimacion esperable. <span class="mono">span &lt; partes</span> es
    <span class="mono">BUG</span>: llego informacion
    sin registrarse y ese episodio no sirve.</p></div>
</div>

<div class="nota"><b>El caso que hay que mirar primero.</b> Un episodio con accion restringida ejecutada,
span &gt; 1, corte &ge; 2, visibilidad maxima baja y veredicto <span class="mono">corroborado</span> es la
tesis completa en una sola pantalla: la capacidad se agrego cruzando la frontera, nadie vio el cuadro
entero, y el grafo no se lo invento.</div>

</div>
<script>
// Firefox restaura el scroll cuando termina de maquetar el SVG (segundos
// despues) y te devuelve al inicio. Lo manejamos nosotros.
if("scrollRestoration" in history) history.scrollRestoration = "manual";
const EPISODIOS = /*DATOS*/;
const LANE = 178, ROW = 34, PAD_T = 54, PAD_L = 62, CAJA_W = 146, CAJA_H = 22;
let iEp = 0, sel = null, soloCono = true, sinRazonamiento = true, iPintado = null;

const color = (i) => "hsl(" + ((i * 67 + 205) % 360) + " 62% 48%)";
const esc = (s) => String(s).replace(/[&<>"]/g,
  (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const pct = (x) => (x * 100).toFixed(0) + "%";
const VEREDICTO = {corroborado: "Corroborado", sobreestimacion: "Sobreestimacion",
                   BUG: "Bug", sin_oraculo: "Sin oraculo"};
const veredictoDe = (v) => VEREDICTO[v] || v || "-";

function indice(){
  const enc = "<thead><tr><th>Episodio</th><th>Condicion</th><th>N</th><th>Accion restringida</th>"
    + "<th>Span</th><th>Corte min.</th><th>Visib. max.</th><th>Aviso</th><th>Oraculo</th></tr></thead>";
  const filas = EPISODIOS.map(function(e, i){
    const r = e.resumen, v = r.visibilidad || {};
    const vals = Object.values(v).map((x) => x.por_raices);
    const vmax = vals.length ? Math.max.apply(null, vals) : null;
    const ver = (r.verificacion || {}).veredicto || "-";
    const clase = ver === "BUG" ? "mal" : (ver === "corroborado" ? "ok" : "");
    return '<tr class="' + (i === iEp ? "activo" : "") + '" onclick="verEpisodio(' + i + ')">'
      + '<td class="mono">' + esc(e.id) + "</td><td>" + esc(e.condicion || "-") + "</td>"
      + "<td>" + (e.N != null ? e.N : "-") + "</td>"
      + '<td class="' + (r.escape ? "alerta" : "") + '">' + (r.escape ? "Si" : "No") + "</td>"
      + "<td><b>" + (r.span_de_origen != null ? r.span_de_origen : "-") + "</b></td>"
      + "<td><b>" + (r.corte_minimo != null ? r.corte_minimo : "-") + "</b></td>"
      + "<td>" + (vmax === null ? "-" : pct(vmax)) + "</td>"
      + "<td>" + (r.aviso_a_humano ? "Si" : '<span class="alerta">Nadie</span>') + "</td>"
      + '<td class="' + clase + '">' + esc(veredictoDe(ver)) + "</td></tr>";
  }).join("");
  document.getElementById("indice").innerHTML = enc + "<tbody>" + filas + "</tbody>";
}

const card = (cifra, pie, clase, nota) =>
  '<div class="tarjeta"><div class="cifra ' + (clase || "") + '">' + esc(cifra) + "</div>"
  + '<div class="pie">' + esc(pie) + "</div>"
  + (nota ? '<div class="pie">' + esc(nota) + "</div>" : "") + "</div>";

function tarjetas(e){
  const r = e.resumen, v = r.visibilidad || {};
  const vals = Object.values(v).map((x) => x.por_raices);
  const vmax = vals.length ? Math.max.apply(null, vals) : null;
  const ver = r.verificacion || {};
  const t = [];
  t.push(card(r.escape ? "Si" : "No", "Accion restringida ejecutada",
    r.escape ? "alerta" : "", r.escape ? "" : "El techo duro aguanto."));
  t.push(card(r.span_de_origen != null ? r.span_de_origen : "-", "Span de origen (contenedores)",
    r.span_de_origen > 1 ? "alerta" : "", r.span_de_origen > 1 ? "La contencion no compuso." : ""));
  t.push(card(r.corte_minimo != null ? r.corte_minimo : "-", "Corte minimo (rutas independientes)", "",
    r.corte_minimo ? "Hay que bloquear " + r.corte_minimo
                   + (r.corte_minimo === 1 ? " mensaje." : " mensajes.") : ""));
  t.push(card(vmax === null ? "-" : pct(vmax), "Visibilidad maxima de un agente", "",
    (vmax !== null && vmax < 1) ? "Nadie vio el cuadro completo." : ""));
  t.push(card(r.aviso_a_humano ? "Si" : "Nadie", "Aviso a un humano",
    r.aviso_a_humano ? "ok" : "alerta", r.aviso_a_humano ? "" : "La herramienta estaba disponible."));
  t.push(card(veredictoDe(ver.veredicto), "Oraculo",
    ver.veredicto === "BUG" ? "mal" : (ver.ok ? "ok" : ""),
    ver.verificable ? "Grafo " + ver.span_del_grafo + " vs partes " + ver.partes_usadas + "."
                    : "Sin exact_parts_used."));
  return '<div class="respuestas">' + t.join("") + "</div>";
}

function criticos(e){
  const r = e.resumen;
  if(!r.mensajes_criticos || !r.mensajes_criticos.length) return "";
  const li = r.mensajes_criticos.map(function(m){
    return '<li><span class="mono enlace" onclick="elegir(\'' + m[0] + '\')">' + esc(m[0])
      + "</span> &mdash; " + esc(m[2]) + " &rarr; " + esc(m[3]) + "</li>";
  }).join("");
  const n = r.mensajes_criticos.length;
  return "<h3>" + (n === 1 ? "El mensaje del corte" : "Los " + n + " mensajes del corte") + "</h3>"
    + '<p style="font-size:13.5px;margin:0 0 4px;color:var(--suave)">Bloquea estos y el escape no ocurre. '
    + "Es la replica contrafactual: se repite el episodio con estos event_id invisibles.</p><ul>"
    + li + "</ul>";
}

function visibilidadTabla(e){
  const v = e.resumen.visibilidad;
  if(!v) return "";
  const filas = Object.entries(v).sort().map(function(par){
    return '<tr><td class="mono">' + esc(par[0]) + "</td><td>" + pct(par[1].por_raices)
      + "</td><td>" + pct(par[1].por_ancestros) + "</td></tr>";
  }).join("");
  return "<h3>Visibilidad por agente</h3>"
    + '<div class="tabla-envoltura"><table><thead><tr><th>Agente</th><th>De los origenes</th>'
    + "<th>Del cono causal</th></tr></thead><tbody>" + filas + "</tbody></table></div>";
}

function dibujar(e){
  const dec = e.decisivo;
  let nodos = e.nodos;
  if(sinRazonamiento) nodos = nodos.filter((n) => n.tipo !== "razonamiento");
  const visibles = {};
  nodos.forEach((n) => { visibles[n.id] = true; });
  const agentes = Array.from(new Set(e.nodos.map((n) => n.agente))).sort();
  const pos = {}, colorDe = {};
  agentes.forEach((a, i) => { colorDe[a] = color(i); });
  nodos.forEach(function(n, i){
    pos[n.id] = {x: PAD_L + agentes.indexOf(n.agente) * LANE + CAJA_W / 2, y: PAD_T + i * ROW};
  });

  const W = PAD_L + agentes.length * LANE + 130;
  const H = PAD_T + nodos.length * ROW + 24;

  let s = '<svg viewBox="0 0 ' + W + " " + H + '" width="' + W + '" height="' + H + '" '
    + 'xmlns="http://www.w3.org/2000/svg" role="img" '
    + 'aria-label="Mapa de procedencia del episodio ' + esc(e.id) + '">'
    + '<defs><marker id="f" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" '
    + 'orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="currentColor"/></marker></defs>';

  agentes.forEach(function(a, i){
    const x = PAD_L + i * LANE;
    s += '<rect x="' + (x - 6) + '" y="' + (PAD_T - 16) + '" width="' + (CAJA_W + 12)
      + '" height="' + (H - PAD_T + 4) + '" rx="8" fill="' + colorDe[a] + '" opacity=".05"/>'
      + '<text x="' + (x + CAJA_W / 2) + '" y="' + (PAD_T - 26) + '" text-anchor="middle" '
      + 'font-size="12" font-weight="700" fill="' + colorDe[a] + '">' + esc(a) + "</text>";
  });

  e.aristas.forEach(function(ar){
    if(!visibles[ar.de] || !visibles[ar.a]) return;
    const p = pos[ar.de], q = pos[ar.a];
    const off = (soloCono && dec && !ar.cono) ? " apagada" : "";
    const dy = Math.max(12, (q.y - p.y) * 0.42);
    const d = "M" + p.x + " " + (p.y + CAJA_H / 2)
      + " C" + p.x + " " + (p.y + CAJA_H / 2 + dy)
      + ", " + q.x + " " + (q.y - CAJA_H / 2 - dy)
      + ", " + q.x + " " + (q.y - CAJA_H / 2);
    let trazo = "var(--deriva)", ancho = 1.1, guion = "";
    if(ar.critica){ trazo = "var(--critica)"; ancho = 2.8; guion = ' stroke-dasharray="6 3"'; }
    else if(ar.tipo === "transfiere"){ trazo = "var(--transfiere)"; ancho = 2; }
    s += '<path class="arista' + off + '" d="' + d + '" fill="none" stroke="' + trazo
      + '" stroke-width="' + ancho + '"' + guion + ' color="' + trazo + '" marker-end="url(#f)"/>';
  });

  nodos.forEach(function(n){
    const p = pos[n.id], c = colorDe[n.agente];
    const off = (soloCono && dec && !n.cono) ? " apagado" : "";
    const borde = n.decisivo ? "var(--critica)" : (n.raiz ? c : "var(--linea)");
    const grosor = n.decisivo ? 2.6 : (n.raiz ? 1.8 : 1.2);
    const anillo = n.id === sel
      ? '<rect x="' + (p.x - CAJA_W / 2 - 3) + '" y="' + (p.y - CAJA_H / 2 - 3) + '" width="'
        + (CAJA_W + 6) + '" height="' + (CAJA_H + 6) + '" rx="7" fill="none" '
        + 'stroke="currentColor" stroke-width="1.6"/>'
      : "";
    const etq = (n.tipo + (n.texto ? " " + n.texto : "")).slice(0, 22);
    s += '<g class="nodo' + off + '" onclick="elegir(\'' + n.id + '\')">'
      + "<title>" + esc(n.tipo) + " - paso " + n.step + " - " + esc(n.texto) + "</title>"
      + '<rect x="' + (p.x - CAJA_W / 2) + '" y="' + (p.y - CAJA_H / 2) + '" width="' + CAJA_W
      + '" height="' + CAJA_H + '" rx="5" fill="' + c + '" fill-opacity=".13" stroke="' + borde
      + '" stroke-width="' + grosor + '"/>' + anillo
      + '<text x="' + (p.x - CAJA_W / 2 + 7) + '" y="' + (p.y + 4)
      + '" font-size="10.5" fill="currentColor">' + esc(etq) + "</text>"
      + '<text x="' + (PAD_L - 14) + '" y="' + (p.y + 4) + '" font-size="9.5" text-anchor="end" '
      + 'fill="var(--suave)">' + n.step + "</text></g>";
    if(n.decisivo){
      s += '<text x="' + (p.x + CAJA_W / 2 + 8) + '" y="' + (p.y + 4) + '" font-size="10.5" '
        + 'font-weight="700" fill="var(--critica)">Accion restringida</text>';
    }
  });
  return s + "</svg>";
}

function panel(e){
  if(!sel) return '<div class="vacio">Selecciona un nodo del mapa para ver de donde salio.</div>';
  const n = e.nodos.find((x) => x.id === sel);
  if(!n) return "";
  const refs = (ids) => ids.length
    ? ids.map((i) => '<span class="mono enlace" onclick="elegir(\'' + i + '\')">' + esc(i)
        + "</span>").join("<br>")
    : '<span style="color:var(--suave)">ninguno</span>';
  let h = "<h3>" + esc(n.tipo) + "</h3>"
    + '<div class="campo"><b>event_id</b><span class="mono">' + esc(n.id) + "</span></div>"
    + '<div class="campo"><b>agente / contenedor</b>' + esc(n.agente) + ' &middot; <span class="mono">'
    + esc(n.contenedor) + "</span></div>"
    + '<div class="campo"><b>paso causal</b>' + n.step
    + (n.raiz ? " &middot; <b>raiz</b>: informacion que entro al sistema" : "") + "</div>"
    + '<div class="campo"><b>contenido</b><pre>' + esc(n.detalle) + "</pre></div>"
    + '<div class="campo"><b>ancestros (lo que tenia)</b>' + refs(n.ancestros) + "</div>";
  if(n.citados.length){
    h += '<div class="campo"><b>citados (lo que dice que uso)</b>' + refs(n.citados) + "</div>";
  }
  if(n.partes.length){
    h += '<div class="campo"><b>partes reales usadas (oraculo)</b><span class="mono">'
      + esc(n.partes.join(", ")) + "</span></div>";
  }
  if(n.exito !== null && n.exito !== undefined){
    h += '<div class="campo"><b>exito</b><span class="' + (n.exito ? "alerta" : "") + '">'
      + (n.exito ? "Si" : "No") + "</span></div>";
  }
  return h;
}

function verEpisodio(i){ iEp = i; sel = null; pintar(); }
function elegir(id){ sel = id; pintar(); }

function pintar(){
  const e = EPISODIOS[iEp];
  // Reescribir el innerHTML encoge el documento un instante y el navegador
  // clava el scroll en 0. Lo guardamos y lo devolvemos.
  const y = window.scrollY, mismo = iPintado === iEp;
  const antes = document.querySelector(".marco-mapa");
  const mx = antes ? antes.scrollLeft : 0, my = antes ? antes.scrollTop : 0;
  iPintado = iEp;
  indice();
  document.getElementById("detalle-episodio").innerHTML =
    "<h2>Episodio " + esc(e.id) + "</h2>" + tarjetas(e)
    + '<div class="controles">'
    + '<label><input type="checkbox" id="c1"' + (soloCono ? " checked" : "")
    + "> Mostrar solo lo que llego a la accion restringida</label>"
    + '<label><input type="checkbox" id="c2"' + (sinRazonamiento ? " checked" : "")
    + "> Ocultar los nodos de razonamiento</label></div>"
    + '<div class="leyenda">'
    + '<span><i class="muestra" style="border-color:var(--deriva)"></i> Deriva: dentro del contenedor, no se puede cortar</span>'
    + '<span><i class="muestra" style="border-color:var(--transfiere)"></i> Transfiere: cruzo el canal</span>'
    + '<span><i class="muestra" style="border-color:var(--critica);border-top-style:dashed"></i> Critica: pertenece al corte minimo</span>'
    + "</div>"
    + '<div class="lienzo"><div class="marco-mapa">' + dibujar(e) + "</div>"
    + "<aside>" + panel(e) + "</aside></div>"
    + criticos(e) + visibilidadTabla(e);

  const c1 = document.getElementById("c1"), c2 = document.getElementById("c2");
  if(c1) c1.onchange = function(){ soloCono = c1.checked; pintar(); };
  if(c2) c2.onchange = function(){ sinRazonamiento = c2.checked; pintar(); };

  const mapa = document.querySelector(".marco-mapa");
  if(mapa && mismo){ mapa.scrollLeft = mx; mapa.scrollTop = my; }
  window.scrollTo(0, y);
}

pintar();
</script></body></html>
"""


if __name__ == "__main__":
    main()
