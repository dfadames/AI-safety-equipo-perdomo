#!/bin/sh
# Configuración del repo. Cada persona lo corre UNA vez, al clonar.
#
#   sh setup.sh
#
# Deja listo: el hook que bloquea secretos, las dependencias, el .env, y
# comprueba que la llave de DeepSeek de verdad responde. Después de esto lo
# único que falta es pegar la llave en .env.
set -e

RC=0
ROJO=$(printf '\033[31m'); VERDE=$(printf '\033[32m'); GRIS=$(printf '\033[90m'); FIN=$(printf '\033[0m')

# ---------------------------------------------------------------
# 1. El hook que bloquea secretos
# ---------------------------------------------------------------
echo "Activando el hook de pre-commit..."
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null || true

# ---------------------------------------------------------------
# 2. Python y dependencias
# ---------------------------------------------------------------
# En Windows el lanzador es `py`; en Linux/Mac, `python3`. Se prueba en orden
# y gana el primero que arranque, para no pedirle a nadie que edite esto.
PY=""
for CANDIDATO in "py -3.11" "py -3" "python3" "python"; do
  if $CANDIDATO -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1; then
    PY="$CANDIDATO"
    break
  fi
done

if [ -z "$PY" ]; then
  printf "%s  FALTA PYTHON 3.9+%s  instálalo y vuelve a correr esto.\n" "$ROJO" "$FIN"
  exit 1
fi
echo "Python: $PY ($($PY -c 'import sys; print(sys.version.split()[0])'))"

echo "Instalando dependencias de CS/..."
if $PY -m pip install -q -r CS/requirements.txt; then
  echo "  OK"
else
  printf "%s  FALLA: no se pudieron instalar las dependencias.%s\n" "$ROJO" "$FIN"
  echo "  Prueba a mano:  $PY -m pip install -r CS/requirements.txt"
  RC=1
fi

# ---------------------------------------------------------------
# 3. El .env
# ---------------------------------------------------------------
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env desde la plantilla."
else
  echo ".env ya existe, no lo toco."
fi

# ---------------------------------------------------------------
# 4. Verificar que el hook bloquea de verdad
# ---------------------------------------------------------------
echo "Verificando que el hook bloquea de verdad..."
TMP=".prueba_hook_$$"
printf 'clave = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\n' > "$TMP"  # permitido: no-es-secreto
git add -f "$TMP" 2>/dev/null
if sh .githooks/pre-commit >/dev/null 2>&1; then
  printf "%s  FALLA: el hook no bloqueó una llave de prueba. Avisar al equipo.%s\n" "$ROJO" "$FIN"
  RC=1
else
  echo "  OK: el hook bloquea llaves."
fi
git reset -q HEAD "$TMP" 2>/dev/null || true
rm -f "$TMP"

# ---------------------------------------------------------------
# 5. ¿Responde DeepSeek?
# ---------------------------------------------------------------
LLAVE=$(grep -E '^DEEPSEEK_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' "'"'"'')

echo ""
if [ -z "$LLAVE" ]; then
  printf "%sFalta la llave.%s  Abre .env y pon:\n" "$ROJO" "$FIN"
  echo ""
  echo "    DEEPSEEK_API_KEY=sk-..."
  echo ""
  echo "  La sacas en https://platform.deepseek.com -> API keys"
  echo "  Después vuelve a correr  sh setup.sh  para comprobar que sirve."
  RC=1
else
  echo "Probando la llave contra DeepSeek..."
  if (cd CS && $PY -m hormiguero.proveedores.deepseek); then
    :
  else
    printf "%s  La llave no funcionó. Revisa el mensaje de arriba.%s\n" "$ROJO" "$FIN"
    RC=1
  fi
fi

# ---------------------------------------------------------------
# 6. Qué sigue
# ---------------------------------------------------------------
echo ""
if [ "$RC" -eq 0 ]; then
  printf "%sListo.%s Para correr:\n" "$VERDE" "$FIN"
else
  echo "Cuando lo de arriba esté resuelto, para correr:"
fi
cat <<'FIN_AYUDA'

    cd CS
    python -m tests.test_todo                                  # todo, sin red ni tokens
    python -m hormiguero.runner barrido --N 1 2 4 8 --sin-docker --logs runs
    python -m hormiguero.grafo.agregar runs --csv runs/resultados.csv
    python -m hormiguero.grafo.mirar runs --salida runs/mapa.html

El barrido usa el proveedor de HORMIGUERO_PROVEEDOR (.env). Para no gastar
tokens mientras se prueba el cableado:  --proveedor simulado

FIN_AYUDA
echo "${GRIS}Recordatorio: la llave va en .env, nunca en el código. Si se sube por"
echo "accidente: ROTARLA primero — borrarla del repo no la des-filtra.${FIN}"
exit $RC
