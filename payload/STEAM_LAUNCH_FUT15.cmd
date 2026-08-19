@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title FIFA 15 Local FUT (Steam launcher)

rem ------------------------------------------------------------------
rem  Steam-friendly launcher for FIFA 15 Local FUT.
rem
rem  Differences from PLAY_LOCAL_FUT15.cmd, both required by Steam:
rem    1. Never elevates. Steam Input cannot inject into an elevated
rem       fifa15.exe while Steam itself runs unelevated.
rem    2. Blocks until fifa15.exe exits, so Steam keeps the shortcut
rem       marked as running and holds the controller config loaded.
rem
rem  This assumes the game folder is user-writable (it is on this
rem  install). If FIFA is ever moved under Program Files, the server
rem  will fail to write cl.ini / EA-MITM.ini and this script will
rem  report a timeout instead of launching.
rem ------------------------------------------------------------------

if not exist "%~dp0fifa15.exe" (
    echo ERROR: fifa15.exe was not found beside this launcher.
    echo Run PLAY_LOCAL_FUT15.cmd from the release package once first.
    pause
    exit /b 1
)
if not exist "%~dp0localfut15\server.py" (
    echo ERROR: Local FUT payload is not installed in this folder.
    echo Run PLAY_LOCAL_FUT15.cmd from the release package once first.
    pause
    exit /b 1
)
if not exist "%~dp0WAIT_FOR_LOCAL_FUT.ps1" (
    echo ERROR: WAIT_FOR_LOCAL_FUT.ps1 is missing from this folder.
    echo The Local FUT files are incomplete - reinstall the release package.
    pause
    exit /b 1
)

echo ============================================================
echo  FIFA 15 LOCAL FUT - Steam launcher
echo ============================================================
echo  Keep this window open. Closing it does not close the game,
echo  but Steam uses it to track the session.
echo.

call "%~dp0STOP_LOCAL_FUT15.cmd" /quiet >nul 2>nul
taskkill /IM fifa15.exe /F >nul 2>nul

del /q "%LOCALAPPDATA%\FIFA15LocalFUT\startup_phase.txt" >nul 2>nul
echo Starting localhost FUT services...
start "FIFA 15 Local FUT Server" /min cmd /c ""%~dp0START_LOCAL_FUT15.cmd""

echo Waiting for localhost FUT service...
rem Readiness is waited on by WAIT_FOR_LOCAL_FUT.ps1 (shared with
rem PLAY_LOCAL_FUT15.cmd): one process, a real deadline, a stage line every 5s,
rem and an exit code naming the failure. Override the deadline with
rem "set LOCALFUT_WAIT_SECONDS=300" before launching from Steam.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0WAIT_FOR_LOCAL_FUT.ps1"
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" goto :launch

echo.
echo ERROR: Local FUT did not become ready, so FIFA will NOT be launched.
echo.
if "%RC%"=="2" (
    echo The server stopped on its own. Restore the minimised "Local FUT
    echo Server" window to see the exact failing service and port.
)
if "%RC%"=="3" (
    echo The server wrote its port map under a different Windows account.
    echo This launcher deliberately never elevates, so do not start Steam
    echo elevated either - run both as the same normal user.
)
if "%RC%"=="4" (
    echo The server is up but nothing can reach it on localhost. A security
    echo suite or firewall is most likely intercepting loopback connections.
    echo Run PORT_DIAGNOSTICS.cmd and LOCAL_FUT_STATUS.cmd for details.
)
if "%RC%"=="5" (
    echo The server is still installing the Python "cryptography" package.
    echo Run INSTALL_PREREQUISITES.cmd once, let it finish, then relaunch -
    echo the second start is much faster.
)
if "%RC%"=="1" (
    echo Restore the minimised "Local FUT Server" window for the failing port,
    echo or run PORT_DIAGNOSTICS.cmd. If the machine is simply slow, raise the
    echo deadline: set LOCALFUT_WAIT_SECONDS=300 and retry.
)
echo.
pause
exit /b 2

:launch

echo Local FUT is ready. Launching FIFA 15...
start "" /wait "%~dp0fifa15.exe"

rem start /wait can return early if the game re-spawns itself, so confirm
rem the process is really gone before releasing the Steam session.
:wait_for_exit
tasklist /FI "IMAGENAME eq fifa15.exe" 2>nul | find /I "fifa15.exe" >nul
if not errorlevel 1 (
    ping -n 4 127.0.0.1 >nul
    goto :wait_for_exit
)

echo FIFA 15 closed. Shutting down localhost FUT services...
call "%~dp0STOP_LOCAL_FUT15.cmd" /quiet >nul 2>nul
exit /b 0
