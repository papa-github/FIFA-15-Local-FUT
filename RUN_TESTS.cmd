@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title FIFA 15 Local FUT - golden tests

rem ------------------------------------------------------------------
rem  Replays recorded FUT requests through route_fut and compares the
rem  responses against the snapshots in tests\golden.
rem
rem  It answers one question: did this change alter what the server
rem  returns? It does NOT check that any response is correct - the
rem  snapshots were recorded from a build that plays properly.
rem
rem  The real club save is never touched: the runner points the server's
rem  runtime root at a temp folder, so each run seeds a fresh database.
rem
rem  Usage:
rem    RUN_TESTS.cmd              verify against the snapshots
rem    RUN_TESTS.cmd --update     re-record (only from a known-good tree)
rem    RUN_TESTS.cmd --only cred  run cases matching "cred"
rem ------------------------------------------------------------------

set "PY="
where py.exe >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python.exe >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo ERROR: Python was not found. Run INSTALL_PREREQUISITES.cmd first.
    pause
    exit /b 1
)

set "RC=0"

rem 1. Undefined names. Fastest check, and the one that catches a refactor
rem    leaving a reference behind when the definition moved to another module.
echo [1/3] undefined-name check
%PY% "%~dp0tests\lint_names.py"
if errorlevel 1 set "RC=1"

rem 2. Recorded FUT responses. Covers route_fut - the FUT HTTP path.
echo.
echo [2/3] golden responses
%PY% "%~dp0tests\golden_runner.py" %*
if errorlevel 1 set "RC=1"

rem 3. LSX handshake. NOT covered by the golden snapshots, and the path whose
rem    breakage freezes FIFA on the language select screen.
echo.
echo [3/3] LSX smoke
%PY% "%~dp0tests\lsx_smoke.py"
if errorlevel 1 set "RC=1"

echo.
if "%RC%"=="0" (
    echo All checks passed.
) else (
    echo One or more checks FAILED - see above.
    echo.
    echo If golden snapshots differ and the change was intentional, re-record
    echo with "RUN_TESTS.cmd --update" and check the git diff before committing.
)

echo.
pause
exit /b %RC%
