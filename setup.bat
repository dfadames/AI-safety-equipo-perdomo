@echo off
rem ===================================================================
rem  Hormiguero - configuracion del repo + corrida del experimento.
rem
rem    setup.bat  [-a N | --num-agentes N]
rem
rem  Es el equivalente de setup.sh para quien no tiene Git Bash a mano.
rem  Hace lo mismo: activa el hook que bloquea secretos, instala las
rem  dependencias, crea el .env, comprueba que la llave responde, y si
rem  todo eso sale bien corre el experimento y deja el resultado listo
rem  para commitear en resultados\<fecha>_N<n>\
rem
rem  OJO: si cambias algo aca, cambialo tambien en setup.sh.
rem
rem  Texto sin tildes a proposito: cmd.exe las rompe segun la pagina de
rem  codigos. El chcp de abajo es para la salida de Python, no para esto.
rem ===================================================================

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

rem Si lo abren con doble clic, el directorio actual no es el del repo.
cd /d "%~dp0"

set RC=0
set NUM_AGENTES=4
set SIMULADO=0
set NOPAUSE=0

rem --- argumentos ----------------------------------------------------
rem Las comillas en `set "X=1"` NO son cosmetica: sin ellas, `set X=1 & shift`
rem guarda "1 " CON el espacio de antes del &, y la comparacion de mas abajo
rem falla en silencio.
:args
if "%~1"=="" goto fin_args
if /i "%~1"=="-a"             ( set "NUM_AGENTES=%~2" & shift & shift & goto args )
if /i "%~1"=="--num-agentes"  ( set "NUM_AGENTES=%~2" & shift & shift & goto args )
if /i "%~1"=="--simulado"     ( set "SIMULADO=1" & shift & goto args )
if /i "%~1"=="--no-pause"     ( set "NOPAUSE=1" & shift & goto args )
if /i "%~1"=="-h"             goto ayuda
if /i "%~1"=="--help"         goto ayuda
echo Opcion desconocida: %~1
exit /b 1
:ayuda
echo Uso: setup.bat [-a N ^| --num-agentes N] [--simulado] [--no-pause]
echo.
echo   -a N        cuantos agentes (por defecto: 4^)
echo   --simulado  corre con el guion fijo: sin llave, sin red y sin gastar
echo               tokens. Sirve para comprobar que TU maquina esta bien
echo               montada. NO es un resultado: el guion siempre abre.
echo   --no-pause  no esperar una tecla al final (para scripts^)
exit /b 0
:fin_args

rem ===================================================================
rem  1. El hook que bloquea secretos
rem ===================================================================
echo Activando el hook de pre-commit...
git config core.hooksPath .githooks
if errorlevel 1 (
  echo   FALLA: esto no parece un repositorio git, o git no esta en el PATH.
  set RC=1
)

rem ===================================================================
rem  2. Python y dependencias
rem ===================================================================
rem Primero el venv del proyecto si alguien ya lo creo; si no, cualquier
rem Python del sistema que llegue al minimo (3.9+).
set PY=
for %%C in ("CS\.venv\Scripts\python.exe" "py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PY=%%~C"
  )
)

if not defined PY (
  echo.
  echo   FALTA PYTHON 3.9+   instalalo desde https://python.org y vuelve a correr esto.
  echo   En el instalador, marca "Add python.exe to PATH".
  set RC=1
  goto final
)

for /f "delims=" %%V in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set PYVER=%%V
echo Python: %PY% (%PYVER%)

echo Instalando dependencias de CS\...
%PY% -m pip install -q -r CS\requirements.txt
if errorlevel 1 (
  echo   FALLA: no se pudieron instalar las dependencias.
  echo   Prueba a mano:  %PY% -m pip install -r CS\requirements.txt
  set RC=1
) else (
  echo   OK
)

rem ===================================================================
rem  3. El .env
rem ===================================================================
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo Creado .env desde la plantilla.
) else (
  echo .env ya existe, no lo toco.
)

rem ===================================================================
rem  4. Verificar que el hook bloquea de verdad
rem ===================================================================
rem El hook es un script sh, y git en Windows lo corre con su propio sh
rem aunque `sh` no este en el PATH: si no lo encontramos aca, solo nos
rem saltamos la comprobacion, el hook igual va a funcionar al commitear.
rem `sh` casi nunca esta en el PATH en Windows, pero Git trae el suyo: se
rem deduce de donde esta git.exe. Vale la pena buscarlo: esta comprobacion
rem es la que confirma que el guardia de secretos de verdad funciona.
set SH=
where sh >nul 2>&1
if not errorlevel 1 set SH=sh
if not defined SH (
  for /f "delims=" %%G in ('where git 2^>nul') do (
    if not defined SH (
      for %%R in ("%%~dpG..") do (
        if exist "%%~fR\bin\sh.exe" set "SH=%%~fR\bin\sh.exe"
      )
    )
  )
)

if not defined SH (
  echo Hook: no encuentro `sh` para probarlo aqui, pero git lo va a usar igual.
) else (
  echo Verificando que el hook bloquea de verdad...
  set "TMPF=.prueba_hook_%RANDOM%"
  rem El `&rem` va en ESTA misma linea a proposito: el hook descarta linea por
  rem linea, asi que el marcador en la linea de arriba no lo salva y el hook
  rem bloquea este propio archivo.
  echo clave = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA">"!TMPF!" &rem permitido: no-es-secreto
  git add -f "!TMPF!" >nul 2>&1
  "!SH!" .githooks/pre-commit >nul 2>&1
  if !errorlevel! equ 0 (
    echo   FALLA: el hook no bloqueo una llave de prueba. Avisar al equipo.
    set RC=1
  ) else (
    echo   OK: el hook bloquea llaves.
  )
  git reset -q HEAD "!TMPF!" >nul 2>&1
  del /q "!TMPF!" >nul 2>&1
)

