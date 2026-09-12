@echo off
rem ===================================================================
rem  Corre TODOS los casos del diseno, en orden de valor.
rem
rem    correr_todo.bat --plan        ver que va a correr, sin correr
rem    correr_todo.bat --simulado    ensayo completo, sin llave y sin tokens
rem    correr_todo.bat               correrlo de verdad
rem    correr_todo.bat --solo 2      solo los dos casos mas importantes
rem
rem  Es reanudable: cuenta lo que ya hay en resultados\ y corre solo lo que
rem  falta. Antes de la primera vez, `setup.bat` deja el entorno y la llave
rem  listos; este script NO reinstala nada, solo corre.
rem
rem  Toda la logica esta en CS\hormiguero\plan.py - aca solo se busca Python.
rem ===================================================================

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PY=
for %%C in ("CS\.venv\Scripts\python.exe" "py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PY=%%~C"
  )
)

if not defined PY (
  echo   FALTA PYTHON 3.9+. Corre primero:  setup.bat
  set RC=1
  goto final
)

rem `--no-pause` es de este envoltorio, no de plan.py: se filtra antes de pasar
rem los argumentos o argparse lo rechaza.
set NOPAUSE=0
set ARGS=
:args
if "%~1"=="" goto fin_args
if /i "%~1"=="--no-pause" ( set "NOPAUSE=1" & shift & goto args )
set "ARGS=!ARGS! %1"
shift
goto args
:fin_args

pushd CS
%PY% -m hormiguero.plan !ARGS!
set RC=!errorlevel!
popd

:final
rem Doble clic: la ventana se cierra de golpe al terminar.
if "%NOPAUSE%"=="1" exit /b %RC%
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 (
  echo.
  pause
)
exit /b %RC%
