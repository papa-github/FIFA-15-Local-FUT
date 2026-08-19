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

%PY% "%~dp0tests\golden_runner.py" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo Snapshots differ from what the server returns now.
    echo If the change was intentional, re-record with:
    echo   RUN_TESTS.cmd --update
    echo and check the resulting git diff before committing it.
)

echo.
pause
exit /b %RC%
