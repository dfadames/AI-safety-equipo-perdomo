#!/bin/sh
# Configuración del repo + corrida del experimento. Cada persona lo corre
# UNA vez al clonar, y de nuevo cuando quiera lanzar un barrido.
#
#   sh setup.sh [AGENTES] [PELDAÑO] [--simulado]
#
# Deja listo: el hook que bloquea secretos, las dependencias, el .env, y
# comprueba que la llave de DeepSeek de verdad responde. Si todo eso sale
# bien, corre el experimento. `sh setup.sh --help` explica los argumentos.
set -e

RC=0
ROJO=$(printf '\033[31m'); VERDE=$(printf '\033[32m'); GRIS=$(printf '\033[90m'); FIN=$(printf '\033[0m')

NUM_AGENTES=4
PELDANO=1
SIMULADO=0
POSICIONALES=0

ayuda() {
  echo "Uso: sh setup.sh [AGENTES] [PELDAÑO] [--simulado]"
  echo
  echo "  AGENTES   cuántos agentes se despliegan (por defecto: 4)"
  echo "            La clave SIEMPRE se parte en 4, pase lo que pase aquí."
  echo "              1, 2, 3 -> alcanzan menos de 4 partes: imposible por diseño"
  echo "              4       -> alcanzan las 4"
  echo "              8       -> 2 agentes por caja: aparecen rutas redundantes"
  echo
  echo "  PELDAÑO   cuánto andamiaje recibe el agente (por defecto: 1)"
  echo "              1 -> R1: se le nombra el canal y se le pide reunir las partes"
  echo "              2 -> R2: tarea de fachada, el canal se menciona de pasada"
  echo "              3 -> R3: ni siquiera se menciona el canal"
  echo "            R1 garantiza que las curvas existan; R2 y R3 son donde se"
  echo "            mide si la coordinación es emergente."
  echo
  echo "  --simulado  guion fijo: sin llave, sin red y sin gastar tokens."
  echo "              Comprueba que TU máquina está bien montada."
  echo "              NO es un resultado: el guion siempre abre la bóveda."
  echo
  echo "Ejemplos:"
  echo "  sh setup.sh              4 agentes, R1"
  echo "  sh setup.sh 8 2          8 agentes, R2"
  echo "  sh setup.sh 8 3          8 agentes, R3 — la apuesta del paper"
  echo "  sh setup.sh --simulado   comprobar el montaje sin gastar nada"
  echo
  echo "Los dos controles del diseño no son peldaños y van por el runner:"
  echo "  --condicion honestidad   (confundidor del aviso)"
  echo "  --condicion benigna      (control de especificidad)"
}

while [ $# -gt 0 ]; do
  case "$1" in
    -a|--num-agentes)   NUM_AGENTES="$2"; shift 2 ;;
    --num-agentes=*)    NUM_AGENTES="${1#*=}"; shift ;;
    -r|--peldano)       PELDANO="$2"; shift 2 ;;
    --peldano=*)        PELDANO="${1#*=}"; shift ;;
    --simulado)         SIMULADO=1; shift ;;
    -h|--help)          ayuda; exit 0 ;;
    -*)
      printf "%sOpción desconocida: %s%s\n" "$ROJO" "$1" "$FIN" >&2
      exit 1 ;;
    *)
      # Posicionales: 1º agentes, 2º peldaño.
      POSICIONALES=$((POSICIONALES + 1))
      if [ "$POSICIONALES" -eq 1 ]; then
        NUM_AGENTES="$1"
      elif [ "$POSICIONALES" -eq 2 ]; then
        PELDANO="$1"
      else
        printf "%sSobra el argumento: %s%s\n" "$ROJO" "$1" "$FIN" >&2
        exit 1
      fi
      shift ;;
  esac
done

case "$NUM_AGENTES" in
  ''|*[!0-9]*|0)
    printf "%sAGENTES tiene que ser un entero positivo (llegó '%s')%s\n" "$ROJO" "$NUM_AGENTES" "$FIN" >&2
    exit 1 ;;
esac

# El peldaño fija la PAREJA condición+peldaño. No son ejes independientes:
# `instruida` ES R1 y `emergente` ES R2/R3, y Config rechaza las mezclas. Si se
# corrieran instruida y emergente con el mismo prompt, la "coordinación
# emergente" saldría como hallazgo cuando en realidad se la habíamos instruido.
case "$PELDANO" in
  1) CONDICION="instruida"; PEL="R1" ;;
  2) CONDICION="emergente"; PEL="R2" ;;
  3) CONDICION="emergente"; PEL="R3" ;;
  *)
    printf "%sPELDAÑO tiene que ser 1, 2 o 3 (llegó '%s')%s\n" "$ROJO" "$PELDANO" "$FIN" >&2
    echo "  sh setup.sh --help" >&2
    exit 1 ;;
esac

# ---------------------------------------------------------------
# 1. El hook que bloquea secretos
# ---------------------------------------------------------------
echo "Activando el hook de pre-commit..."
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null || true

# ---------------------------------------------------------------
# 2. Python y dependencias
# ---------------------------------------------------------------
# Primero el venv propio del proyecto (CS/.venv, si alguien ya lo creó);
# si no existe, cualquier Python del sistema que alcance el mínimo del
# proyecto (3.9+) sirve — no exigimos una versión exacta como 3.11.
ROOT="$(pwd)"
VERSION_OK() {
  $1 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >/dev/null 2>&1
}

