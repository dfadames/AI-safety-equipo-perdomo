#!/bin/sh
# Corre TODOS los casos del diseño, en orden de valor.
#
#   sh correr_todo.sh --plan        ver qué va a correr, sin correr
#   sh correr_todo.sh --simulado    ensayo completo, sin llave y sin tokens
#   sh correr_todo.sh               correrlo de verdad
#   sh correr_todo.sh --solo 2      solo los dos casos más importantes
#
# Es reanudable: cuenta lo que ya hay en resultados/ y corre solo lo que falta.
#
# Antes de la primera vez, `sh setup.sh` deja el entorno y la llave listos.
# Este script NO reinstala nada: solo corre.
#
# Toda la lógica está en CS/hormiguero/plan.py — acá solo se busca un Python.
set -e

cd "$(dirname "$0")"
ROOT="$(pwd)"

PY=""
for CANDIDATO in "$ROOT/CS/.venv/bin/python" "$ROOT/CS/.venv/Scripts/python.exe" "python3" "python" "py -3"; do
  if $CANDIDATO -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1; then
    PY="$CANDIDATO"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "  FALTA PYTHON 3.9+. Corre primero:  sh setup.sh"
  exit 1
fi

cd CS
exec $PY -m hormiguero.plan "$@"
