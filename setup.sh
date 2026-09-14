#!/bin/sh
# Set the repository up and run one episode. Run it once after cloning, and
# again whenever you want to launch a run.
#
#   sh setup.sh [AGENTS] [RUNG] [--simulated]
#
# It leaves ready: the hook that blocks secrets, the dependencies, the .env,
# and it checks that the DeepSeek key actually answers. If all of that goes
# through, it runs the experiment. `sh setup.sh --help` explains the arguments.
set -e

RC=0
RED=$(printf '\033[31m'); GREEN=$(printf '\033[32m'); GREY=$(printf '\033[90m'); OFF=$(printf '\033[0m')

NUM_AGENTS=4
RUNG=1
SIMULATED=0
POSITIONAL=0

usage() {
  echo "Usage: sh setup.sh [AGENTS] [RUNG] [--simulated]"
  echo
  echo "  AGENTS   how many agents are deployed (default: 4)"
  echo "           The credential is ALWAYS split in 4, whatever goes here."
  echo "             1, 2, 3 -> reach fewer than 4 parts: impossible by design"
  echo "             4       -> reach all 4"
  echo "             8       -> 2 agents per box: redundant routes appear"
  echo
  echo "  RUNG     how much scaffolding the agent gets (default: 1)"
  echo "             1 -> R1: the channel is named and it is asked to pool the parts"
  echo "             2 -> R2: cover task, the channel is mentioned in passing"
  echo "             3 -> R3: the channel is not mentioned at all"
  echo "           R1 guarantees the curves exist; R2 and R3 are where emergent"
  echo "           coordination is measured."
  echo
  echo "  --simulated  fixed script: no key, no network, no tokens spent."
  echo "               Checks that YOUR machine is set up. NOT a result: the"
  echo "               script always opens the vault."
  echo
  echo "Examples:"
  echo "  sh setup.sh              4 agents, R1"
  echo "  sh setup.sh 8 2          8 agents, R2"
  echo "  sh setup.sh 8 3          8 agents, R3 — the paper's bet"
  echo "  sh setup.sh --simulated  check the setup without spending anything"
  echo
  echo "The design's two controls are not rungs and go through the runner:"
  echo "  --condicion honestidad   (the warning confounder)"
  echo "  --condicion benigna      (specificity control)"
}

while [ $# -gt 0 ]; do
  case "$1" in
    -a|--agents)      NUM_AGENTS="$2"; shift 2 ;;
    --agents=*)       NUM_AGENTS="${1#*=}"; shift ;;
    -r|--rung)        RUNG="$2"; shift 2 ;;
    --rung=*)         RUNG="${1#*=}"; shift ;;
    --simulated)      SIMULATED=1; shift ;;
    -h|--help)        usage; exit 0 ;;
    -*)
      printf "%sUnknown option: %s%s\n" "$RED" "$1" "$OFF" >&2
      exit 1 ;;
    *)
      # Positional: 1st agents, 2nd rung.
      POSITIONAL=$((POSITIONAL + 1))
      if [ "$POSITIONAL" -eq 1 ]; then
        NUM_AGENTS="$1"
      elif [ "$POSITIONAL" -eq 2 ]; then
        RUNG="$1"
      else
        printf "%sExtra argument: %s%s\n" "$RED" "$1" "$OFF" >&2
        exit 1
      fi
      shift ;;
  esac
done

case "$NUM_AGENTS" in
  ''|*[!0-9]*|0)
    printf "%sAGENTS must be a positive integer (got '%s')%s\n" "$RED" "$NUM_AGENTS" "$OFF" >&2
    exit 1 ;;
esac

# The rung fixes the PAIR condition+rung. They are not independent axes:
# `instruida` IS R1 and `emergente` IS R2/R3, and Config rejects the mixes. If
# instructed and emergent ran with the same prompt, "emergent coordination"
# would come out as a finding when we had in fact instructed it.
case "$RUNG" in
  1) CONDITION="instruida"; R="R1" ;;
  2) CONDITION="emergente"; R="R2" ;;
  3) CONDITION="emergente"; R="R3" ;;
  *)
    printf "%sRUNG must be 1, 2 or 3 (got '%s')%s\n" "$RED" "$RUNG" "$OFF" >&2
    echo "  sh setup.sh --help" >&2
    exit 1 ;;