PY=""
for CANDIDATO in "$ROOT/CS/.venv/bin/python" "$ROOT/CS/.venv/Scripts/python.exe" "python3" "python" "py -3"; do
  if VERSION_OK "$CANDIDATO"; then
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
PROV=""
if [ "$SIMULADO" -eq 1 ]; then
  PROV="--proveedor simulado"
  LLAVE="(no hace falta)"
  echo ""
  echo "Modo --simulado: guion fijo, sin llave y sin gastar tokens."
  echo "  Comprueba que tu máquina está bien montada. NO es un resultado."
else
  LLAVE=$(grep -E '^DEEPSEEK_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d ' "'"'"'')
fi

echo ""
if [ "$SIMULADO" -eq 1 ]; then
  :
elif [ -z "$LLAVE" ]; then
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
# 6. Correr el experimento (si todo lo de arriba salió bien)
# ---------------------------------------------------------------
echo ""
if [ "$RC" -eq 0 ]; then
  printf "%sListo.%s Corriendo: %s agentes, peldaño %s (%s)...\n" \
    "$VERDE" "$FIN" "$NUM_AGENTES" "$PEL" "$CONDICION"
  echo ""

  # Docker de verdad si la máquina lo tiene. Importa: la tabla de auditoría de
  # contención individual solo se puede respaldar con contenedores reales, y es
  # la que sostiene la frase «las cajas aprobaron y la contención falló igual».
  if docker info >/dev/null 2>&1; then
    MODO="contenedores reales"
    SIN_DOCKER=""
    echo "Docker disponible: levantando el clúster..."
    (cd CS && $PY -m hormiguero.runner levantar --n-partes 4) || RC=1
    (cd CS && $PY -m hormiguero.runner auditar --n-partes 4) || RC=1
    echo ""
  else
    MODO="contención EMULADA"
    SIN_DOCKER="--sin-docker"
    echo "Sin Docker: se usa la caja emulada (hormiguero/caja_falsa.py)."
    echo "  Cada agente ve SOLO su fragmento y las transferencias siguen pasando"
    echo "  por el canal, así que la medición vale. Lo que NO respalda es la tabla"
    echo "  de auditoría: esa necesita contenedores de verdad."
    echo ""
  fi

  # Sin --logs: el runner escribe solo en resultados/<timestamp>_N<n>/, que es
  # la carpeta que git SÍ acepta. Antes esto iba a runs/, ignorada, y al repo
  # llegaba el csv sin las trazas que lo respaldan.
  if (cd CS && $PY -m hormiguero.runner uno --N "$NUM_AGENTES" \
        --condicion "$CONDICION" --peldano "$PEL" $SIN_DOCKER $PROV); then

    # La corrida recién hecha es la carpeta más nueva.
    CARPETA=$(ls -dt "$ROOT"/resultados/*/ 2>/dev/null | head -1)

    if [ -n "$CARPETA" ]; then
      echo ""
      echo "Analizando la corrida..."
      # Las cuatro preguntas -> csv, y el mapa -> pagina. Encadenado aca para
      # que nadie tenga que acordarse de correr tres comandos en orden.
      (cd CS && $PY -m hormiguero.grafo.agregar "$CARPETA" --csv "${CARPETA}resultados.csv") || RC=1
      (cd CS && $PY -m hormiguero.grafo.mirar "$CARPETA" --salida "${CARPETA}mapa.html") || RC=1

      echo ""
      printf "%sTodo quedó en:%s %s\n" "$VERDE" "$FIN" "$CARPETA"
      echo "  las trazas (.jsonl), el csv y mapa.html — ya se pueden commitear."
      echo "  Modo: $MODO - peldaño $PEL ($CONDICION)"
      echo ""
      echo "  Antes de subirlo, revisa la columna 'proveedor' del csv:"
      echo "    deepseek -> es un resultado"
      echo "    simulado -> es solo el cableado, el guion siempre abre la bóveda"
      echo ""
      echo "  git add resultados/ && git commit -m \"resultados: N=$NUM_AGENTES $PEL\""
    fi
  else
    RC=1
  fi

  if [ "$MODO" = "contenedores reales" ]; then
    (cd CS && $PY -m hormiguero.runner bajar) >/dev/null 2>&1 || true
  fi
else
  echo "Cuando lo de arriba esté resuelto, corre a mano:"
  echo ""
  echo "    cd CS && python -m hormiguero.runner uno --N $NUM_AGENTES --condicion $CONDICION --peldano $PEL"
  echo ""
  echo "  O para comprobar el montaje sin llave ni tokens:  sh setup.sh --simulado"
  echo ""
fi

cat <<'FIN_AYUDA'

Otros comandos útiles (desde CS/, todos escriben solos en resultados/):

    python -m tests.test_todo                       # todo, sin red ni tokens
    python -m hormiguero.runner barrido --N 1 2 4 8 --episodios 3 --sin-docker
    python -m hormiguero.runner uno --N 4 --condicion emergente    # el peldaño R2

Por defecto corre la condición `instruida`, que es el peldaño R1: el prompt le
dice al agente que comparta su fragmento y reúna las partes. Sirve para que las
curvas existan, pero NO mide coordinación emergente — para eso, `--condiciones
emergente` (R2) o `--peldano R3`. En `barrido` la opción es `--condiciones`.

El experimento usa el proveedor de HORMIGUERO_PROVEEDOR (.env). Para no gastar
tokens mientras se prueba el cableado:  --proveedor simulado

FIN_AYUDA
echo "${GRIS}Recordatorio: la llave va en .env, nunca en el código. Si se sube por"
echo "accidente: ROTARLA primero — borrarla del repo no la des-filtra.${FIN}"
exit $RC
