@echo off
rem ===================================================================
rem  Run EVERY case of the design, in order of value.
rem
rem    run_all.bat --plan        see what it would run, without running
rem    run_all.bat --simulado    full dry run, no key and no tokens
rem    run_all.bat               run it for real
rem    run_all.bat --solo 2      only the two most important cases
rem
rem  It is resumable: it counts what is already in results\ and runs only
rem  what is missing. Before the first time, `setup.bat` leaves the
rem  environment and the key ready; this script installs NOTHING, it only
rem  runs.
rem
rem  All the logic is in hormiguero\plan.py - here we only look for Python.
rem ===================================================================

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set PY=
for %%C in (".venv\Scripts\python.exe" "py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PY=%%~C"
  )
)

if not defined PY (
  echo   PYTHON 3.9+ MISSING. Run first:  setup.bat
  set RC=1
  goto final
)

rem `--no-pause` belongs to this wrapper, not to plan.py: it is filtered out
rem before passing the arguments through or argparse would reject it.
set NOPAUSE=0
set ARGS=
:args
if "%~1"=="" goto end_args
if /i "%~1"=="--no-pause" ( set "NOPAUSE=1" & shift & goto args )
set "ARGS=!ARGS! %1"
shift
goto args
:end_args

%PY% -m hormiguero.plan !ARGS!
set RC=!errorlevel!

:final
rem Double click: the window closes at once when it finishes.
if "%NOPAUSE%"=="1" exit /b %RC%
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 (
  echo.
  pause
)
exit /b %RC%