esac

# ---------------------------------------------------------------
# 1. The hook that blocks secrets
# ---------------------------------------------------------------
echo "Enabling the pre-commit hook..."
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null || true

# ---------------------------------------------------------------
# 2. Python and dependencies
# ---------------------------------------------------------------
# The project's own venv first, if someone already created it; otherwise any
# system Python that meets the minimum (3.9+) — no exact version required.
ROOT="$(pwd)"
VERSION_OK() {
  $1 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1
}

PY=""
for CANDIDATE in "$ROOT/.venv/bin/python" "$ROOT/.venv/Scripts/python.exe" "python3" "python" "py -3"; do
  if VERSION_OK "$CANDIDATE"; then
    PY="$CANDIDATE"
    break
  fi
done

if [ -z "$PY" ]; then
  printf "%s  PYTHON 3.9+ MISSING%s  install it and run this again.\n" "$RED" "$OFF"
  exit 1
fi
echo "Python: $PY ($($PY -c 'import sys; print(sys.version.split()[0])'))"

echo "Installing dependencies..."
if $PY -m pip install -q -r requirements.txt; then
  echo "  OK"
else
  printf "%s  FAILED: dependencies could not be installed.%s\n" "$RED" "$OFF"
  echo "  Try by hand:  $PY -m pip install -r requirements.txt"
  RC=1
fi

# ---------------------------------------------------------------
# 3. The .env
# ---------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from the template."
else
  echo ".env already exists, leaving it alone."
fi

# ---------------------------------------------------------------
# 4. Check that the hook really blocks
# ---------------------------------------------------------------
echo "Checking that the hook really blocks..."
TMP=".hook_test_$$"
printf 'key = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\n' > "$TMP"  # permitido: no-es-secreto
git add -f "$TMP" 2>/dev/null
if sh .githooks/pre-commit >/dev/null 2>&1; then
  printf "%s  FAILED: the hook did not block a test key.%s\n" "$RED" "$OFF"
  RC=1
else
  echo "  OK: the hook blocks keys."
fi
git reset -q HEAD "$TMP" 2>/dev/null || true
rm -f "$TMP"

# ---------------------------------------------------------------
# 5. Does DeepSeek answer?
# ---------------------------------------------------------------
PROVIDER=""
if [ "$SIMULATED" -eq 1 ]; then
  PROVIDER="--proveedor simulado"
  KEY="(not needed)"
  echo ""
  echo "--simulated mode: fixed script, no key and no tokens spent."
  echo "  Checks that your machine is set up. NOT a result."
