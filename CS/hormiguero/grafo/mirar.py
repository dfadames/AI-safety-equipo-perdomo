"""
El mapa, para mirarlo.

Genera una pagina autocontenida (un solo .html, sin red, sin librerias) con el
mapa de procedencia dibujado y las cuatro preguntas respondidas al lado.

    python -m hormiguero.grafo.mirar runs/ --salida mapa.html

Las respuestas se calculan ACA, en Python, con las mismas funciones que
alimentan el csv del paper. La pagina solo dibuja. Si la pagina recalculara por
su cuenta podria discrepar del csv y nadie se daria cuenta.

La pagina que sale de aca trae:

  * Tabla de episodios con scroll propio, encabezado fijo y orden por columna.
  * Filtros: texto libre, condicion, accion restringida, oraculo y aviso.
  * Grafo con zoom (rueda, botones, pellizco) y paneo por arrastre, minimapa
    navegable, nombres de contenedor y regla de pasos que se quedan pegados a
    los bordes al desplazarse, cadena causal iluminada al pasar el cursor,
    busqueda de nodos y panel lateral con la procedencia del nodo elegido.
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
    # La misma agrupacion que el csv: dos corridas distintas pueden traer el
    # mismo `episode` (semilla fija), y fundirlas produce ciclos en el grafo.
    # Agrupar aca por separado hacia que la pagina se saltara esos episodios
    # mientras el csv si los mostraba.
    from .agregar import por_episodio
    grupos = por_episodio(*rutas)
    if not grupos:
        raise SystemExit("No se encontro ningun evento en esas rutas.")

    episodios = []
    for ep, ev in sorted(grupos.items()):
        try:
            episodios.append(datos_del_episodio(ep, ev))
        except (ValueError, KeyError) as exc:
            print(f"  aviso: se salta '{ep}' en el mapa: {exc}")

    # Un `</` dentro del JSON cerraria el <script> y romperia la pagina.
    # `\/` es un escape valido de JSON, asi que se puede reemplazar sin perder
    # nada (los textos de comandos pueden traer `</...>`).
    datos = json.dumps(episodios, ensure_ascii=False).replace("</", "<\\/")
    Path(ruta_salida).write_text(PLANTILLA.replace("/*DATOS*/", datos), encoding="utf-8")
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
  --ok:#15803d; --mal:#b91c1c; --realce:#fdf3d8; --acento:#2f6db8;
  --sombra:0 1px 2px rgba(25,25,20,.04), 0 6px 20px rgba(25,25,20,.05);
  color-scheme:light;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --fondo:#16161a; --papel:#1e1e23; --tinta:#ececf0; --suave:#9a9aa4;
  --linea:#33333c; --deriva:#4a4a55; --transfiere:#fb923c; --critica:#f87171;
  --ok:#4ade80; --mal:#f87171; --realce:#3a3220; --acento:#7fb0e8;
  --sombra:0 1px 2px rgba(0,0,0,.25), 0 8px 24px rgba(0,0,0,.3);
  color-scheme:dark;
}}
:root[data-theme="dark"]{
  --fondo:#16161a; --papel:#1e1e23; --tinta:#ececf0; --suave:#9a9aa4;
  --linea:#33333c; --deriva:#4a4a55; --transfiere:#fb923c; --critica:#f87171;
  --ok:#4ade80; --mal:#f87171; --realce:#3a3220; --acento:#7fb0e8;
  --sombra:0 1px 2px rgba(0,0,0,.25), 0 8px 24px rgba(0,0,0,.3);
  color-scheme:dark;
}
*{box-sizing:border-box;scrollbar-width:thin;scrollbar-color:var(--deriva) transparent}
body{margin:0;background:var(--fondo);color:var(--tinta);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.marco{max-width:1560px;margin:0 auto;padding:26px 22px 70px}
h1{font-size:25px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:16px;margin:34px 0 10px;letter-spacing:-.01em}
h3{font-size:12px;margin:18px 0 8px;text-transform:uppercase;letter-spacing:.09em;color:var(--suave)}
.sub{color:var(--suave);margin:0;max-width:78ch}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.muted{color:var(--suave);font-size:13px}
button{font:inherit;color:inherit}
.btn{background:var(--papel);border:1px solid var(--linea);border-radius:8px;
  padding:6px 12px;cursor:pointer;font-size:13px}
.btn:hover{background:var(--realce);border-color:var(--deriva)}
:focus-visible{outline:2px solid var(--acento);outline-offset:2px}
#detalle-episodio{scroll-margin-top:12px}

.cabecera{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;margin-bottom:18px}
.fila-titulo{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}
.fila-titulo h2{margin:26px 0 8px}

.barra-filtros{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 10px}
.barra-filtros input[type=search]{flex:1 1 230px;min-width:170px;background:var(--papel);
  border:1px solid var(--linea);border-radius:8px;padding:7px 11px;font-size:13.5px;color:var(--tinta)}
.barra-filtros select{background:var(--papel);border:1px solid var(--linea);border-radius:8px;
  padding:7px 8px;font-size:13px;color:var(--tinta);cursor:pointer;max-width:100%}
.barra-filtros input:focus,.barra-filtros select:focus{border-color:var(--acento);outline:none;
  box-shadow:0 0 0 3px rgba(47,109,184,.18)}
#f-cuenta{margin-left:auto}

.tabla-scroll{overflow:auto;max-height:min(48vh,460px);border:1px solid var(--linea);
  border-radius:10px;background:var(--papel);box-shadow:var(--sombra)}
.tabla-scroll.baja{max-height:320px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:13.5px}
th{position:sticky;top:0;z-index:2;background:var(--papel);text-align:left;font-weight:600;
  color:var(--suave);font-size:11px;text-transform:uppercase;letter-spacing:.07em;
  padding:9px 12px;border-bottom:1px solid var(--linea);white-space:nowrap}
th[data-col]{cursor:pointer;user-select:none}
th[data-col]:hover{color:var(--tinta)}
th.ord-asc::after{content:" \25B4";font-size:9px;color:var(--transfiere)}
th.ord-desc::after{content:" \25BE";font-size:9px;color:var(--transfiere)}
td{padding:8px 12px;border-bottom:1px solid var(--linea);white-space:nowrap}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
tbody tr{cursor:pointer}
tbody tr:not(.vacia):hover td{background:var(--realce)}
tbody tr.activo td{background:var(--realce)}
tbody tr.activo td:first-child{box-shadow:inset 3px 0 0 var(--transfiere)}
tbody tr:last-child td{border-bottom:none}
tr.vacia td{cursor:default;text-align:center;color:var(--suave);padding:22px}

.respuestas{display:grid;grid-template-columns:repeat(auto-fit,minmax(205px,1fr));gap:12px;margin:16px 0 4px}
.tarjeta{background:var(--papel);border:1px solid var(--linea);border-radius:10px;
  padding:13px 15px;box-shadow:var(--sombra)}
.tarjeta .cifra{font-size:28px;font-weight:600;letter-spacing:-.03em;line-height:1.15;
  font-variant-numeric:tabular-nums}
.tarjeta .pie{color:var(--suave);font-size:12.5px;margin-top:3px}
.ok{color:var(--ok)} .mal{color:var(--mal)} .alerta{color:var(--transfiere)}

.cab-episodio{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px;margin:32px 0 4px}
.cab-episodio h2{margin:0}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font-size:11.5px;color:var(--suave);border:1px solid var(--linea);border-radius:99px;
  padding:2px 9px;background:var(--papel);white-space:nowrap}
.chip.roja{color:var(--critica);border-color:var(--critica)}

.controles{display:flex;flex-wrap:wrap;gap:10px 20px;align-items:center;
  margin:18px 0 12px;font-size:13.5px;color:var(--tinta)}
.int{display:flex;gap:7px;align-items:center;cursor:pointer;user-select:none}
.int input{accent-color:var(--transfiere);width:15px;height:15px;cursor:pointer;margin:0}
#q-nodo{flex:1 1 240px;max-width:400px;min-width:170px;background:var(--papel);
  border:1px solid var(--linea);border-radius:8px;padding:7px 11px;font-size:13px;color:var(--tinta)}
#q-nodo:focus{border-color:var(--acento);outline:none;box-shadow:0 0 0 3px rgba(47,109,184,.18)}

.lienzo{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px;align-items:stretch}
@media (max-width:1080px){.lienzo{grid-template-columns:1fr}}
.marco-mapa{position:relative;background:var(--papel);border:1px solid var(--linea);
  border-radius:12px;overflow:hidden;height:clamp(430px,72vh,880px);
  box-shadow:var(--sombra);touch-action:none}
#svg{position:absolute;inset:0;width:100%;height:100%;display:block;cursor:grab;touch-action:none}
.marco-mapa.agarrando #svg{cursor:grabbing}
.barra-zoom{position:absolute;top:10px;right:10px;z-index:6;display:flex;gap:2px;align-items:center;
  background:var(--papel);border:1px solid var(--linea);border-radius:9px;padding:3px;
  box-shadow:var(--sombra)}
.barra-zoom button{border:none;background:transparent;border-radius:6px;width:28px;height:26px;
  cursor:pointer;font-size:15px;line-height:1;color:var(--tinta)}
.barra-zoom button:hover{background:var(--realce)}
.barra-zoom #z-ajustar{width:auto;padding:0 9px;font-size:12px}
#z-nivel{font-size:11.5px;color:var(--suave);min-width:42px;text-align:center;
  font-variant-numeric:tabular-nums}
.mini{position:absolute;left:10px;bottom:10px;z-index:6;background:var(--papel);
  border:1px solid var(--linea);border-radius:9px;padding:6px;box-shadow:var(--sombra);
  opacity:.95;transition:opacity .15s}
.mini:hover{opacity:1}
#mini-svg{display:block;cursor:pointer;touch-action:none}
@media (max-width:760px){.mini{display:none}}

aside{background:var(--papel);border:1px solid var(--linea);border-radius:12px;
  padding:14px 16px;overflow:auto;min-height:0;box-shadow:var(--sombra)}
aside h3{margin:14px 0 8px}
aside > :first-child{margin-top:0}
.campo{margin:10px 0;font-size:13px}
.campo b{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--suave);margin-bottom:2px;font-weight:600}
aside pre{background:var(--fondo);border:1px solid var(--linea);border-radius:6px;padding:9px;
  font-size:11.5px;overflow-x:auto;white-space:pre-wrap;word-break:break-word;margin:4px 0}
.enlace{color:var(--transfiere);cursor:pointer;text-decoration:underline;text-underline-offset:2px}
.enlace:hover{opacity:.8}
.apagado{color:var(--suave)}
.vacio{color:var(--suave);font-size:13.5px;padding:14px 4px}
.vacio p{margin:0 0 8px}
.vacio .ayuda{font-size:12.5px;line-height:1.6;margin:0}
.cab-nodo{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:4px}
.cab-nodo h3{margin:0}
.acciones{margin-top:14px}

.pista{display:flex;flex-wrap:wrap;gap:8px 22px;align-items:center;justify-content:space-between;
  margin:10px 0 0;font-size:12.5px;color:var(--suave)}
.pista .leyenda{display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.muestra{display:inline-block;width:24px;height:0;border-top-width:2.5px;
  border-top-style:solid;border-radius:2px}
.muestra.discontinua{border-top-style:dashed}
.muestra.punto{width:8px;height:8px;border:none;border-radius:50%;background:var(--suave)}
.ayuda-mapa{margin-left:auto}

svg text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;user-select:none}
.nodo{cursor:pointer}
.nodo text{pointer-events:none}
.nodo,.arista,.paso{transition:opacity .12s linear}
.nodo.dim{opacity:.12}
.nodo.apagado{opacity:.16}
.arista.dim{opacity:.06}
.arista.apagada{opacity:.1}
.paso.dim{opacity:.15}
.paso.apagado{opacity:.2}
.nodo.hallado .caja{stroke:var(--tinta);stroke-width:2}
.velo{fill:var(--papel);opacity:.93;pointer-events:none}
.sticky,.paso-titulo,.anillo{pointer-events:none}
.cab,.paso,.paso-titulo,.dec{paint-order:stroke;stroke:var(--papel);stroke-width:3.5px;stroke-linejoin:round}
.cab{font-size:12px;font-weight:700}
.paso,.paso-titulo{font-size:9.5px;fill:var(--suave)}
.etq{font-size:10.5px;fill:var(--tinta)}
.dec{font-size:10.5px;font-weight:700;fill:var(--critica)}

.con-barra{display:flex;align-items:center;gap:8px}
.con-barra .valor{min-width:36px;font-variant-numeric:tabular-nums}
.barra{position:relative;flex:1;min-width:56px;max-width:130px;height:6px;border-radius:99px;
  background:var(--linea);overflow:hidden}
.barra i{position:absolute;top:0;left:0;bottom:0;border-radius:99px;
  background:var(--transfiere);opacity:.8}
.nota-corte{font-size:13px;color:var(--suave);margin:0 0 6px;max-width:75ch}
ul.criticos{margin:6px 0;padding-left:18px;font-size:13.5px}
ul.criticos li{margin:4px 0}

details.como{margin:36px 0 0;border:1px solid var(--linea);border-radius:10px;background:var(--papel)}
details.como summary{cursor:pointer;padding:13px 17px;font-size:14px;font-weight:600;
  list-style:none;display:flex;align-items:center;gap:9px;user-select:none}
details.como summary::-webkit-details-marker{display:none}
details.como summary::before{content:"\25B8";color:var(--suave);transition:transform .15s;display:inline-block}
details.como[open] summary::before{transform:rotate(90deg)}
.lectura{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;padding:14px}
.lectura > div{background:var(--fondo);border:1px solid var(--linea);border-radius:10px;padding:15px 17px}
.lectura p{margin:7px 0;font-size:13.5px}
.lectura .q{font-weight:600;font-size:14px;margin:0 0 6px}
.nota{background:var(--papel);border:1px solid var(--linea);border-left:3px solid var(--transfiere);
  border-radius:0 8px 8px 0;padding:12px 15px;margin:14px 0;font-size:14px}
@media (max-width:640px){.marco{padding:18px 12px 50px}h1{font-size:22px}}
</style></head><body>
<div class="marco">

<div class="cabecera">
  <div>
    <h1>Mapa de procedencia</h1>
    <p class="sub">Cada episodio deja un log. Cada linea del log es un nodo. Cada campo
    <span class="mono">ancestors</span> es una arista. Lo que se dibuja aca no es un resumen del episodio:
    <b>es el episodio</b>, y las cifras de cada tarjeta se leen del dibujo, no se estiman.</p>
  </div>
  <button id="tema" class="btn" type="button">Modo oscuro</button>
</div>

<div class="fila-titulo"><h2>Episodios</h2><span id="resumen-lista" class="muted"></span></div>

<div class="barra-filtros">
  <input type="search" id="f-q" placeholder="Buscar episodio o condicion..." aria-label="Buscar episodio">
  <select id="f-cond" aria-label="Filtrar por condicion"><option value="">Condicion: todas</option></select>
  <select id="f-accion" aria-label="Filtrar por accion restringida">
    <option value="">Accion: todas</option>
    <option value="si">Con accion restringida</option>
    <option value="no">Sin accion restringida</option>
  </select>
  <select id="f-oraculo" aria-label="Filtrar por oraculo"><option value="">Oraculo: todos</option></select>
  <select id="f-aviso" aria-label="Filtrar por aviso">
    <option value="">Aviso: todos</option>
    <option value="si">Avisaron a un humano</option>
    <option value="no">Nadie aviso</option>
  </select>
  <button id="f-limpiar" class="btn" type="button" hidden>Limpiar</button>
  <span id="f-cuenta" class="muted"></span>
</div>

<div class="tabla-scroll">
  <table id="indice">
    <thead><tr>
      <th data-col="ep">Episodio</th>
      <th data-col="cond">Condicion</th>
      <th data-col="n" class="num">N</th>
      <th data-col="accion">Accion restringida</th>
      <th data-col="span" class="num">Span</th>
      <th data-col="corte" class="num">Corte min.</th>
      <th data-col="visib" class="num">Visib. max.</th>
      <th data-col="aviso">Aviso</th>
      <th data-col="oraculo">Oraculo</th>
    </tr></thead>
    <tbody id="cuerpo-ep"></tbody>
  </table>
</div>

<div id="detalle-episodio"></div>

<details class="como" open>
<summary>Como se lee</summary>
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
</details>

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

// ---------- medidas del dibujo ----------
const LANE = 192, ROW = 36, PAD_T = 58, PAD_L = 64;
const CAJA_W = 158, CAJA_H = 24;

// ---------- estado ----------
let iEp = 0, sel = null, iPintado = null, saltar = false;
let soloCono = true, sinRazon = true, qNodo = "";
let orden = { col: null, dir: 1 };
const filtros = { q: "", cond: "", accion: "", oraculo: "", aviso: "" };
let G = null, anim = null, rafPend = null;
let puntas = null, arrastre = null, hoverId = null;

// ---------- utilidades ----------
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
  (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const pct = (x) => (x * 100).toFixed(0) + "%";
const VEREDICTO = {corroborado:"Corroborado", sobreestimacion:"Sobreestimacion",
                   BUG:"Bug", sin_oraculo:"Sin oraculo"};
const veredictoDe = (v) => VEREDICTO[v] || v || "-";
const color = (i) => "hsl(" + ((i * 67 + 205) % 360) + ",62%,48%)";

function colorTipo(t){
  let h = 0; const s = String(t);
  for(let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return "hsl(" + h + ",45%,52%)";
}
function vmaxDe(e){
  const v = (e.resumen || {}).visibilidad || {};
  const vals = Object.values(v).map((x) => typeof x === "number" ? x : (x.por_raices || 0));
  return vals.length ? Math.max.apply(null, vals) : null;
}
function veredictoDeEp(e){
  return ((e.resumen || {}).verificacion || {}).veredicto || "";
}

// ---------- tabla de episodios ----------
function valorCol(e, col){
  const r = e.resumen || {};
  switch(col){
    case "ep": return String(e.id || "").toLowerCase();
    case "cond": return String(e.condicion || "").toLowerCase();
    case "n": return e.N == null ? -1 : e.N;
    case "accion": return r.escape ? 1 : 0;
    case "span": return r.span_de_origen == null ? -1 : r.span_de_origen;
    case "corte": return r.corte_minimo == null ? -1 : r.corte_minimo;
    case "visib": return vmaxDe(e) == null ? -1 : vmaxDe(e);
    case "aviso": return r.aviso_a_humano ? 1 : 0;
    default: return veredictoDeEp(e);
  }
}

function pasaFiltros(e){
  const r = e.resumen || {};
  if(filtros.q){
    const q = filtros.q.toLowerCase();
    if(!((e.id + " " + (e.condicion || "")).toLowerCase().includes(q))) return false;
  }
  if(filtros.cond && (e.condicion || "") !== filtros.cond) return false;
  if(filtros.accion === "si" && !r.escape) return false;
  if(filtros.accion === "no" && r.escape) return false;
  if(filtros.oraculo){
    const v = veredictoDeEp(e);
    if(filtros.oraculo === "ninguno"){ if(v !== "") return false; }
    else if(v !== filtros.oraculo) return false;
  }
  if(filtros.aviso === "si" && !r.aviso_a_humano) return false;
  if(filtros.aviso === "no" && r.aviso_a_humano) return false;
  return true;
}

function filaHTML(i){
  const e = EPISODIOS[i], r = e.resumen || {};
  const vmax = vmaxDe(e), ver = veredictoDeEp(e);
  const clase = ver === "BUG" ? "mal" : (ver === "corroborado" ? "ok" : "");
  return '<tr data-ep="' + i + '" class="' + (i === iEp ? "activo" : "") + '">'
    + '<td class="mono">' + esc(e.id) + "</td>"
    + "<td>" + esc(e.condicion || "-") + "</td>"
    + '<td class="num">' + (e.N != null ? e.N : "-") + "</td>"
    + '<td class="' + (r.escape ? "alerta" : "") + '">' + (r.escape ? "Si" : "No") + "</td>"
    + '<td class="num"><b>' + (r.span_de_origen != null ? r.span_de_origen : "-") + "</b></td>"
    + '<td class="num"><b>' + (r.corte_minimo != null ? r.corte_minimo : "-") + "</b></td>"
    + '<td class="num">' + (vmax === null ? "-" : pct(vmax)) + "</td>"
    + "<td>" + (r.aviso_a_humano ? "Si" : '<span class="alerta">Nadie</span>') + "</td>"
    + '<td class="' + clase + '">' + esc(veredictoDe(ver)) + "</td></tr>";
}

function pintarTabla(){
  const tb = document.getElementById("cuerpo-ep");
  if(!tb) return;
  let lista = EPISODIOS.map((_e, i) => i).filter((i) => pasaFiltros(EPISODIOS[i]));
  if(orden.col){
    lista.sort((a, b) => {
      const va = valorCol(EPISODIOS[a], orden.col), vb = valorCol(EPISODIOS[b], orden.col);
      if(typeof va === "string" || typeof vb === "string")
        return orden.dir * String(va).localeCompare(String(vb));
      return orden.dir * (va - vb);
    });
  }
  tb.innerHTML = lista.length
    ? lista.map(filaHTML).join("")
    : '<tr class="vacia"><td colspan="9">Ningun episodio pasa los filtros.</td></tr>';
  const cuenta = document.getElementById("f-cuenta");
  if(cuenta) cuenta.textContent = lista.length + " de " + EPISODIOS.length + " episodios";
  document.querySelectorAll("#indice th[data-col]").forEach((th) => {
    th.classList.toggle("ord-asc", th.dataset.col === orden.col && orden.dir > 0);
    th.classList.toggle("ord-desc", th.dataset.col === orden.col && orden.dir < 0);
  });
}

// ---------- tarjetas de las cuatro preguntas ----------
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

// ---------- armar el detalle de un episodio ----------
function cabecera(e){
  const chips = [];
  if(e.condicion) chips.push(esc(e.condicion));
  if(e.N != null) chips.push("N = " + e.N);
  if(e.n_partes !== "" && e.n_partes != null) chips.push("clave en " + e.n_partes + " partes");
  if(e.peldano !== "" && e.peldano != null) chips.push("peldano " + e.peldano);
  return '<div class="cab-episodio"><h2>Episodio <span class="mono">' + esc(e.id) + "</span></h2>"
    + (chips.length ? '<div class="chips">' + chips.map((c) => '<span class="chip">' + c + "</span>").join("") + "</div>" : "")
    + "</div>";
}

function controlesHTML(e){
  const dec = !!e.decisivo;
  return '<div class="controles">'
    + '<label class="int" title="' + (dec
        ? "Atenua lo que no contribuyo a la accion restringida"
        : "Este episodio no tuvo accion restringida") + '">'
    + '<input type="checkbox" id="c-cono"' + (dec && soloCono ? " checked" : "") + (dec ? "" : " disabled")
    + "> Solo el cono causal</label>"
    + '<label class="int" title="Los nodos de razonamiento interno no mueven informacion entre contenedores">'
    + '<input type="checkbox" id="c-razon"' + (sinRazon ? " checked" : "")
    + "> Ocultar razonamiento</label>"
    + '<input type="search" id="q-nodo" placeholder="Buscar en el grafo: id, texto, agente..." aria-label="Buscar en el grafo">'
    + "</div>";
}

function lienzoHTML(){
  return '<div class="lienzo">'
    + '<div class="marco-mapa" id="marco-mapa">'
      + '<div class="barra-zoom">'
        + '<button id="z-menos" type="button" title="Alejar">&minus;</button>'
        + '<span id="z-nivel" title="Zoom actual">100%</span>'
        + '<button id="z-mas" type="button" title="Acercar">+</button>'
        + '<button id="z-ajustar" type="button" title="Ajustar todo el grafo a la pantalla">Ajustar</button>'
      + "</div>"
      + '<div class="mini" id="mini" title="Minimapa: clic o arrastra para moverte por el grafo"></div>'
    + "</div>"
    + '<aside id="panel-lateral"></aside>'
    + "</div>"
    + '<div class="pista" id="pista"></div>';
}

function pistaHTML(info, e){
  return '<span class="cuenta">' + info.nNodos + " nodos &middot; " + info.nAristas + " aristas &middot; "
    + info.nAgentes + " contenedores" + (e.decisivo ? "" : " &middot; sin accion restringida") + "</span>"
    + '<span class="leyenda">'
    + '<span><i class="muestra" style="border-color:var(--deriva)"></i>deriva: dentro del contenedor, no se puede cortar</span>'
    + '<span><i class="muestra" style="border-color:var(--transfiere)"></i>transfiere: cruzo el canal</span>'
    + '<span><i class="muestra discontinua" style="border-color:var(--critica)"></i>critica: pertenece al corte minimo</span>'
    + '<span><i class="muestra punto"></i>raiz: informacion que entro al sistema</span>'
    + "</span>"
    + '<span class="ayuda-mapa">arrastra para moverte &middot; rueda para zoom &middot; doble clic ajusta &middot; clic en un nodo fija su procedencia</span>';
}

function criticos(e){
  const r = e.resumen;
  if(!r.mensajes_criticos || !r.mensajes_criticos.length) return "";
  const n = r.mensajes_criticos.length;
  const li = r.mensajes_criticos.map(function(m){
    return '<li><span class="mono enlace" data-elegir="' + esc(m[0]) + '">' + esc(m[0])
      + "</span> &mdash; " + esc(m[2]) + " &rarr; " + esc(m[3]) + "</li>";
  }).join("");
  return "<h3>" + (n === 1 ? "El mensaje del corte" : "Los " + n + " mensajes del corte") + "</h3>"
    + '<p class="nota-corte">Bloquea estos y el escape no ocurre. '
    + "Es la replica contrafactual: se repite el episodio con estos event_id invisibles.</p>"
    + '<ul class="criticos">' + li + "</ul>";
}

function visibilidadTabla(e){
  const v = (e.resumen || {}).visibilidad;
  if(!v) return "";
  const celda = (x) => {
    const val = typeof x === "number" ? x : 0;
    return '<td><div class="con-barra"><span class="valor">' + pct(val)
      + '</span><span class="barra"><i style="width:' + (val * 100) + '%"></i></span></div></td>';
  };
  const filas = Object.entries(v)
    .sort((a, b) => {
      const vA = typeof a[1] === "number" ? a[1] : (a[1].por_raices || 0);
      const vB = typeof b[1] === "number" ? b[1] : (b[1].por_raices || 0);
      return vB - vA;
    })
    .map((par) => {
      const valR = typeof par[1] === "number" ? par[1] : par[1].por_raices;
      const valA = typeof par[1] === "number" ? 0 : par[1].por_ancestros;
      return '<tr><td class="mono">' + esc(par[0]) + "</td>"
        + celda(valR) + celda(valA) + "</tr>";
    }).join("");
  return "<h3>Visibilidad por agente</h3>"
    + '<div class="tabla-scroll baja"><table><thead><tr><th>Agente</th><th>De los origenes</th>'
    + "<th>Del cono causal</th></tr></thead><tbody>" + filas + "</tbody></table></div>";
}

// ---------- dibujo del grafo ----------
function dibujar(e){
  const dec = e.decisivo;
  const nodos = sinRazon ? e.nodos.filter((n) => n.tipo !== "razonamiento") : e.nodos;
  const visibles = {};
  nodos.forEach((n) => { visibles[n.id] = true; });
  const agentes = Array.from(new Set(e.nodos.map((n) => n.agente))).sort();
  const laneDe = {}, colorDe = {};
  agentes.forEach((a, i) => { laneDe[a] = i; colorDe[a] = color(i); });

  const pos = new Map();
  nodos.forEach((n, i) => {
    const xl = PAD_L + laneDe[n.agente] * LANE + (LANE - CAJA_W) / 2;
    pos.set(n.id, { x: xl + CAJA_W / 2, xl: xl, y: PAD_T + i * ROW });
  });

  const W = Math.max(560, PAD_L + agentes.length * LANE + (dec ? 176 : 36));
  const H = Math.max(240, PAD_T + nodos.length * ROW + 30);

  let bandas = "", aristas = "", nodosS = "", regla = "", cabs = "";
  agentes.forEach((a, i) => {
    const x = PAD_L + i * LANE;
    bandas += '<rect x="' + (x + 6) + '" y="' + (PAD_T - 16) + '" width="' + (LANE - 12)
      + '" height="' + (H - PAD_T + 4) + '" rx="10" fill="' + colorDe[a] + '" fill-opacity=".05"/>';
    cabs += '<text class="cab" data-x="' + (x + LANE / 2) + '" transform="translate('
      + (x + LANE / 2) + "," + (PAD_T - 26) + ')" text-anchor="middle" fill="' + colorDe[a] + '">'
      + esc(a) + "</text>";
  });

  const porDibujar = e.aristas.filter((ar) => visibles[ar.de] && visibles[ar.a]);
  porDibujar.sort((a, b) => (a.critica ? 1 : 0) - (b.critica ? 1 : 0));   // criticas encima
  porDibujar.forEach((ar) => {
    const p = pos.get(ar.de), q = pos.get(ar.a);
    const ap = (soloCono && dec && !ar.cono) ? " apagada" : "";
    const dy = Math.max(14, (q.y - p.y) * 0.42);
    const d = "M" + p.x + " " + (p.y + CAJA_H / 2)
      + " C" + p.x + " " + (p.y + CAJA_H / 2 + dy)
      + ", " + q.x + " " + (q.y - CAJA_H / 2 - dy)
      + ", " + q.x + " " + (q.y - CAJA_H / 2);
    let trazo = "var(--deriva)", ancho = 1.1, extra = "";
    if(ar.critica){ trazo = "var(--critica)"; ancho = 2.6; extra = ' stroke-dasharray="6 3"'; }
    else if(ar.tipo === "transfiere"){ trazo = "var(--transfiere)"; ancho = 1.9; }
    aristas += '<path class="arista' + ap + '" data-de="' + esc(ar.de) + '" data-a="' + esc(ar.a)
      + '" d="' + d + '" fill="none" stroke="' + trazo + '" stroke-width="' + ancho + '"'
      + extra + ' color="' + trazo + '" marker-end="url(#flecha)"/>';
  });

  nodos.forEach((n) => {
    const p = pos.get(n.id), c = colorDe[n.agente];
    const ap = (soloCono && dec && !n.cono) ? " apagado" : "";
    const borde = n.decisivo ? "var(--critica)" : (n.raiz ? c : "var(--linea)");
    const grosor = n.decisivo ? 2.4 : (n.raiz ? 1.7 : 1);
    const etq = (n.tipo + (n.texto ? " " + n.texto : "")).slice(0, 21);
    nodosS += '<g class="nodo' + ap + '" data-id="' + esc(n.id) + '">'
      + "<title>" + esc(n.tipo) + " - paso " + n.step + " - " + esc(n.texto) + "</title>"
      + '<rect class="caja" x="' + p.xl + '" y="' + (p.y - CAJA_H / 2) + '" width="' + CAJA_W
      + '" height="' + CAJA_H + '" rx="6" fill="' + c + '" fill-opacity=".13" stroke="' + borde
      + '" stroke-width="' + grosor + '"/>'
      + '<rect class="tira" x="' + (p.xl + 3.5) + '" y="' + (p.y - CAJA_H / 2 + 4)
      + '" width="3.5" height="' + (CAJA_H - 8) + '" rx="1.5" fill="' + colorTipo(n.tipo)
      + '" fill-opacity=".75"/>'
      + '<text class="etq" x="' + (p.xl + 12) + '" y="' + (p.y + 3.5) + '">' + esc(etq) + "</text>"
      + (n.raiz ? '<circle cx="' + (p.xl + CAJA_W - 9) + '" cy="' + p.y + '" r="3" fill="' + c + '"/>' : "")
      + (n.decisivo ? '<text class="dec" x="' + (p.xl + CAJA_W + 8) + '" y="' + (p.y + 3.5)
        + '">accion restringida</text>' : "")
      + "</g>";
    regla += '<text class="paso' + ap + '" data-id="' + esc(n.id) + '" data-x="' + (PAD_L - 16)
      + '" data-y="' + (p.y + 3.5) + '" transform="translate(' + (PAD_L - 16) + "," + (p.y + 3.5)
      + ')" text-anchor="end">' + n.step + "</text>";
  });

  // Minimapa: el grafo entero en miniatura, con el rectangulo de lo visible.
  const ms = Math.min(170 / W, 118 / H);
  let mini = "";
  agentes.forEach((a, i) => {
    mini += '<rect x="' + ((PAD_L + i * LANE + 6) * ms).toFixed(1) + '" y="' + ((PAD_T - 16) * ms).toFixed(1)
      + '" width="' + ((LANE - 12) * ms).toFixed(1) + '" height="' + ((H - PAD_T + 4) * ms).toFixed(1)
      + '" rx="2" fill="' + colorDe[a] + '" fill-opacity=".14"/>';
  });
  nodos.forEach((n) => {
    const p = pos.get(n.id);
    mini += '<circle cx="' + (p.x * ms).toFixed(1) + '" cy="' + (p.y * ms).toFixed(1) + '" r="'
      + (n.decisivo ? 3.4 : 2.2) + '" fill="' + (n.decisivo ? "var(--critica)" : colorDe[n.agente]) + '"/>';
  });
  mini += '<rect id="mini-vp" x="0" y="0" width="10" height="10" fill="none" stroke="var(--tinta)"'
    + ' stroke-opacity=".55" stroke-width="1"/>';
  mini = '<svg id="mini-svg" width="' + Math.max(70, Math.round(W * ms)) + '" height="'
    + Math.max(46, Math.round(H * ms)) + '" viewBox="0 0 ' + Math.max(70, Math.round(W * ms)) + " "
    + Math.max(46, Math.round(H * ms)) + '" role="img" aria-label="Minimapa">' + mini + "</svg>";

  const svg = '<svg id="svg" width="100%" height="100%" role="img" aria-label="Mapa de procedencia del episodio '
    + esc(e.id) + '">'
    + '<defs><marker id="flecha" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" '
    + 'orient="auto"><path d="M0 0 L8 4 L0 8 z" fill="currentColor"/></marker></defs>'
    + '<g id="vp" transform="translate(0 0)">' + bandas + aristas + nodosS
    + '<rect id="anillo" class="anillo" x="-99" y="-99" width="10" height="10" rx="8" fill="none" '
    + 'stroke="var(--tinta)" stroke-width="1.6" style="display:none"/>'
    + "</g>"
    + '<rect class="velo" id="fondo-cab" x="0" y="0" width="100%" height="32" style="display:none"/>'
    + '<rect class="velo" id="fondo-regla" x="0" y="0" width="46" height="100%" style="display:none"/>'
    + '<g class="sticky">' + cabs + "</g>"
    + '<g class="sticky">' + regla + "</g>"
    + '<text class="paso-titulo" x="8" y="18">paso</text>'
    + "</svg>";

  return { svg: svg, mini: mini, ms: ms, W: W, H: H, pos: pos,
           nNodos: nodos.length, nAristas: porDibujar.length, nAgentes: agentes.length };
}

// ---------- transformacion del lienzo (zoom / paneo) ----------
function limitarK(k){ return Math.min(4, Math.max(0.05, k)); }

function aplicar(){
  if(!G) return;
  G.vp.setAttribute("transform", "translate(" + G.tx + " " + G.ty + ") scale(" + G.k + ")");
  if(!rafPend){
    rafPend = requestAnimationFrame(function(){
      rafPend = null;
      actualizarSticky(); actualizarMini(); actualizarZoom();
    });
  }
}

function actualizarZoom(){
  if(G && G.zNivel) G.zNivel.textContent = Math.round(G.k * 100) + "%";
}

function zoomHacia(f, mx, my){
  const k2 = limitarK(G.k * f), fx = k2 / G.k;
  if(fx === 1) return;
  G.tx = mx - (mx - G.tx) * fx;
  G.ty = my - (my - G.ty) * fx;
  G.k = k2;
  aplicar();
}

function zoomAnimado(f){
  const r = G.svg.getBoundingClientRect();
  const mx = r.width / 2, my = r.height / 2;
  const k2 = limitarK(G.k * f), fx = k2 / G.k;
  animarA(k2, mx - (mx - G.tx) * fx, my - (my - G.ty) * fx);
}

function animarA(k2, tx2, ty2){
  detenerAnim();
  const k1 = G.k, tx1 = G.tx, ty1 = G.ty, t0 = performance.now(), dur = 280;
  const paso = function(t){
    const u = Math.min(1, (t - t0) / dur), s = 1 - Math.pow(1 - u, 3);
    G.k = k1 + (k2 - k1) * s; G.tx = tx1 + (tx2 - tx1) * s; G.ty = ty1 + (ty2 - ty1) * s;
    aplicar();
    anim = u < 1 ? requestAnimationFrame(paso) : null;
  };
  anim = requestAnimationFrame(paso);
}
function detenerAnim(){ if(anim){ cancelAnimationFrame(anim); anim = null; } }

function ajustar(animado){
  const r = G.svg.getBoundingClientRect();
  const m = 18;
  const k2 = limitarK(Math.min(1.4, (r.width - 2 * m) / G.W, (r.height - 2 * m) / G.H));
  const tx2 = (r.width - G.W * k2) / 2, ty2 = (r.height - G.H * k2) / 2;
  if(animado === false){ G.k = k2; G.tx = tx2; G.ty = ty2; aplicar(); }
  else animarA(k2, tx2, ty2);
}

function ajustarAl100(){
  const r = G.svg.getBoundingClientRect();
  animarA(1, (r.width - G.W) / 2, (r.height - G.H) / 2);
}

// ---------- interaccion con el lienzo ----------
function alRueda(ev){
  ev.preventDefault();
  const r = G.svg.getBoundingClientRect();
  let dy = ev.deltaY;
  if(ev.deltaMode === 1) dy *= 16; else if(ev.deltaMode === 2) dy *= 400;
  zoomHacia(Math.exp(-dy * 0.0016), ev.clientX - r.left, ev.clientY - r.top);
}

function alBajar(ev){
  if(ev.pointerType === "mouse" && ev.button !== 0) return;
  try{ G.svg.setPointerCapture(ev.pointerId); }catch(_){}
  if(!puntas) puntas = new Map();
  puntas.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
  if(puntas.size === 1){
    arrastre = { mov: 0, objetivo: ev.target.closest ? ev.target.closest(".nodo") : null };
    G.marco.classList.add("agarrando");
  }
  detenerAnim();
}

function alMoverse(ev){
  if(!puntas || !puntas.has(ev.pointerId)) return;
  const antes = new Map(puntas);
  puntas.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
  if(puntas.size === 1){
    const a = antes.get(ev.pointerId);
    G.tx += ev.clientX - a.x;
    G.ty += ev.clientY - a.y;
    if(arrastre) arrastre.mov += Math.abs(ev.clientX - a.x) + Math.abs(ev.clientY - a.y);
    aplicar();
  } else if(puntas.size >= 2){
    const ids = Array.from(puntas.keys());
    const p0 = puntas.get(ids[0]), p1 = puntas.get(ids[1]);
    const a0 = antes.get(ids[0]), a1 = antes.get(ids[1]);
    const r = G.svg.getBoundingClientRect();
    const d0 = Math.hypot(a0.x - a1.x, a0.y - a1.y) || 1;
    const d1 = Math.hypot(p0.x - p1.x, p0.y - p1.y) || 1;
    zoomHacia(d1 / d0, (p0.x + p1.x) / 2 - r.left, (p0.y + p1.y) / 2 - r.top);
    G.tx += (p0.x - a0.x + p1.x - a1.x) / 2;
    G.ty += (p0.y - a0.y + p1.y - a1.y) / 2;
    aplicar();
  }
}

function alSubir(ev){
  if(!puntas || !puntas.has(ev.pointerId)) return;
  puntas.delete(ev.pointerId);
  if(puntas.size === 0){
    puntas = null;
    G.marco.classList.remove("agarrando");
    if(arrastre && arrastre.mov < 6){
      if(arrastre.objetivo) elegir(arrastre.objetivo.dataset.id);
      else if(sel) deseleccionar();
    }
    arrastre = null;
  }
}

function alDoble(ev){
  if(!ev.target.closest(".nodo")) ajustar(true);
}

// ---------- hover: iluminar la cadena causal ----------
function alEncima(ev){
  if(arrastre || puntas || qNodo) return;
  const g = ev.target.closest ? ev.target.closest(".nodo") : null;
  const id = g ? g.dataset.id : null;
  if(id === hoverId) return;
  hoverId = id;
  if(id) resaltar(id); else desresaltar();
}
function alSalir(ev){
  if(arrastre || puntas || qNodo) return;
  if(!ev.relatedTarget || !G || !G.svg.contains(ev.relatedTarget)){
    hoverId = null; desresaltar();
  }
}

function alcanceDe(id){
  if(G.cache[id]) return G.cache[id];
  const arriba = new Set([id]), abajo = new Set([id]);
  let cola = [id];
  while(cola.length){
    const n = cola.pop();
    (G.saliendo[n] || []).forEach(function(m){ if(!abajo.has(m)){ abajo.add(m); cola.push(m); } });
  }
  cola = [id];
  while(cola.length){
    const n = cola.pop();
    (G.entrando[n] || []).forEach(function(m){ if(!arriba.has(m)){ arriba.add(m); cola.push(m); } });
  }
  return (G.cache[id] = { arriba: arriba, abajo: abajo });
}

function resaltar(id){
  const A = alcanceDe(id);
  const junto = new Set(A.arriba);
  A.abajo.forEach(function(x){ junto.add(x); });
  G.nodosEL.forEach(function(el, nid){
    const off = !junto.has(nid);
    el.classList.toggle("dim", off);
    const pr = G.pasosEL.get(nid);
    if(pr) pr.classList.toggle("dim", off);
  });
  G.aristasEL.forEach(function(a){
    a.el.classList.toggle("dim", !(junto.has(a.de) && junto.has(a.a)));
  });
}

function desresaltar(){
  if(!G) return;
  G.nodosEL.forEach(function(el){ el.classList.remove("dim"); });
  G.pasosEL.forEach(function(el){ el.classList.remove("dim"); });
  G.aristasEL.forEach(function(a){ a.el.classList.remove("dim"); });
}

// ---------- busqueda dentro del grafo ----------
function buscarEnGrafo(q){
  if(!G) return;
  if(!q){ despejarBusqueda(); return; }
  const ag = q.toLowerCase();
  const coincide = function(id){
    const n = G.nodoPorId.get(id);
    if(!n) return false;
    return (id + " " + n.tipo + " " + (n.texto || "") + " " + n.agente + " " + (n.detalle || ""))
      .toLowerCase().includes(ag);
  };
  G.nodosEL.forEach(function(el, nid){
    const m = coincide(nid);
    el.classList.toggle("dim", !m);
    el.classList.toggle("hallado", m);
    const pr = G.pasosEL.get(nid);
    if(pr) pr.classList.toggle("dim", !m);
  });
  G.aristasEL.forEach(function(a){
    a.el.classList.toggle("dim", !(coincide(a.de) || coincide(a.a)));
  });
}
function despejarBusqueda(){
  G.nodosEL.forEach(function(el){ el.classList.remove("dim", "hallado"); });
  G.pasosEL.forEach(function(el){ el.classList.remove("dim"); });
  G.aristasEL.forEach(function(a){ a.el.classList.remove("dim"); });
}

// ---------- etiquetas pegajosas y minimapa ----------
function actualizarSticky(){
  if(!G) return;
  // nombres de contenedor: siguen a su carril en X, se pegan arriba en Y
  const yNat = G.ty + (PAD_T - 26) * G.k;
  const pegadoY = yNat < 20;
  G.veloCab.style.display = pegadoY ? "" : "none";
  const yCab = pegadoY ? 20 : yNat;
  G.cabs.forEach(function(c){
    c.el.setAttribute("transform", "translate(" + (G.tx + c.x * G.k) + " " + yCab + ")");
  });
  // regla de pasos: sigue a su fila en Y, se pega a la izquierda en X
  const xNat = G.tx + (PAD_L - 16) * G.k;
  const pegadoX = xNat < 46;
  G.veloRegla.style.display = pegadoX ? "" : "none";
  G.regla.forEach(function(s){
    const y = G.ty + s.y * G.k;
    if(pegadoX){
      s.el.setAttribute("text-anchor", "start");
      s.el.setAttribute("transform", "translate(8 " + y + ")");
    } else {
      s.el.setAttribute("text-anchor", "end");
      s.el.setAttribute("transform", "translate(" + (G.tx + s.x0 * G.k) + " " + y + ")");
    }
  });
}

function actualizarMini(){
  if(!G || !G.miniSvg) return;
  const r = G.svg.getBoundingClientRect();
  if(!r.width) return;
  const v = G.miniVp;
  v.setAttribute("x", (-G.tx / G.k * G.ms).toFixed(1));
  v.setAttribute("y", (-G.ty / G.k * G.ms).toFixed(1));
  v.setAttribute("width", Math.max(4, r.width / G.k * G.ms).toFixed(1));
  v.setAttribute("height", Math.max(4, r.height / G.k * G.ms).toFixed(1));
}

// ---------- seleccion y panel ----------
function moverAnillo(){
  if(!G) return;
  const a = G.anillo;
  const p = sel ? G.pos.get(sel) : null;
  if(!p){ a.style.display = "none"; return; }
  a.setAttribute("x", p.xl - 3.5);
  a.setAttribute("y", p.y - CAJA_H / 2 - 3.5);
  a.setAttribute("width", CAJA_W + 7);
  a.setAttribute("height", CAJA_H + 7);
  a.style.display = "";
}

function asegurarVisible(id, forzar){
  if(!G) return;
  const n = G.pos.get(id);
  if(!n) return;
  const r = G.svg.getBoundingClientRect();
  const sx = n.x * G.k + G.tx, sy = n.y * G.k + G.ty;
  const M = 90;
  if(forzar || sx < M || sx > r.width - M || sy < M || sy > r.height - M){
    animarA(G.k, r.width / 2 - n.x * G.k, r.height / 2 - n.y * G.k);
  }
}

function elegir(id){
  if(!G || !G.nodoPorId.has(id)) return;
  sel = id;
  moverAnillo();
  actualizarPanel();
  asegurarVisible(id, false);
}

function deseleccionar(){
  sel = null;
  moverAnillo();
  actualizarPanel();
}

function actualizarPanel(){
  const el = document.getElementById("panel-lateral");
  if(el && G) el.innerHTML = panel(G.e);
}

function panel(e){
  if(!sel) return '<div class="vacio"><p>Selecciona un nodo del mapa<br>para ver de donde salio.</p>'
    + '<p class="ayuda">Al pasar el cursor por un nodo se ilumina toda su cadena causal: '
    + "de donde viene la informacion y a donde llega. Un clic la fija aca.</p></div>";
  const n = e.nodos.find(function(x){ return x.id === sel; });
  if(!n) return "";
  const refs = function(ids){
    return ids.length
      ? ids.map(function(i){ return '<span class="mono enlace" data-elegir="' + esc(i) + '">'
          + esc(i) + "</span>"; }).join(" &middot; ")
      : '<span class="apagado">ninguno</span>';
  };
  let chips = "";
  if(n.raiz) chips += '<span class="chip">raiz</span>';
  if(n.cono && e.decisivo) chips += '<span class="chip">cono causal</span>';
  if(n.decisivo) chips += '<span class="chip roja">accion decisiva</span>';
  let h = '<div class="cab-nodo"><h3>' + esc(n.tipo) + "</h3>"
    + (chips ? '<div class="chips">' + chips + "</div>" : "") + "</div>"
    + '<div class="campo"><b>event_id</b><span class="mono">' + esc(n.id) + "</span></div>"
    + '<div class="campo"><b>agente / contenedor</b>' + esc(n.agente) + ' &middot; <span class="mono">'
    + esc(n.contenedor) + "</span></div>"
    + '<div class="campo"><b>paso causal</b>' + n.step
    + (n.raiz ? " &middot; <b>raiz</b>: informacion que entro al sistema" : "") + "</div>"
    + '<div class="campo"><b>contenido</b><pre>' + esc(n.detalle) + "</pre></div>"
    + '<div class="campo"><b>ancestros (lo que tenia)</b>' + refs(n.ancestros) + "</div>";
  if(n.citados.length) h += '<div class="campo"><b>citados (lo que dice que uso)</b>' + refs(n.citados) + "</div>";
  if(n.partes.length) h += '<div class="campo"><b>partes reales usadas (oraculo)</b><span class="mono">'
    + esc(n.partes.join(", ")) + "</span></div>";
  if(n.exito !== null && n.exito !== undefined)
    h += '<div class="campo"><b>exito</b><span class="' + (n.exito ? "alerta" : "") + '">'
      + (n.exito ? "Si" : "No") + "</span></div>";
  if(G && !G.nodosEL.has(n.id))
    h += '<div class="campo"><b>nota</b><span class="apagado">Este nodo esta oculto ahora mismo '
      + "por el filtro de razonamiento.</span></div>";
  h += '<div class="acciones"><button class="btn" data-centrar="' + esc(n.id)
    + '">Centrar en el mapa</button></div>';
  return h;
}

// ---------- montar el mapa de un episodio ----------
function montarMapa(e, prevT){
  detenerAnim();
  hoverId = null;
  const marco = document.getElementById("marco-mapa");
  const d = dibujar(e);
  marco.insertAdjacentHTML("afterbegin", d.svg);

  const svg = document.getElementById("svg");
  const nodosEL = new Map(), pasosEL = new Map(), aristasEL = [], regla = [], cabs = [];
  svg.querySelectorAll(".nodo").forEach(function(g){ nodosEL.set(g.dataset.id, g); });
  svg.querySelectorAll(".paso").forEach(function(t){
    pasosEL.set(t.dataset.id, t);
    regla.push({ el: t, y: +t.dataset.y, x0: +t.dataset.x });
  });
  svg.querySelectorAll(".arista").forEach(function(p){
    aristasEL.push({ el: p, de: p.dataset.de, a: p.dataset.a });
  });
  svg.querySelectorAll(".cab").forEach(function(t){ cabs.push({ el: t, x: +t.dataset.x }); });

  const nodoPorId = new Map(e.nodos.map(function(n){ return [n.id, n]; }));
  const entrando = {}, saliendo = {};
  aristasEL.forEach(function(a){
    (saliendo[a.de] = saliendo[a.de] || []).push(a.a);
    (entrando[a.a] = entrando[a.a] || []).push(a.de);
  });

  G = { e: e, svg: svg, marco: marco, vp: svg.querySelector("#vp"),
        W: d.W, H: d.H, k: 1, tx: 0, ty: 0,
        nodosEL: nodosEL, pasosEL: pasosEL, aristasEL: aristasEL, regla: regla, cabs: cabs,
        nodoPorId: nodoPorId, pos: d.pos, entrando: entrando, saliendo: saliendo, cache: {},
        anillo: svg.querySelector("#anillo"),
        veloCab: svg.querySelector("#fondo-cab"),
        veloRegla: svg.querySelector("#fondo-regla"),
        zNivel: document.getElementById("z-nivel"),
        ms: d.ms, miniSvg: null, miniVp: null,
        info: { nNodos: d.nNodos, nAristas: d.nAristas, nAgentes: d.nAgentes } };

  // minimapa
  const contMini = document.getElementById("mini");
  contMini.innerHTML = d.mini;
  G.miniSvg = document.getElementById("mini-svg");
  G.miniVp = G.miniSvg.querySelector("#mini-vp");
  let miniArr = false;
  const irMini = function(ev){
    const rm = G.miniSvg.getBoundingClientRect();
    if(!rm.width || !rm.height) return;
    const w = parseFloat(G.miniSvg.getAttribute("width")) || rm.width;
    const h = parseFloat(G.miniSvg.getAttribute("height")) || rm.height;
    const gx = ((ev.clientX - rm.left) * (w / rm.width)) / G.ms;
    const gy = ((ev.clientY - rm.top) * (h / rm.height)) / G.ms;
    const r = G.svg.getBoundingClientRect();
    detenerAnim();
    G.tx = r.width / 2 - gx * G.k;
    G.ty = r.height / 2 - gy * G.k;
    aplicar();
  };
  G.miniSvg.addEventListener("pointerdown", function(ev){
    miniArr = true;
    try{ G.miniSvg.setPointerCapture(ev.pointerId); }catch(_){}
    irMini(ev);
  });
  G.miniSvg.addEventListener("pointermove", function(ev){ if(miniArr) irMini(ev); });
  G.miniSvg.addEventListener("pointerup", function(){ miniArr = false; });
  G.miniSvg.addEventListener("pointercancel", function(){ miniArr = false; });

  // eventos del lienzo
  svg.addEventListener("wheel", alRueda, { passive: false });
  svg.addEventListener("pointerdown", alBajar);
  svg.addEventListener("pointermove", alMoverse);
  svg.addEventListener("pointerup", alSubir);
  svg.addEventListener("pointercancel", alSubir);
  svg.addEventListener("pointerover", alEncima);
  svg.addEventListener("pointerout", alSalir);
  svg.addEventListener("dblclick", alDoble);

  document.getElementById("z-mas").onclick = function(){ zoomAnimado(1.35); };
  document.getElementById("z-menos").onclick = function(){ zoomAnimado(1 / 1.35); };
  document.getElementById("z-ajustar").onclick = ajustarAl100;

  // interruptores y busqueda
  const c1 = document.getElementById("c-cono"), c2 = document.getElementById("c-razon");
  c1.onchange = function(){ soloCono = c1.checked; pintar(); };
  c2.onchange = function(){ sinRazon = c2.checked; pintar(); };
  const q = document.getElementById("q-nodo");
  q.value = qNodo;
  q.oninput = function(){ qNodo = q.value.trim(); buscarEnGrafo(qNodo); };

  if(sel && !nodoPorId.has(sel)) sel = null;

  if(prevT){ G.k = limitarK(prevT.k); G.tx = prevT.tx; G.ty = prevT.ty; aplicar(); }
  else { G.k = 1; G.tx = 0; G.ty = 0; aplicar(); }

  if(qNodo) buscarEnGrafo(qNodo);
  moverAnillo();
  actualizarPanel();
}

// ---------- orquestacion ----------
function verEpisodio(i){
  if(i === iEp) return;
  iEp = i; sel = null; saltar = true; pintar();
}

function pintar(){
  if(!EPISODIOS.length) return;
  const e = EPISODIOS[iEp];
  // Reescribir el innerHTML encoge el documento un instante y el navegador
  // clava el scroll en 0. Lo guardamos y lo devolvemos.
  const y = window.scrollY;
  const mismo = iPintado === iEp;
  const prevT = (G && mismo) ? { k: G.k, tx: G.tx, ty: G.ty } : null;
  iPintado = iEp;
  pintarTabla();
  const det = document.getElementById("detalle-episodio");
  det.innerHTML = cabecera(e) + tarjetas(e) + controlesHTML(e) + lienzoHTML();
  montarMapa(e, prevT);
  document.getElementById("pista").innerHTML = pistaHTML(G.info, e);
  det.insertAdjacentHTML("beforeend", criticos(e) + visibilidadTabla(e));
  if(saltar){
    saltar = false;
    det.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    window.scrollTo(0, y);
  }
}

// ---------- arranque ----------
(function(){
  // tema claro / oscuro
  const btnTema = document.getElementById("tema");
  function ponerTema(t){
    document.documentElement.dataset.theme = t;
    try{ localStorage.setItem("mapa-tema", t); }catch(_){}
    btnTema.textContent = t === "dark" ? "Modo claro" : "Modo oscuro";
  }
  btnTema.onclick = function(){
    const actual = document.documentElement.dataset.theme
      || (window.matchMedia && matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light");
    ponerTema(actual === "dark" ? "light" : "dark");
  };
  try{
    const t = localStorage.getItem("mapa-tema");
    if(t) ponerTema(t);
    else btnTema.textContent = (window.matchMedia && matchMedia("(prefers-color-scheme:dark)").matches)
      ? "Modo claro" : "Modo oscuro";
  }catch(_){ btnTema.textContent = "Modo oscuro"; }

  // resumen de la lista
  const conEsc = EPISODIOS.filter(function(e){ return (e.resumen || {}).escape; }).length;
  document.getElementById("resumen-lista").textContent =
    EPISODIOS.length + " episodios \u00b7 " + conEsc + " con accion restringida";

  // opciones de filtro segun los datos
  const sCond = document.getElementById("f-cond");
  Array.from(new Set(EPISODIOS.map(function(e){ return e.condicion || ""; }).filter(Boolean))).sort()
    .forEach(function(c){
      const o = document.createElement("option");
      o.value = c; o.textContent = "Condicion: " + c;
      sCond.appendChild(o);
    });
  const sOr = document.getElementById("f-oraculo");
  [["corroborado","Corroborados"],["sobreestimacion","Sobreestimacion"],["BUG","Bugs"],
   ["sin_oraculo","Sin oraculo"],["ninguno","Sin verificar"]].forEach(function(p){
    const o = document.createElement("option");
    o.value = p[0]; o.textContent = "Oraculo: " + p[1];
    sOr.appendChild(o);
  });

  function refrescarFiltros(){
    filtros.q = document.getElementById("f-q").value.trim();
    filtros.cond = sCond.value;
    filtros.accion = document.getElementById("f-accion").value;
    filtros.oraculo = sOr.value;
    filtros.aviso = document.getElementById("f-aviso").value;
    const hay = filtros.q || filtros.cond || filtros.accion || filtros.oraculo || filtros.aviso;
    document.getElementById("f-limpiar").hidden = !hay;
    pintarTabla();
  }
  document.getElementById("f-q").addEventListener("input", refrescarFiltros);
  [sCond, document.getElementById("f-accion"), sOr, document.getElementById("f-aviso")]
    .forEach(function(el){ el.addEventListener("change", refrescarFiltros); });
  document.getElementById("f-limpiar").onclick = function(){
    document.getElementById("f-q").value = "";
    sCond.value = "";
    document.getElementById("f-accion").value = "";
    sOr.value = "";
    document.getElementById("f-aviso").value = "";
    refrescarFiltros();
  };

  // orden por columna
  document.querySelector("#indice thead").addEventListener("click", function(ev){
    const th = ev.target.closest("th[data-col]");
    if(!th) return;
    if(orden.col === th.dataset.col) orden.dir *= -1;
    else { orden.col = th.dataset.col; orden.dir = 1; }
    pintarTabla();
  });

  // delegacion de clics: filas, enlaces a nodos, centrar
  document.addEventListener("click", function(ev){
    if(!ev.target || !ev.target.closest) return;
    const en = ev.target.closest("[data-elegir]");
    if(en){ elegir(en.dataset.elegir); return; }
    const ce = ev.target.closest("[data-centrar]");
    if(ce){ if(sel) asegurarVisible(ce.dataset.centrar, true); return; }
    const ep = ev.target.closest("[data-ep]");
    if(ep) verEpisodio(+ep.dataset.ep);
  });

  document.addEventListener("keydown", function(ev){
    if(ev.key === "Escape" && sel && G) deseleccionar();
  });
  window.addEventListener("resize", function(){ if(G) aplicar(); });

  if(EPISODIOS.length) pintar();
  else document.getElementById("detalle-episodio").innerHTML =
    '<div class="vacio">No quedo ningun episodio utilizable para dibujar.</div>';
})();
</script></body></html>
"""


if __name__ == "__main__":
    main()