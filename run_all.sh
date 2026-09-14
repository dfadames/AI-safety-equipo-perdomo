#!/bin/sh
# Run EVERY case of the design, in order of value.
#
#   sh run_all.sh --plan        see what it would run, without running
#   sh run_all.sh --simulado    full dry run, no key and no tokens
#   sh run_all.sh               run it for real
#   sh run_all.sh --solo 2      only the two most important cases
#
# It is resumable: it counts what is already in results/ and runs only what is
# missing.
#
# Before the first time, `sh setup.sh` leaves the environment and the key
# ready. This script installs NOTHING: it only runs.
#
# All the logic is in hormiguero/plan.py — here we only look for a Python.
set -e

cd "$(dirname "$0")"
ROOT="$(pwd)"

PY=""
for CANDIDATE in "$ROOT/.venv/bin/python" "$ROOT/.venv/Scripts/python.exe" "python3" "python" "py -3"; do
  if $CANDIDATE -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1; then
    PY="$CANDIDATE"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "  PYTHON 3.9+ MISSING. Run first:  sh setup.sh"
  exit 1
fi

exec $PY -m hormiguero.plan "$@"