rem ===================================================================
rem  5. Responde DeepSeek?
rem ===================================================================
set PROV=
if "%SIMULADO%"=="1" (
  set "PROV=--proveedor simulado"
  echo.
  echo Modo --simulado: guion fijo, sin llave y sin gastar tokens.
  echo   Comprueba que tu maquina esta bien montada. NO es un resultado.
  goto correr
)

set LLAVE=
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"DEEPSEEK_API_KEY=" ".env"`) do set "LLAVE=%%B"

echo.
if "%LLAVE%"=="" (
  echo Falta la llave.  Abre .env y pon:
  echo.
  echo     DEEPSEEK_API_KEY=sk-...
  echo.
  echo   La sacas en https://platform.deepseek.com -^> API keys
  echo   Despues vuelve a correr  setup.bat  para comprobar que sirve.
  set RC=1
) else (
  echo Probando la llave contra DeepSeek...
  pushd CS
  %PY% -m hormiguero.proveedores.deepseek
  if errorlevel 1 (
    echo   La llave no funciono. Revisa el mensaje de arriba.
    set RC=1
  )
  popd
)

rem ===================================================================
rem  6. Correr el experimento
rem ===================================================================
echo.
if not "%RC%"=="0" (
  echo Cuando lo de arriba este resuelto, corre a mano:
  echo.
  echo     cd CS ^&^& %PY% -m hormiguero.runner uno --N %NUM_AGENTES% --sin-docker
  echo.
  echo   O para comprobar el montaje sin llave ni tokens:  setup.bat --simulado
  echo.
  goto ayuda_final
)

:correr
echo Listo. Corriendo el experimento con %NUM_AGENTES% agentes...
echo.

rem Sin --logs: el runner escribe solo en resultados\<fecha>_N<n>\, que es
rem la carpeta que git SI acepta.
pushd CS
%PY% -m hormiguero.runner uno --N %NUM_AGENTES% --sin-docker %PROV%
set ERR=!errorlevel!
popd
if not "%ERR%"=="0" (
  set RC=1
  goto ayuda_final
)

rem La corrida recien hecha es la carpeta mas nueva de resultados\
set CARPETA=
for /f "delims=" %%D in ('dir /b /ad /o-d "resultados" 2^>nul') do (
  if not defined CARPETA set "CARPETA=resultados\%%D"
)

if not defined CARPETA (
  echo   No encuentro la carpeta de la corrida en resultados\
  set RC=1
  goto ayuda_final
)

echo.
echo Analizando la corrida...
rem Las cuatro preguntas -^> csv, y el mapa -^> pagina. Encadenado aca para
rem que nadie tenga que acordarse de correr tres comandos en orden.
pushd CS
%PY% -m hormiguero.grafo.agregar "..\%CARPETA%" --csv "..\%CARPETA%\resultados.csv"
if errorlevel 1 set RC=1
%PY% -m hormiguero.grafo.mirar "..\%CARPETA%" --salida "..\%CARPETA%\mapa.html"
if errorlevel 1 set RC=1
popd

echo.
echo Todo quedo en: %CARPETA%
echo   las trazas (.jsonl), el csv y mapa.html - ya se pueden commitear.
echo.
echo   Antes de subirlo, revisa la columna 'proveedor' del csv:
echo     deepseek -^> es un resultado
echo     simulado -^> es solo el cableado, el guion siempre abre la boveda
echo.
echo   git add resultados/ ^&^& git commit -m "resultados: N=%NUM_AGENTES%"

:ayuda_final
echo.
echo Otros comandos utiles (desde CS\, todos escriben solos en resultados\):
echo.
echo     %PY% -m tests.test_todo                      # todo, sin red ni tokens
echo     %PY% -m hormiguero.runner barrido --N 1 2 4 8 --episodios 3 --sin-docker
echo     %PY% -m hormiguero.runner uno --N 4 --condicion emergente   # el peldano R2
echo.
echo Por defecto corre la condicion `instruida`, que es el peldano R1: el prompt
echo le dice al agente que comparta su fragmento y reuna las partes. Sirve para
echo que las curvas existan, pero NO mide coordinacion emergente - para eso,
echo --condicion emergente (R2) o --peldano R3. En `barrido` es --condiciones.
echo.
echo El experimento usa el proveedor de HORMIGUERO_PROVEEDOR (.env). Para no
echo gastar tokens mientras se prueba el cableado:  --proveedor simulado
echo.
echo Recordatorio: la llave va en .env, nunca en el codigo. Si se sube por
echo accidente: ROTARLA primero - borrarla del repo no la des-filtra.

:final
rem Doble clic: cmd arranca como `cmd /c ""...\setup.bat" "` y la ventana se
rem cierra de golpe al terminar. Desde una consola abierta, %cmdcmdline% es
rem solo cmd.exe y no hace falta esperar. `--no-pause` fuerza no esperar.
if "%NOPAUSE%"=="1" exit /b %RC%
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 (
  echo.
  pause
)
exit /b %RC%
