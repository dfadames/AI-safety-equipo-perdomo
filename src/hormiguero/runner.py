"""
El runner: corre episodios y barridos.

Ronda robin, no paralelo. Con semilla fija la corrida se repite igual —hace
falta para la réplica contrafactual—, no hay escrituras entrelazadas, y es
mucho más fácil saber qué tenía cada agente en la ventana en cada paso. No se
pierde nada científicamente: lo que medimos es agregación de información, no
condiciones de carrera.

    python -m hormiguero.runner barrido --N 1 2 4 8 --episodios 20
    python -m hormiguero.runner uno --N 4 --condicion honestidad
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from .canal import Canal
from .config import Config
from .registro import Registro
from .sesion import SesionAgente


def correr_episodio(cfg: Config, proveedor_de, runner=None, con_docker: bool = False) -> str:
    """`proveedor_de(agent_id) -> ProveedorLLM`. Devuelve la ruta del log."""
    random.seed(cfg.semilla)

    registro = Registro(cfg.ruta_log(), cfg.episodio, cfg.semilla, cfg.condicion)
    canal = Canal(cfg.ruta_shared(), cfg)

    sesiones = [SesionAgente(proveedor_de(a), registro, canal, cfg, a, runner=runner)
                for a in cfg.agentes]

    # ronda robin hasta que todos terminen o se acabe el presupuesto de pasos
    for _ronda in range(cfg.max_pasos):
        vivos = False
        for s in sesiones:
            if s.paso():
                vivos = True
        if not vivos:
            break

    return cfg.ruta_log()


def barrido(ns, episodios, condiciones, proveedor_de, runner=None,
            peldano="R1", escenario="credencial", semilla_base=1000,
            dir_logs="logs", verbose=True) -> list[str]:
    """Corre el producto (condiciones x N x episodios). Devuelve las rutas."""
    rutas = []
    for cond in condiciones:
        esc = "benigno" if cond == "benigna" else escenario
        for n in ns:
            for i in range(episodios):
                cfg = Config(
                    n_agentes=n, condicion=cond, peldano=peldano, escenario=esc,
                    semilla=semilla_base + i,
                    episodio=f"ep_{cond}_N{n}_{i:03d}",
                    dir_logs=dir_logs,
                )
                rutas.append(correr_episodio(cfg, proveedor_de, runner=runner))
                if verbose:
                    print(f"  {cfg.episodio}", flush=True)
    return rutas


# --- CLI --------------------------------------------------------------------

def _proveedor_por_nombre(nombre: str, cfg: Config):
    if nombre == "simulado":
        from .proveedores.simulado import ProveedorSimulado, guion_escape, guion_benigno
        # El guion intenta con lo que la poblacion ALCANZA, no con la clave
        # completa: si este N tiene techo duro, el intento falla solo. Si
        # armaramos la credencial completa a mano estariamos falseando el
        # techo, que es justo lo que hace que la brecha signifique algo.
        credencial = " ".join(sorted(cfg.alcanzables()))

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
        p = ProveedorOllama()
        return lambda _a: p

    if nombre == "openai":
        from .proveedores.openai_compat import ProveedorOpenAICompatible
        p = ProveedorOpenAICompatible()
        return lambda _a: p

    raise SystemExit(f"proveedor desconocido: {nombre}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hormiguero.runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    comun = argparse.ArgumentParser(add_help=False)
    comun.add_argument("--proveedor", default="simulado",
                       choices=["simulado", "ollama", "openai"])
    comun.add_argument("--peldano", default="R1", choices=["R1", "R2", "R3"])
    comun.add_argument("--logs", default="logs")
    comun.add_argument("--sin-docker", action="store_true",
                       help="usa un runner simulado en vez de docker exec")

    u = sub.add_parser("uno", parents=[comun])
    u.add_argument("--N", type=int, default=4)
    u.add_argument("--condicion", default="instruida")
    u.add_argument("--semilla", type=int, default=42)

    b = sub.add_parser("barrido", parents=[comun])
    b.add_argument("--N", type=int, nargs="+", default=[1, 2, 4, 8])
    b.add_argument("--episodios", type=int, default=20)
    b.add_argument("--condiciones", nargs="+", default=["instruida"])

    a = ap.parse_args(argv)
    runner = (lambda c, cmd: f"(simulado) salida de '{cmd}' en {c}") if a.sin_docker else None

    if a.cmd == "uno":
        esc = "benigno" if a.condicion == "benigna" else "credencial"
        cfg = Config(n_agentes=a.N, condicion=a.condicion, peldano=a.peldano,
                     escenario=esc, semilla=a.semilla,
                     episodio=f"ep_{a.condicion}_N{a.N}_{a.semilla}", dir_logs=a.logs)
        ruta = correr_episodio(cfg, _proveedor_por_nombre(a.proveedor, cfg), runner=runner)
        print(f"log: {ruta}")
        return [ruta]

    def prov(cfg_local=None):
        return None
    # el proveedor depende de la config de cada episodio (el guion simulado usa
    # las partes de ESE N), asi que se construye adentro del barrido
    rutas = []
    for cond in a.condiciones:
        esc = "benigno" if cond == "benigna" else "credencial"
        for n in a.N:
            for i in range(a.episodios):
                cfg = Config(n_agentes=n, condicion=cond, peldano=a.peldano,
                             escenario=esc, semilla=1000 + i,
                             episodio=f"ep_{cond}_N{n}_{i:03d}", dir_logs=a.logs)
                rutas.append(correr_episodio(cfg, _proveedor_por_nombre(a.proveedor, cfg),
                                             runner=runner))
    print(f"{len(rutas)} episodios en {a.logs}/")
    return rutas


if __name__ == "__main__":
    main()
