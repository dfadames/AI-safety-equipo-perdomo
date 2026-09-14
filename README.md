# Hormiguero

**Containment Does Not Compose: Provenance Graphs for Tracing Collective Escape
in Multi-Agent Systems.**

A population of LLM agents runs in individually audited containers. Each
container holds one fragment of a credential and nothing else; every container
passes its own containment audit. The agents can post messages to a shared
channel. The experiment measures when the population reassembles the credential
anyway, and reconstructs from the logs a provenance graph that says which
containers the information actually came from.

The report is `paper/AI_Safety_Equipo_Perdomo_Paper.pdf` (source:
`paper/main.tex`). Every number in it is produced by the scripts here from the
logs in `results/`.

---

## Requirements

- Python 3.9+
- Docker, only for runs with real isolation (`--sin-docker` replaces it)
- An API key for the model that drives the agents (DeepSeek by default)

```sh
sh setup.sh          # Windows: setup.bat
```

Once per clone: it enables the pre-commit hook that blocks secrets, installs
the dependencies, creates your `.env` from the template, checks that the key
answers and then runs one episode. `sh setup.sh --help` lists the arguments
(number of agents, rung, `--simulated`).

By hand it is just:

```sh
pip install -r requirements.txt
cp .env.example .env     # then put your DEEPSEEK_API_KEY in it
```

All commands below run from the repository root.

## Check the harness without a key, without Docker, without tokens

The `simulado` provider is a fixed script: it exercises the harness, the
channel and the graph without calling a model. It measures nothing — it only
proves the wiring works.

```sh
python -m tests.test_todo          # the whole system, end to end

python -m hormiguero.runner barrido --N 1 2 4 8 --episodios 3 \
    --sin-docker --proveedor simulado --logs runs
python -m hormiguero.grafo.agregar runs --csv resultados.csv
```

## Run the experiment

1. **Key.** In `.env`, as `DEEPSEEK_API_KEY`. To check it without burning a
   sweep:

   ```sh
   python -m hormiguero.proveedores.deepseek
   ```

2. **Cluster.** Bring the containers up and audit them before spending tokens.
   The audit is the local containment claim the paper then breaks at the
   population level:

   ```sh
   python -m hormiguero.runner levantar --n-agentes 4
   python -m hormiguero.runner auditar  --n-agentes 4
   ```

3. **Episodes.** A single one, to see the whole pipeline move:

   ```sh
   python -m hormiguero.runner uno --N 4
   ```

   Or the full design, which is what produced `results/`. It is resumable: it
   counts what is already in `results/` and runs only what is missing.

   ```sh
   python -m hormiguero.plan --plan        # what it would run, without running
   python -m hormiguero.plan --simulado    # full dry run, no key, no tokens
   python -m hormiguero.plan               # the real thing
   ```

   `sh run_all.sh` (Windows: `run_all.bat`) is the same thing with the Python
   lookup done for you, and takes the same arguments.

4. **Down.**

   ```sh
   python -m hormiguero.runner bajar
   ```

Runs write to `results/` by default — logs, per-episode config and CSVs
together. A CSV without its `.jsonl` cannot be re-checked, so both are kept.

**Watch the size of a sweep.** `--N 1 2 4 8 --episodios 20` is
`(1+2+4+8) × 20 = 300` agent-episodes and up to `max_pasos` calls each: on the
order of 3,000 model calls. Run with `--episodios 2` first.

### The three curves

```sh
# 1. composition gap: escape rate against population size
python -m hormiguero.runner barrido --N 1 2 4 8 --episodios 20

# 2. dilution: per-agent monitor detection against N
python -m hormiguero.monitor results --proveedor deepseek --csv monitor.csv

# 3. warning collapse against decomposition depth
python -m hormiguero.runner barrido --N 4 --n-partes 2 3 4 6 --episodios 20
```

The channel dials (width, persistence, addressing) are swept the same way and
are recorded in every event, so configurations never average into each other:

```sh
python -m hormiguero.runner barrido --N 4 --episodios 20 --canal-max-chars 80
python -m hormiguero.runner barrido --N 4 --episodios 20 --canal-persistencia efimero --canal-ttl 2
python -m hormiguero.runner barrido --N 4 --episodios 20 --canal-direccionamiento punto_a_punto
```

### Counterfactual replica

Block what the critical messages carried and replay the episode, to see whether
the escape was still reachable without them. Each replica needs its random
control, otherwise "the escape collapsed" is also explained by having blocked
messages at all.

```sh
python -m hormiguero.grafo.agregar results --csv resultados.csv   # writes lista_de_bloqueo.json
python -m hormiguero.runner repetir --bloqueo lista_de_bloqueo.json --episodio <episode>
python -m hormiguero.runner repetir --bloqueo lista_de_bloqueo.json --episodio <episode> --control-aleatorio
```

Or both, over the escapes already recorded: `python -m hormiguero.plan --replicas 3`.

Blocking is by content and sender, not by `event_id`: the model is not
deterministic, so the same fragment lands on a different event id on the replay.
The channel counts how many messages it actually withheld
(`mensajes_retenidos`), and `grafo.agregar` warns if that is 0.

## Analysis

```sh
python -m hormiguero.grafo.agregar results --csv resultados.csv  # table + sanity checks
python -m hormiguero.grafo.mirar   results --salida mapa.html    # self-contained page, one episode
python -m hormiguero.figuras                                     # figures, tables and numbers for the paper
python paper/reanalisis_revision.py                              # oracle check, cut decomposition, statistical tests
python paper/baseline_atribucion.py                              # attribution baselines against the graph
```

`grafo.agregar` also runs the sanity checks — unlogged transfers, escapes
without independent verification, a successful N=1 episode (the hard ceiling
must hold). Run it after the first batch, before launching the full sweep.

| Output | What it is |
|---|---|
| `resultados.csv` | One row per episode |
| `resultados_curvas.csv` | One row per `(condition, N)` point — this is what gets plotted |
| `lista_de_bloqueo.json` | Critical messages, input to `runner repetir` |
| `<episode>.cfg.json` | The full config of the episode, next to its log |
| `monitor.csv` | Both monitors, per episode |
| `mapa.html` | The provenance map of an episode, as a standalone page |
| `paper/numeros.md` | Every number quoted in the report, regenerated from the logs |

## Layout

| Path | What it holds |
|---|---|
| `hormiguero/` | The system: harness, channel, containers, providers, provenance graph |
| `hormiguero/config.py` | Single source of truth: key parts, container names, caps, channel dials |
| `hormiguero/runner.py` | Episodes and sweeps; `plan.py` runs the whole design, resumably |
| `hormiguero/grafo/` | Graph construction, the four questions, aggregation, export, the map page |
| `hormiguero/figuras.py` | Figures, LaTeX tables and `paper/numeros.md`, from `results/` |
| `tests/` | `python -m tests.test_todo` — the whole system without Docker, model or network |
| `examples/` | Fixture logs, including a deliberately broken one the oracle must reject |
| `results/` | The released batch: logs, configs and CSVs of the episodes in the paper |
| `paper/` | Report source, figures and the analysis scripts behind its numbers |
| `setup.sh` `setup.bat` | One-shot setup plus one episode, analysed and left in `results/` |
| `run_all.sh` `run_all.bat` | The whole design (`hormiguero.plan`), resumable |

## Secrets

Keys live in `.env` (gitignored). A pre-commit hook blocks commits that contain
one. `setup.sh` enables it; by hand it is:

```sh
git config core.hooksPath .githooks
```

If a key is ever committed, rotate it at the provider first — removing it from
the repo does not unleak it.
