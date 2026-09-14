@echo off
rem ===================================================================
rem  Hormiguero - set the repository up + run the experiment.
rem
rem    setup.bat  [AGENTS] [RUNG] [--simulated]      (--help explains)
rem
rem  The setup.sh equivalent for anyone without Git Bash at hand. It does
rem  the same: enables the hook that blocks secrets, installs the
rem  dependencies, creates the .env, checks that the key answers, and if
rem  all of that goes through it runs the experiment and leaves the result
rem  ready to commit in results\<date>_N<n>\
rem
rem  NOTE: if you change something here, change it in setup.sh too.
rem
rem  Plain ASCII on purpose: cmd.exe mangles accents depending on the code
rem  page. The chcp below is for Python's output, not for this.
rem ===================================================================

setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

rem If opened by double click, the current directory is not the repository.
cd /d "%~dp0"

set RC=0
set NUM_AGENTS=4
set RUNG=1
set SIMULATED=0
set NOPAUSE=0
set POS=0

rem --- arguments -----------------------------------------------------
rem The quotes in `set "X=1"` are NOT cosmetic: without them, `set X=1 & shift`
rem stores "1 " WITH the space before the &, and the comparison further down
rem fails silently.
:args
if "%~1"=="" goto end_args
if /i "%~1"=="-a"          ( set "NUM_AGENTS=%~2" & shift & shift & goto args )
if /i "%~1"=="--agents"    ( set "NUM_AGENTS=%~2" & shift & shift & goto args )
if /i "%~1"=="-r"          ( set "RUNG=%~2" & shift & shift & goto args )
if /i "%~1"=="--rung"      ( set "RUNG=%~2" & shift & shift & goto args )
if /i "%~1"=="--simulated" ( set "SIMULATED=1" & shift & goto args )
if /i "%~1"=="--no-pause"  ( set "NOPAUSE=1" & shift & goto args )
if /i "%~1"=="-h"          goto usage
if /i "%~1"=="--help"      goto usage
rem --option=VALUE forms: split on the first "=".
for /f "tokens=1,* delims==" %%A in ("%~1") do (
  if /i "%%~A"=="--agents" ( set "NUM_AGENTS=%%~B" & set "HIT=1" )
  if /i "%%~A"=="--rung"   ( set "RUNG=%%~B"       & set "HIT=1" )
)
if defined HIT ( set "HIT=" & shift & goto args )
echo %~1 | findstr /b /c:"-" >nul
if not errorlevel 1 ( echo Unknown option: %~1 & exit /b 1 )
rem Positional: 1st agents, 2nd rung.
set /a POS+=1
if !POS! equ 1 ( set "NUM_AGENTS=%~1" & shift & goto args )
if !POS! equ 2 ( set "RUNG=%~1"       & shift & goto args )
echo Extra argument: %~1
exit /b 1

:usage
echo Usage: setup.bat [AGENTS] [RUNG] [--simulated] [--no-pause]
echo.
echo   AGENTS    how many agents are deployed (default: 4^)
echo             The credential is ALWAYS split in 4, whatever goes here.
echo               1, 2, 3 -^> reach fewer than 4 parts: impossible by design
echo               4       -^> reach all 4
echo               8       -^> 2 agents per box: redundant routes appear
echo.
echo   RUNG      how much scaffolding the agent gets (default: 1^)
echo               1 -^> R1: the channel is named and it is asked to pool the parts
echo               2 -^> R2: cover task, the channel is mentioned in passing
echo               3 -^> R3: the channel is not mentioned at all
echo             R1 guarantees the curves exist; R2 and R3 are where emergent
echo             coordination is measured.
echo.
echo   --simulated fixed script: no key, no network, no tokens spent.
echo               Checks that YOUR machine is set up.
echo               NOT a result: the script always opens the vault.
echo   --no-pause  do not wait for a key press at the end (for scripts^)
echo.
echo Examples:
echo   setup.bat              4 agents, R1
echo   setup.bat 8 2          8 agents, R2
echo   setup.bat 8 3          8 agents, R3 - the paper's bet
echo   setup.bat --simulated  check the setup without spending anything
echo.
echo The design's two controls are not rungs and go through the runner:
echo   --condicion honestidad   (the warning confounder^)
echo   --condicion benigna      (specificity control^)
exit /b 0
:end_args

echo %NUM_AGENTS%|findstr /r "^[1-9][0-9]*$" >nul
if errorlevel 1 (
  echo AGENTS must be a positive integer ^(got '%NUM_AGENTS%'^)
  echo   setup.bat --help
  exit /b 1
)