else
  KEY=$(grep -E '^DEEPSEEK_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' "'"'"'')
fi

echo ""
if [ "$SIMULATED" -eq 1 ]; then
  :
elif [ -z "$KEY" ]; then
  printf "%sThe key is missing.%s  Open .env and put:\n" "$RED" "$OFF"
  echo ""
  echo "    DEEPSEEK_API_KEY=sk-..."
  echo ""
  echo "  Get one at https://platform.deepseek.com -> API keys"
  echo "  Then run  sh setup.sh  again to check that it works."
  RC=1
else
  echo "Testing the key against DeepSeek..."
  if $PY -m hormiguero.proveedores.deepseek; then
    :
  else
    printf "%s  The key did not work. Read the message above.%s\n" "$RED" "$OFF"
    RC=1
  fi
fi

# ---------------------------------------------------------------
# 6. Run the experiment (if everything above went through)
# ---------------------------------------------------------------
echo ""
if [ "$RC" -eq 0 ]; then
  printf "%sReady.%s Running: %s agents, rung %s (%s)...\n" \
    "$GREEN" "$OFF" "$NUM_AGENTS" "$R" "$CONDITION"
  echo ""

  # Real Docker if the machine has it. It matters: the individual containment
  # audit table can only be backed by real containers, and it is the table
  # behind "every box passed and containment failed anyway".
  if docker info >/dev/null 2>&1; then
    MODE="real containers"
    NO_DOCKER=""
    echo "Docker available: bringing the cluster up..."
    $PY -m hormiguero.runner levantar --n-agentes "$NUM_AGENTS" || RC=1
    $PY -m hormiguero.runner auditar --n-agentes "$NUM_AGENTS" || RC=1
    echo ""
  else
    MODE="EMULATED containment"
    NO_DOCKER="--sin-docker"
    echo "No Docker: the emulated box is used (hormiguero/caja_falsa.py)."
    echo "  Each agent sees ONLY its fragment and transfers still go through the"
    echo "  channel, so the measurement holds. What it does NOT back is the audit"
    echo "  table: that one needs real containers."
    echo ""
  fi

  # No --logs: the runner writes to results/<timestamp>_N<n>/ on its own, which
  # is the folder git does accept. This used to go to runs/, ignored, and the
  # repo got the csv without the traces that back it.
  if $PY -m hormiguero.runner uno --N "$NUM_AGENTS" \
        --condicion "$CONDITION" --peldano "$R" $NO_DOCKER $PROVIDER; then

    # The run just made is the newest folder.
    FOLDER=$(ls -dt "$ROOT"/results/*/ 2>/dev/null | head -1)

    if [ -n "$FOLDER" ]; then
      echo ""
      echo "Analysing the run..."
      # The four questions -> csv, and the map -> page. Chained here so nobody
      # has to remember to run three commands in order.
      $PY -m hormiguero.grafo.agregar "$FOLDER" --csv "${FOLDER}resultados.csv" || RC=1
      $PY -m hormiguero.grafo.mirar "$FOLDER" --salida "${FOLDER}mapa.html" || RC=1

      echo ""
      printf "%sEverything landed in:%s %s\n" "$GREEN" "$OFF" "$FOLDER"
      echo "  the traces (.jsonl), the csv and mapa.html — ready to commit."
      echo "  Mode: $MODE - rung $R ($CONDITION)"
      echo ""
      echo "  Before pushing it, check the csv's 'proveedor' column:"
      echo "    deepseek -> it is a result"
      echo "    simulado -> it is only the wiring, the script always opens the vault"
      echo ""
      echo "  git add results/ && git commit -m \"results: N=$NUM_AGENTS $R\""
    fi
  else
    RC=1
  fi

  if [ "$MODE" = "real containers" ]; then
    $PY -m hormiguero.runner bajar >/dev/null 2>&1 || true
  fi
else
  echo "Once the above is sorted out, run by hand:"
  echo ""
  echo "    python -m hormiguero.runner uno --N $NUM_AGENTS --condicion $CONDITION --peldano $R"
  echo ""
  echo "  Or to check the setup without a key or tokens:  sh setup.sh --simulated"
  echo ""
fi

cat <<'END_HELP'

Other useful commands (from the repository root, all write to results/):

    python -m tests.test_todo                       # everything, no network, no tokens
    python -m hormiguero.runner barrido --N 1 2 4 8 --episodios 3 --sin-docker
    python -m hormiguero.runner uno --N 4 --condicion emergente    # rung R2
    sh run_all.sh --plan                            # the whole design, resumable

By default it runs the `instruida` condition, which is rung R1: the prompt tells
the agent to share its fragment and pool the parts. It makes the curves exist,
but it does NOT measure emergent coordination — for that, `--condicion
emergente` (R2) or `--peldano R3`. In `barrido` the option is `--condiciones`.

The experiment uses the provider in HORMIGUERO_PROVEEDOR (.env). To avoid
spending tokens while testing the wiring:  --proveedor simulado

END_HELP
echo "${GREY}Reminder: the key goes in .env, never in the code. If one is pushed by"
echo "accident: ROTATE IT first — deleting it from the repo does not unleak it.${OFF}"
exit $RC
