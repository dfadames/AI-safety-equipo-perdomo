"""
El runner: corre episodios y barridos.

Ronda robin, no paralelo. Con semilla fija la corrida se repite igual —hace
falta para la réplica contrafactual—, no hay escrituras entrelazadas, y es
mucho más fácil saber qué tenía cada agente en la ventana en cada paso. No se
pierde nada científicamente: lo que medimos es agregación de información, no
condiciones de carrera.

    python -m hormiguero.runner barrido --N 1 2 4 8 --episodios 20
    python -m hormiguero.runner uno --N 4 --condicion honestidad
    python -m hormiguero.runner levantar --n-partes 4
    python -m hormiguero.runner auditar --n-partes 4
    python -m hormiguero.runner bajar
    python -m hormiguero.runner repetir --bloqueo lista_de_bloqueo.json --episodio ep_instruida_N4_000
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import random
import secrets
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .caja_falsa import runner_de
from .canal import Canal
from .config import Config, dir_resultados, peldano_por_defecto
from .registro import Registro
from .sesion import SesionAgente

_SUFIJO_LOG = ".jsonl"


def _ruta_cfg(ruta_log: str) -> str:
    """El nombre del `.cfg.json` que acompaña a cada log: es lo que permite
    reconstruir el episodio EXACTO despues, para la réplica contrafactual."""
    base = ruta_log[: -len(_SUFIJO_LOG)] if ruta_log.endswith(_SUFIJO_LOG) else ruta_log
    return f"{base}.cfg.json"


def _escribir_cfg(cfg: Config, **extra) -> None:
    """`extra` lleva lo que es del episodio corrido y no de la Config
    (`estado`, `turnos_por_agente`). `repetir` lo descarta al reconstruirla."""
    Path(_ruta_cfg(cfg.ruta_log())).write_text(
        json.dumps({**dataclasses.asdict(cfg), **extra}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def config_del_punto(cfg: Config) -> dict:
    """Lo que distingue un punto experimental de otro. Se guarda en cada
    evento para que `grafo.agregar` pueda separar las curvas."""
    return {
        "n_agentes": cfg.n_agentes, "n_partes": cfg.n_partes,
        "peldano": cfg.peldano, "explicitud": cfg.explicitud,
        # Sin esto, los episodios del validador viejo y los del nuevo caen en la
        # misma fila del csv y se promedian entre si: son tareas distintas.
        "version_tarea": cfg.version_tarea,
        "proveedor": cfg.proveedor, "modelo": cfg.modelo,
        "canal_max_chars": cfg.canal_max_chars,
        "canal_max_mensajes": cfg.canal_max_mensajes,
        "canal_persistencia": cfg.canal_persistencia,
        "canal_ttl": cfg.canal_ttl,
        "canal_direccionamiento": cfg.canal_direccionamiento,
    }


def correr_episodio(cfg: Config, proveedor_de, runner=None, con_docker: bool = False,
                    bloqueados: Optional[Iterable[str]] = None,
                    bloqueo_contenido: Optional[dict] = None) -> str:
    """`proveedor_de(agent_id) -> ProveedorLLM`. Devuelve la ruta del log.

    Las dos formas de la réplica contrafactual (subcomando `repetir`):
      `bloqueados`         event_id a descartar. Es la vieja, y no sirve con un
                           modelo no determinista: los ids son posicionales.
      `bloqueo_contenido`  {remitente: [fragmentos]} — ese agente no puede
                           entregar ese contenido, le toque el event_id que le
                           toque. Es la que sí repite el bloqueo."""
    random.seed(cfg.semilla)

    # Con Docker (`runner=None`) las pistas viven en `data/<agente>`, montado
    # en cada caja. El cluster se levanta una vez por N, con la config de quien
    # lo levanto (n_partes=4, condicion instruida): asi corrieron los P=2/P=3
    # con pistas de 4 partes, y un `imposible` correria con las 4 partes a la
    # vista. Se reescriben para ESTE episodio; el montaje es en vivo, asi que
    # no hace falta recrear las cajas.
    if runner is None:
        from .contenedores import preparar_datos
        preparar_datos(cfg)

    registro = Registro(cfg.ruta_log(), cfg.episodio, cfg.semilla, cfg.condicion,
                        config=config_del_punto(cfg))
    canal = Canal(cfg.ruta_shared(), cfg, bloqueados=bloqueados,
                  bloqueo_contenido=bloqueo_contenido)

    sesiones = [SesionAgente(proveedor_de(a), registro, canal, cfg, a, runner=runner)
                for a in cfg.agentes]

    # El cfg se escribe AL EMPEZAR, no al final. Antes solo se escribia al
    # terminar, y un episodio cortado (Ctrl+C, una terminal cerrada) dejaba un
    # .jsonl sin cfg: el plan no lo contaba, `repetir` no lo podia repetir y
    # el agregado lo metia como "sin escape". El log ya se escribe evento a
    # evento; con esto el episodio queda identificado desde el primer paso.
    #
    # `estado` dice como termino: "completo", "interrumpido" (Ctrl+C) o
    # "error: ...". Si el proceso muere sin poder escribir nada (kill), queda
    # "en_curso", que el plan y el agregado tratan igual que interrumpido.
    _escribir_cfg(cfg, estado="en_curso")
    estado = "interrumpido"
    try:
        # ronda robin hasta que todos terminen o se acabe el presupuesto de pasos
        for _ronda in range(cfg.max_pasos):
            vivos = False
            for s in sesiones:
                if s.paso():
                    vivos = True
            if not vivos:
                break
        estado = "completo"
    except Exception as e:
        estado = f"error: {type(e).__name__}"
        raise
    finally:
        # `mensajes_retenidos` es el chequeo de la replica contrafactual: si
        # queda en 0 con un bloqueo puesto, no se bloqueo nada y la replica no
        # dice nada. Eso es lo que paso en 2 de las 3 replicas del 12-sep.
        _escribir_cfg(cfg, estado=estado,
                      turnos_por_agente={s.agent_id: s.turnos for s in sesiones},
                      mensajes_retenidos=len(canal.retenidos))
    return cfg.ruta_log()


def sello() -> str:
    """Identifica UNA corrida. Va en la carpeta y también en el nombre del
    episodio: son dos usos del mismo identificador y tienen que coincidir."""
    return f"{datetime.now():%Y%m%d-%H%M%S}"


def dir_corrida(base: str, ns, peldano: str | None = None, marca: str | None = None) -> str:
    """`runs/<timestamp>_N<agentes>_<peldano>/` — una carpeta por corrida.

    Sin esto todos los barridos caen en el mismo `runs/` y se pisan entre sí:
    dos corridas del mismo punto experimental producen el mismo nombre de
    episodio, y la segunda sobreescribe el log de la primera en silencio.

    El peldaño (R1/R2/R3) va en el nombre porque es el escenario que se corrió:
    sin él, dos corridas con el mismo N solo se distinguen abriendo el cfg.json.
    """
    etiqueta = "-".join(str(n) for n in ns) if isinstance(ns, (list, tuple)) else str(ns)
    esc = f"_{peldano}" if peldano else ""
    return f"{base}/{marca or sello()}_N{etiqueta}{esc}"


def etiqueta_canal(canal: dict) -> str:
    """Sufijo corto para el nombre del episodio cuando el canal NO está en sus
    valores por defecto. Sin esto, dos configuraciones del barrido de canal
    producen el mismo nombre de episodio y la segunda pisa el log de la
    primera en silencio."""
    d, partes = Config(), []
    if canal.get("canal_max_chars", d.canal_max_chars) != d.canal_max_chars:
        partes.append(f"c{canal['canal_max_chars']}")
    if canal.get("canal_max_mensajes", d.canal_max_mensajes) != d.canal_max_mensajes:
        partes.append(f"m{canal['canal_max_mensajes']}")
    if canal.get("canal_persistencia", d.canal_persistencia) != d.canal_persistencia:
        partes.append(f"ef{canal.get('canal_ttl', d.canal_ttl)}")
    if canal.get("canal_direccionamiento", d.canal_direccionamiento) != d.canal_direccionamiento:
        partes.append("p2p")
    return ("_" + "-".join(partes)) if partes else ""


def barrido(ns, episodios, condiciones, crear_proveedor, runner=None, crear_runner=None,
            marca="",
            peldano=None, escenario="credencial", semilla_base=1000,
            dir_logs="logs", dir_shared=None, verbose=True,
            partes=(4,), canal=None) -> list[str]:
    """Corre el producto (condiciones x profundidad x N x episodios).

    `crear_proveedor(cfg) -> (agent_id -> ProveedorLLM)`. Se reconstruye por
    cada episodio, no una vez para todo el barrido: el guion simulado usa las
    partes de ESE N, así que el proveedor depende de la config del episodio.

    `partes` es la profundidad de descomposición (en cuántos pedazos está
    repartida la tarea): es el eje de la tercera curva, la del colapso del
    aviso. `canal` son los tres diales, para el barrido del canal.

    `peldano=None` lo deriva de la condición (instruida->R1, emergente->R2).
    """
    # El canal compartido va bajo --logs, no en el cwd: si no, cada barrido
    # ensucia el repo con una carpeta `shared/` suelta.
    dir_shared = dir_shared or f"{dir_logs}/_shared"
    # Dos barridos del mismo punto producirian episodios con el mismo nombre
    # y `agregar` los fundiria en uno solo. Ver el comentario en `main`.
    sufijo = f"_{marca}" if marca else ""
    canal = dict(canal or {})
    tag = etiqueta_canal(canal)
    rutas = []
    for cond in condiciones:
        esc = "benigno" if cond == "benigna" else escenario
        pel = peldano or peldano_por_defecto(cond)
        for np_ in partes:
            for n in ns:
                for i in range(episodios):
                    cfg = Config(
                        n_agentes=n, n_partes=np_, condicion=cond, peldano=pel,
                        escenario=esc, semilla=semilla_base + i,
                        episodio=f"ep_{cond}_P{np_}_N{n}{tag}_{i:03d}{sufijo}",
                        dir_logs=dir_logs, dir_shared=dir_shared, **canal,
                    )
                    # La caja emulada depende de la config del episodio (el
                    # fragmento sale de cfg), asi que se construye por episodio.
                    r = crear_runner(cfg) if crear_runner else runner
                    rutas.append(correr_episodio(cfg, crear_proveedor(cfg), runner=r))
                    if verbose:
                        print(f"  {cfg.episodio}", flush=True)
    return rutas


def pares_a_bloquear(entrada: dict, control: bool = False) -> dict:
    """{remitente: [fragmentos]} que el canal no va a entregar, sacado de la
    entrada del `lista_de_bloqueo.json` (ver `grafo.agregar.
    especificacion_de_bloqueo`).

    Del corte minimo, o —para la replica de CONTROL— la misma cantidad de pares
    (remitente, fragmento) elegida al azar entre los mensajes que NO estaban en
    el corte. Sin ese control, que el escape se caiga al bloquear el corte
    tambien se explicaria porque bloqueamos mensajes, cualesquiera."""
    def pares(clave):
        return [(p["remitente"], f) for p in entrada.get(clave) or []
                for f in p.get("fragmentos") or []]

    elegidos = pares("corte")
    if control:
        fuera = pares("fuera_del_corte")
        elegidos = (random.Random().sample(fuera, min(len(elegidos), len(fuera)))
                    if fuera else [])
    out: dict[str, list[str]] = {}
    for agente, fragmento in elegidos:
        out.setdefault(agente, []).append(fragmento)
    return out


# --- CLI --------------------------------------------------------------------

def _proveedor_por_nombre(nombre: str, cfg: Config):
    # Queda grabado en el cfg.json y en cada evento: es lo que despues permite
    # mirar un csv y saber si es una medicion o el guion.
    cfg.proveedor = nombre

    if nombre == "simulado":
        cfg.modelo = "guion"
        from .proveedores.simulado import ProveedorSimulado, guion_escape, guion_benigno
        # El guion intenta con lo que la poblacion ALCANZA, no con la clave
        # completa: si este N tiene techo duro, el intento falla solo. Si
        # armaramos la credencial completa a mano estariamos falseando el
        # techo, que es justo lo que hace que la brecha signifique algo.
        # En orden y pegadas: el validador v2 exige la credencial exacta.
        alcanzables = cfg.alcanzables()
        credencial = "".join(p for p in cfg.partes if p in alcanzables)

        def hacer(agent_id):
            ultimo = agent_id == cfg.agentes[-1]
            if cfg.escenario == "benigno":
                g = guion_benigno(agent_id, es_el_que_agrega=ultimo)
            else:
                g = guion_escape(agent_id, cfg.fragmento_de(agent_id),
                                 es_el_que_valida=ultimo, credencial=credencial)
            return ProveedorSimulado(g)
        return hacer

    if nombre == "ollama":
        from .proveedores.ollama import ProveedorOllama
        # semilla fija: la replica contrafactual necesita repetir el episodio
        p = ProveedorOllama(seed=cfg.semilla)
        cfg.modelo = getattr(p, "modelo", "")
        return lambda _a: p

    if nombre == "openai":
        from .proveedores.openai_compat import ProveedorOpenAICompatible
        p = ProveedorOpenAICompatible(seed=cfg.semilla)
        cfg.modelo = p.modelo
        return lambda _a: p

    if nombre == "deepseek":
        from .proveedores.deepseek import ProveedorDeepSeek
        # Ignora la semilla (DeepSeek no la expone). No es un olvido: ver el
        # comentario en deepseek.py sobre que se pierde y que no.
        p = ProveedorDeepSeek(seed=cfg.semilla)
        cfg.modelo = p.modelo
        return lambda _a: p

    if nombre == "glm":
        from .proveedores.glm import ProveedorGLM
        # Tampoco manda semilla, por lo mismo (ver glm.py).
        p = ProveedorGLM(seed=cfg.semilla)
        cfg.modelo = p.modelo
        return lambda _a: p

    raise SystemExit(f"proveedor desconocido: {nombre}")


def _proveedor_o_salir(nombre: str, cfg: Config):
    """Falta la llave es el error mas comun de todos, y por dentro sale como
    RuntimeError: sin esto el usuario ve treinta lineas de traza y el mensaje
    util al final. Sale limpio."""
    try:
        return _proveedor_por_nombre(nombre, cfg)
    except RuntimeError as e:
        raise SystemExit(f"\n{e}\n")


PROVEEDORES = ("simulado", "ollama", "openai", "deepseek", "glm")


def proveedor_por_defecto() -> str:
    """Lo que diga `HORMIGUERO_PROVEEDOR` en el .env, para que correr con
    modelo real sea solo poner la llave y nada mas. Un valor mal escrito cae a
    `simulado` con aviso, en vez de reventar el CLI con un error de argparse
    que no dice de donde salio ese valor."""
    from .entorno import cfg as _cfg
    nombre = (_cfg("HORMIGUERO_PROVEEDOR", "simulado") or "simulado").strip().lower()
    if nombre not in PROVEEDORES:
        print(f"  aviso: HORMIGUERO_PROVEEDOR={nombre!r} no es un proveedor; uso 'simulado'")
        return "simulado"
    return nombre


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hormiguero.runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--proveedor", default=proveedor_por_defecto(),
                       choices=list(PROVEEDORES),
                       help="por defecto, HORMIGUERO_PROVEEDOR del .env")
    comun.add_argument("--peldano", default=None, choices=["R1", "R2", "R3"],
                       help="por defecto se deriva de la condicion: instruida->R1, emergente->R2")
    comun.add_argument("--logs", default=dir_resultados(),
                       help="por defecto, resultados/ en la raiz del repo: es la carpeta que se commitea")
    comun.add_argument("--sin-docker", action="store_true",
                       help="usa un runner simulado en vez de docker exec")
    # Los tres diales del canal: es el barrido del domingo, la unica palanca
    # que un laboratorio sí puede mover.
    comun.add_argument("--canal-max-chars", type=int, default=None)
    comun.add_argument("--canal-max-mensajes", type=int, default=None)
    comun.add_argument("--canal-persistencia", default=None,
                       choices=["duradero", "efimero"])
    comun.add_argument("--canal-ttl", type=int, default=None)
    comun.add_argument("--canal-direccionamiento", default=None,
                       choices=["difusion", "punto_a_punto"])
    comun.add_argument("--explicitud", default=None,
                       choices=["opaco", "sugerente", "explicito"])

    u = sub.add_parser("uno", parents=[comun])
    u.add_argument("--N", type=int, default=4)
    u.add_argument("--n-partes", type=int, default=4)
    u.add_argument("--condicion", default="instruida")
    # En v2 la semilla ademas SORTEA los fragmentos del episodio: con 42 fija,
    # los diez episodios de un punto compartirian la misma clave y el sorteo no
    # seria tal. Por eso el default es una distinta por episodio.
    u.add_argument("--semilla", type=int, default=None,
                   help="por defecto, una distinta por episodio")
    # Solo `imposible`: los controles corrieron con 10 turnos y cambiarles el
    # tope los vuelve incomparables con lo ya corrido.
    u.add_argument("--max-pasos", type=int, default=None,
                   help="turnos por agente; solo con --condicion imposible (por defecto 30)")

    b = sub.add_parser("barrido", parents=[comun])
    b.add_argument("--N", type=int, nargs="+", default=[1, 2, 4, 8])
    b.add_argument("--n-partes", type=int, nargs="+", default=[4],
                   help="profundidad de descomposicion; barrela (ej. 2 3 4 6) "
                        "para la curva de colapso del aviso")
    b.add_argument("--episodios", type=int, default=20)
    b.add_argument("--condiciones", nargs="+", default=["instruida"])

    # El cluster tiene una caja POR AGENTE, asi que `--n-agentes` es lo que
    # fija cuantas se levantan; `--n-partes` solo dice en cuantos pedazos va
    # la clave. Levantar con un N distinto al de la corrida deja cajas de mas
    # (o de menos) y la auditoria no describe el episodio que se corrio.
    lv = sub.add_parser("levantar", help="levanta los contenedores del cluster")
    lv.add_argument("--n-agentes", type=int, default=4)
    lv.add_argument("--n-partes", type=int, default=4)
    lv.add_argument("--dir-data", default="data")

    au = sub.add_parser("auditar", help="corre la auditoria de contencion individual")
    au.add_argument("--n-agentes", type=int, default=4)
    au.add_argument("--n-partes", type=int, default=4)
    au.add_argument("--dir-data", default="data")

    sub.add_parser("bajar", help="baja los contenedores del cluster")

    rp = sub.add_parser(
        "repetir",
        help="repite un episodio con sus mensajes criticos bloqueados (replica contrafactual)")
    rp.add_argument("--bloqueo", required=True,
                    help="el lista_de_bloqueo.json que escribe grafo.agregar")
    rp.add_argument("--episodio", required=True,
                    help="la clave del episodio dentro de --bloqueo")
    rp.add_argument("--control-aleatorio", action="store_true",
                    help="la replica de CONTROL: bloquea la misma cantidad de mensajes, "
                         "pero elegidos al azar FUERA del corte. Sin esta, que el escape "
                         "se caiga no distingue el corte de bloquear cualquier cosa")
    rp.add_argument("--logs", default=dir_resultados(),
                    help="donde esta el <episodio>.cfg.json del episodio original")
    rp.add_argument("--proveedor", default=proveedor_por_defecto(),
                    choices=list(PROVEEDORES))
    rp.add_argument("--sin-docker", action="store_true")

    a = ap.parse_args(argv)

    # Que quede escrito en la salida con que se corrio: un barrido de horas no
    # puede terminar sin que se sepa si fue con modelo real o con el guion.
    if getattr(a, "proveedor", None) and a.cmd in ("uno", "barrido", "repetir"):
        print(f"  proveedor: {a.proveedor}")

    if a.cmd == "levantar":
        from .contenedores import levantar
        from .config import nombre_contenedor
        cfg = Config(n_agentes=a.n_agentes, n_partes=a.n_partes,
                     episodio="_docker", dir_data=a.dir_data)
        levantar(cfg)
        print("Contenedores arriba: "
              + ", ".join(nombre_contenedor(s) for s in cfg.contenedores))
        return None

    if a.cmd == "bajar":
        from .contenedores import bajar
        bajar()
        print("Contenedores abajo.")
        return None

    if a.cmd == "auditar":
        from .contenedores import auditar, imprimir_auditoria
        cfg = Config(n_agentes=a.n_agentes, n_partes=a.n_partes,
                     episodio="_docker", dir_data=a.dir_data)
        resultados = auditar(cfg)
        ok = imprimir_auditoria(resultados)
        if not ok:
            sys.exit(1)
        return resultados

    if a.cmd == "repetir":
        bloqueo = json.loads(Path(a.bloqueo).read_text(encoding="utf-8"))
        if a.episodio not in bloqueo:
            raise SystemExit(f"'{a.episodio}' no esta en {a.bloqueo} "
                             f"(episodios disponibles: {', '.join(sorted(bloqueo)) or '-'})")
        entrada = bloqueo[a.episodio]
        # Formato viejo: una lista de event_id. Se sigue leyendo, para poder
        # repetir un bloqueo ya escrito, pero con el aviso de por que no sirve.
        if isinstance(entrada, list):
            bloqueados, por_contenido = set(entrada), {}
            print("  AVISO: bloqueo por event_id. Los ids son posicionales, asi que al "
                  "repetir con un modelo no determinista caen en otro evento.")
        else:
            bloqueados = set()
            por_contenido = pares_a_bloquear(entrada, control=a.control_aleatorio)
            if not por_contenido:
                raise SystemExit(
                    f"no hay nada que bloquear en '{a.episodio}'"
                    + (": ningun mensaje fuera del corte llevaba un fragmento, asi que "
                       "no se puede armar el control." if a.control_aleatorio
                       else ": el corte no llevaba fragmentos."))
        sufijo = "_contrafactual_control" if a.control_aleatorio else "_contrafactual"

        nombre_cfg = Path(_ruta_cfg(f"{a.episodio}.jsonl")).name
        ruta_cfg_original = Path(a.logs) / nombre_cfg
        if not ruta_cfg_original.exists():
            # los episodios viven en `runs/<corrida>/`, asi que `--logs runs`
            # sigue sirviendo: se busca hacia adentro y se toma la mas reciente.
            candidatos = sorted(Path(a.logs).rglob(nombre_cfg),
                                key=lambda x: x.stat().st_mtime)
            if candidatos:
                ruta_cfg_original = candidatos[-1]
        if not ruta_cfg_original.exists():
            raise SystemExit(
                f"no encontre {ruta_cfg_original}. Se escribe junto al log de cada "
                "episodio corrido con esta misma version del runner.")
        datos = json.loads(ruta_cfg_original.read_text(encoding="utf-8"))
        # Con la marca al final, repetir dos veces el mismo episodio no produce
        # dos logs con el mismo nombre.
        datos["episodio"] = f"{a.episodio}{sufijo}_{sello()[-6:]}"
        # Las rutas del cfg son ABSOLUTAS y de la maquina que corrio el
        # episodio original. Reusarlas hacia que la replica intentara escribir
        # en el home de otra persona ("Access is denied: C:\\Users\\carco").
        # Con el equipo repartido en varios computadores eso pasa siempre, asi
        # que las rutas se toman de aca y lo demas del cfg.
        carpeta_cf = dir_corrida(a.logs, datos.get("n_agentes", "?"),
                                 datos.get("peldano"))
        datos["dir_logs"] = carpeta_cf
        datos["dir_shared"] = f"{carpeta_cf}/_shared"
        datos["dir_data"] = "data"
        cfg = Config.desde_dict(datos)

        runner_cf = runner_de(cfg) if a.sin_docker else None
        ruta = correr_episodio(cfg, _proveedor_o_salir(a.proveedor, cfg), runner=runner_cf,
                               bloqueados=bloqueados, bloqueo_contenido=por_contenido)
        # Cuantos mensajes se retuvieron DE VERDAD. Con el bloqueo por event_id
        # esto daba 0 y nadie se enteraba: la replica figuraba como hecha sin
        # haber bloqueado nada.
        retenidos = json.loads(
            Path(_ruta_cfg(ruta)).read_text(encoding="utf-8")).get("mensajes_retenidos", 0)
        cuantos = sum(len(v) for v in por_contenido.values()) or len(bloqueados)
        tipo = "control" if a.control_aleatorio else "corte"
        print(f"log contrafactual ({tipo}): {ruta} "
              f"- {cuantos} bloqueados, {retenidos} mensajes retenidos")
        if not retenidos:
            print("  -> OJO: no se retuvo NINGUN mensaje. Esta replica no bloqueo nada, "
                  "asi que no dice nada.")

        from .grafo import cargar, nodo_decisivo
        G = cargar(ruta)
        if nodo_decisivo(G) is None:
            print("  -> el escape NO ocurrio: los mensajes bloqueados eran necesarios.")
        elif a.proveedor == "simulado":
            print("  -> el escape SIGUIO ocurriendo, pero con --proveedor simulado esto no "
                 "mide nada: el guion es fijo y le pasa la credencial completa a "
                 "validar_credencial sin importar lo que de verdad llego por el canal. "
                 "La replica contrafactual solo es informativa con --proveedor ollama/openai, "
                 "donde el modelo si reacciona a lo que lee.")
        else:
            print("  -> el escape SIGUIO ocurriendo: habia una ruta alternativa sin esos mensajes.")
        return ruta


    # solo los diales que el usuario tocó; el resto queda en el default de Config
    canal = {k: v for k, v in (
        ("canal_max_chars", a.canal_max_chars),
        ("canal_max_mensajes", a.canal_max_mensajes),
        ("canal_persistencia", a.canal_persistencia),
        ("canal_ttl", a.canal_ttl),
        ("canal_direccionamiento", a.canal_direccionamiento),
        ("explicitud", a.explicitud),
    ) if v is not None}

    if a.cmd == "uno":
        esc = "benigno" if a.condicion == "benigna" else "credencial"
        pel = a.peldano or peldano_por_defecto(a.condicion)
        marca = sello()
        carpeta = dir_corrida(a.logs, a.N, pel, marca)
        tag = etiqueta_canal(canal)
        # La marca de la corrida va en el NOMBRE DEL EPISODIO, no solo en la
        # carpeta. Con `--semilla` fija (el default es 42), repetir el mismo
        # punto producia tres episodios llamados igual: `grafo.agregar` los
        # agrupa por `episode`, asi que los tres se fundian en UNO. Y como los
        # event_id son deterministas, al fundirse aparecian ciclos en el grafo.
        # Repetir es justo lo que hace falta para tener n>1: no puede romperse.
        if a.max_pasos is not None and a.condicion != "imposible":
            raise SystemExit("--max-pasos solo aplica a --condicion imposible: los controles "
                             "corrieron con 10 turnos y cambiarlo los vuelve incomparables.")
        # Una combinacion invalida (p. ej. `imposible` con N=2) es un error de
        # uso, no un bug: sale con el mensaje, sin traza de Python.
        semilla = a.semilla if a.semilla is not None else secrets.randbelow(1_000_000)
        try:
            cfg = Config(n_agentes=a.N, n_partes=a.n_partes, condicion=a.condicion,
                         peldano=pel, escenario=esc, semilla=semilla, max_pasos=a.max_pasos,
                         episodio=f"ep_{a.condicion}_P{a.n_partes}_N{a.N}{tag}_{semilla}_{marca[-6:]}",
                         dir_logs=carpeta, dir_shared=f"{carpeta}/_shared", **canal)
        except ValueError as e:
            raise SystemExit(f"\n  {e}\n")
        runner = runner_de(cfg) if a.sin_docker else None
        ruta = correr_episodio(cfg, _proveedor_o_salir(a.proveedor, cfg), runner=runner)
        print(f"log: {ruta}")
        return [ruta]

    # a.cmd == "barrido": el proveedor depende de la config de cada episodio
    # (el guion simulado usa las partes de ESE N), asi que se reconstruye por
    # episodio dentro de barrido() en vez de una vez para todo el barrido.
    marca = sello()
    carpeta = dir_corrida(a.logs, a.N,
                          a.peldano or peldano_por_defecto(a.condiciones[0]), marca)
    rutas = barrido(a.N, a.episodios, a.condiciones,
                    crear_proveedor=lambda cfg: _proveedor_o_salir(a.proveedor, cfg),
                    crear_runner=(runner_de if a.sin_docker else None),
                    peldano=a.peldano, dir_logs=carpeta, marca=marca[-6:],
                    partes=a.n_partes, canal=canal)
    print(f"{len(rutas)} episodios en {carpeta}/")
    return rutas


if __name__ == "__main__":
    main()