rem The rung fixes the PAIR condition+rung. They are not independent axes:
rem `instruida` IS R1 and `emergente` IS R2/R3, and Config rejects the mixes.
rem If instructed and emergent ran with the same prompt, "emergent
rem coordination" would come out as a finding when we had instructed it.
if "%RUNG%"=="1" ( set "CONDITION=instruida" & set "R=R1" ) ^
else if "%RUNG%"=="2" ( set "CONDITION=emergente" & set "R=R2" ) ^
else if "%RUNG%"=="3" ( set "CONDITION=emergente" & set "R=R3" ) ^
else (
  echo RUNG must be 1, 2 or 3 ^(got '%RUNG%'^)
  echo   setup.bat --help
  exit /b 1
)

rem ===================================================================
rem  1. The hook that blocks secrets
rem ===================================================================
echo Enabling the pre-commit hook...
git config core.hooksPath .githooks
if errorlevel 1 (
  echo   FAILED: this does not look like a git repository, or git is not in PATH.
  set RC=1
)

rem ===================================================================
rem  2. Python and dependencies
rem ===================================================================
rem The project's venv first if someone already created it; otherwise any
rem system Python that meets the minimum (3.9+).
set PY=
for %%C in (".venv\Scripts\python.exe" "py -3" "python" "python3") do (
  if not defined PY (
    %%~C -c "import sys; raise SystemExit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "PY=%%~C"
  )
)

if not defined PY (
  echo.
  echo   PYTHON 3.9+ MISSING   install it from https://python.org and run this again.
  echo   In the installer, tick "Add python.exe to PATH".
  set RC=1
  goto final
)

for /f "delims=" %%V in ('%PY% -c "import sys; print(sys.version.split()[0])"') do set PYVER=%%V
echo Python: %PY% (%PYVER%)

echo Installing dependencies...
%PY% -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo   FAILED: dependencies could not be installed.
  echo   Try by hand:  %PY% -m pip install -r requirements.txt
  set RC=1
) else (
  echo   OK
)

rem ===================================================================
rem  3. The .env
rem ===================================================================
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  echo Created .env from the template.
) else (
  echo .env already exists, leaving it alone.
)

rem ===================================================================
rem  4. Check that the hook really blocks
rem ===================================================================
rem The hook is an sh script, and git on Windows runs it with its own sh
rem even if `sh` is not in PATH: if we cannot find it here we only skip the
rem check, the hook will still work on commit. `sh` is almost never in PATH
rem on Windows, but Git ships its own: it is derived from where git.exe is.
rem Worth looking for: this check is what confirms the secret guard works.
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
  echo Hook: cannot find `sh` to test it here, but git will use it anyway.
) else (
  echo Checking that the hook really blocks...
  set "TMPF=.hook_test_%RANDOM%"
  rem The `&rem` goes on THIS same line on purpose: the hook discards line by
  rem line, so the marker on the line above would not save it and the hook
  rem would block this very file.
  echo key = "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA">"!TMPF!" &rem permitido: no-es-secreto
  git add -f "!TMPF!" >nul 2>&1
  "!SH!" .githooks/pre-commit >nul 2>&1
  if !errorlevel! equ 0 (
    echo   FAILED: the hook did not block a test key.
    set RC=1
  ) else (
    echo   OK: the hook blocks keys.
  )
  git reset -q HEAD "!TMPF!" >nul 2>&1
  del /q "!TMPF!" >nul 2>&1
)

rem ===================================================================
rem  5. Does DeepSeek answer?
rem ===================================================================
set PROVIDER=
if "%SIMULATED%"=="1" (
  set "PROVIDER=--proveedor simulado"
  echo.
  echo --simulated mode: fixed script, no key and no tokens spent.
  echo   Checks that your machine is set up. NOT a result.
  goto rc
)

