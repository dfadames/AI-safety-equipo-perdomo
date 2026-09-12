#!/bin/sh
# Configuración del repo. Cada persona lo corre UNA vez, al clonar.
#
#   sh setup.sh
#
set -e

echo "Activando el hook de pre-commit..."
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit 2>/dev/null || true

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Creado .env desde la plantilla — ábrelo y pon tu llave."
else
  echo ".env ya existe, no lo toco."
fi

echo "Verificando que el hook bloquea de verdad..."
TMP=".prueba_hook_$$"
printf 'clave = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"\n' > "$TMP"  # permitido: no-es-secreto
git add -f "$TMP" 2>/dev/null
if sh .githooks/pre-commit >/dev/null 2>&1; then
  echo "  FALLA: el hook no bloqueó una llave de prueba. Avisar al equipo."
  RC=1
else
  echo "  OK: el hook bloquea llaves."
  RC=0
fi
git reset -q HEAD "$TMP" 2>/dev/null || true
rm -f "$TMP"

echo ""
echo "Listo. Recordatorio:"
echo "  - La llave va en .env, que está ignorado por git."
echo "  - Nunca escribas una llave directo en el código: os.environ.get(\"OPENAI_API_KEY\")"
echo "  - Si una llave se sube por accidente: ROTARLA primero. Borrarla del repo no la des-filtra."
exit $RC
