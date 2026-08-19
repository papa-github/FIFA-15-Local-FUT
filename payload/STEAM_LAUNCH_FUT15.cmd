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

echo ============================================================
echo  FIFA 15 LOCAL FUT - Steam launcher
echo ============================================================
echo  Keep this window open. Closing it does not close the game,
echo  but Steam uses it to track the session.
echo.

call "%~dp0STOP_LOCAL_FUT15.cmd" /quiet >nul 2>nul
taskkill /IM fifa15.exe /F >nul 2>nul

echo Starting localhost FUT services...
start "FIFA 15 Local FUT Server" /min cmd /c ""%~dp0START_LOCAL_FUT15.cmd""

echo Waiting for localhost FUT service...
set "READY=0"
for /L %%I in (1,1,45) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$f=Join-Path $env:LOCALAPPDATA 'FIFA15LocalFUTuntime_ports.json'; if(-not (Test-Path $f)){exit 1}; try{$p=[int]((Get-Content $f -Raw | ConvertFrom-Json).fut_port); $c=New-Object Net.Sockets.TcpClient; $a=$c.BeginConnect('127.0.0.1',$p,$null,$null); if(-not $a.AsyncWaitHandle.WaitOne(300)){ $c.Close(); exit 1 }; $c.EndConnect($a); $c.Close(); exit 0}catch{exit 1}" >nul 2>nul
    if not errorlevel 1 (
        set "READY=1"
        goto :launch
    )
    ping -n 2 127.0.0.1 >nul
)

:launch
if "%READY%"=="0" (
    echo.
    echo ERROR: Local FUT did not become ready, so FIFA will NOT be launched.
    echo Restore the minimised "Local FUT Server" window to see the failing port.
    echo.
    pause
    exit /b 2
)

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