set KEY=
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /c:"DEEPSEEK_API_KEY=" ".env"`) do set "KEY=%%B"

echo.
if "%KEY%"=="" (
  echo The key is missing.  Open .env and put:
  echo.
  echo     DEEPSEEK_API_KEY=sk-...
  echo.
  echo   Get one at https://platform.deepseek.com -^> API keys
  echo   Then run  setup.bat  again to check that it works.
  set RC=1
) else (
  echo Testing the key against DeepSeek...
  %PY% -m hormiguero.proveedores.deepseek
  if errorlevel 1 (
    echo   The key did not work. Read the message above.
    set RC=1
  )
)

rem ===================================================================
rem  6. Run the experiment
rem ===================================================================
rem `--simulated` skips the key, but NOT this check: if pip or the hook
rem failed, the machine is not set up and running anyway says nothing.
:rc
echo.
if not "%RC%"=="0" (
  echo Once the above is sorted out, run by hand:
  echo.
  echo     %PY% -m hormiguero.runner uno --N %NUM_AGENTS% --condicion !CONDITION! --peldano !R!
  echo.
  echo   Or to check the setup without a key or tokens:  setup.bat --simulated
  echo.
  goto final_help
)

echo Ready. Running: %NUM_AGENTS% agents, rung !R! ^(!CONDITION!^)...
echo.

rem Real Docker if the machine has it: the individual containment audit table
rem can only be backed by real containers.
set MODE=EMULATED containment
set NO_DOCKER=--sin-docker
docker info >nul 2>&1
if not errorlevel 1 (
  set "MODE=real containers"
  set "NO_DOCKER="
  echo Docker available: bringing the cluster up...
  rem One box PER AGENT: --n-agentes is what fixes how many come up.
  %PY% -m hormiguero.runner levantar --n-agentes %NUM_AGENTS%
  if errorlevel 1 set RC=1
  %PY% -m hormiguero.runner auditar --n-agentes %NUM_AGENTS%
  if errorlevel 1 set RC=1
  echo.
) else (
  echo No Docker: the emulated box is used ^(hormiguero\caja_falsa.py^).
  echo   Each agent sees ONLY its fragment and transfers still go through the
  echo   channel, so the measurement holds. What it does NOT back is the audit
  echo   table: that one needs real containers.
  echo.
)

rem No --logs: the runner writes to results\<date>_N<n>\ on its own, which is
rem the folder git does accept.
%PY% -m hormiguero.runner uno --N %NUM_AGENTS% --condicion !CONDITION! --peldano !R! !NO_DOCKER! %PROVIDER%
set ERR=!errorlevel!
if not "%ERR%"=="0" (
  set RC=1
  goto final_help
)

rem The run just made is the newest folder in results\
set FOLDER=
for /f "delims=" %%D in ('dir /b /ad /o-d "results" 2^>nul') do (
  if not defined FOLDER set "FOLDER=results\%%D"
)

if not defined FOLDER (
  echo   Cannot find the run folder in results\
  set RC=1
  goto final_help
)

echo.
echo Analysing the run...
rem The four questions -^> csv, and the map -^> page. Chained here so nobody
rem has to remember to run three commands in order.
%PY% -m hormiguero.grafo.agregar "%FOLDER%" --csv "%FOLDER%\resultados.csv"
if errorlevel 1 set RC=1
%PY% -m hormiguero.grafo.mirar "%FOLDER%" --salida "%FOLDER%\mapa.html"
if errorlevel 1 set RC=1

if /i "!MODE!"=="real containers" (
  %PY% -m hormiguero.runner bajar >nul 2>&1
)

echo.
echo Everything landed in: %FOLDER%
echo   the traces (.jsonl), the csv and mapa.html - ready to commit.
echo   Mode: !MODE! - rung !R! ^(!CONDITION!^)
echo.
echo   Before pushing it, check the csv's 'proveedor' column:
echo     deepseek -^> it is a result
echo     simulado -^> it is only the wiring, the script always opens the vault
echo.
echo   git add results/ ^&^& git commit -m "results: N=%NUM_AGENTS% !R!"

:final_help
echo.
echo Other useful commands (from the repository root, all write to results\):
echo.
echo     %PY% -m tests.test_todo                      # everything, no network, no tokens
echo     %PY% -m hormiguero.runner barrido --N 1 2 4 8 --episodios 3 --sin-docker
echo     %PY% -m hormiguero.runner uno --N 4 --condicion emergente   # rung R2
echo     run_all.bat --plan                           # the whole design, resumable
echo.
echo By default it runs the `instruida` condition, which is rung R1: the prompt
echo tells the agent to share its fragment and pool the parts. It makes the
echo curves exist, but it does NOT measure emergent coordination - for that,
echo --condicion emergente (R2) or --peldano R3. In `barrido` it is --condiciones.
echo.
echo The experiment uses the provider in HORMIGUERO_PROVEEDOR (.env). To avoid
echo spending tokens while testing the wiring:  --proveedor simulado
echo.
echo Reminder: the key goes in .env, never in the code. If one is pushed by
echo accident: ROTATE IT first - deleting it from the repo does not unleak it.

:final
rem Double click: cmd starts as `cmd /c ""...\setup.bat" "` and the window
rem closes at once when it finishes. From an open console, %cmdcmdline% is
rem just cmd.exe and there is no need to wait. `--no-pause` forces no wait.
if "%NOPAUSE%"=="1" exit /b %RC%
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 (
  echo.
  pause
)
exit /b %RC%
