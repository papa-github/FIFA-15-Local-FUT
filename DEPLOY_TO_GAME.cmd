@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title FIFA 15 Local FUT - deploy hook files

rem ------------------------------------------------------------------
rem  Copies ONLY the files that must physically sit in the FIFA 15
rem  install folder:
rem
rem    * dinput8.dll, ItsAMe_Origin.dll, CardsDLLzf.dll
rem      Windows resolves these from fifa15.exe's own directory, so the
rem      hook chain cannot load from anywhere else.
rem    * cards0.big/.bh, data_patch.big/.bh
rem      Asset archives fifa15.exe reads from its own directory.
rem    * EA-MITM.ini, cl.ini
rem      Seed copies. server.py regenerates both at every start.
rem
rem  Everything else stays in this working copy: localfut15\server.py,
rem  its JSON data, and the helper .cmd scripts. server.py locates the
rem  game through install.json (written at the end of this script), so
rem  editing the server needs no redeploy at all.
rem
rem  Usage:
rem    DEPLOY_TO_GAME.cmd                      resolve the folder automatically
rem    DEPLOY_TO_GAME.cmd "C:\Games\FIFA 15"   use an explicit folder
rem    DEPLOY_TO_GAME.cmd /quiet               do not pause on success
rem ------------------------------------------------------------------

set "SRC=%~dp0payload"
set "STATE=%LOCALAPPDATA%\FIFA15LocalFUT"
set "BACKUP=%STATE%\install-backup"
set "INSTALL_JSON=%STATE%\install.json"
set "HOOKFILES=dinput8.dll ItsAMe_Origin.dll CardsDLLzf.dll cards0.big cards0.bh data_patch.big data_patch.bh EA-MITM.ini cl.ini"

set "GAME="
set "QUIET="
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="/quiet" (
    set "QUIET=1"
) else (
    if not defined GAME set "GAME=%~1"
)
shift
goto :parse_args
:args_done

if not exist "%SRC%\dinput8.dll" (
    echo ERROR: The payload folder is missing or incomplete:
    echo   "%SRC%"
    goto :fail
)

rem ---- resolve the FIFA 15 folder ----------------------------------
if not defined GAME if exist "%INSTALL_JSON%" (
    for /f "usebackq delims=" %%G in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "try{(ConvertFrom-Json (Get-Content $env:INSTALL_JSON -Raw)).game_dir}catch{''}"`) do if not defined GAME set "GAME=%%G"
    if defined GAME echo Game folder from install.json.
)

if not defined GAME (
    for /f "usebackq delims=" %%G in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=@(); $reg=@('HKLM:\SOFTWARE\EA Games\FIFA 15','HKLM:\SOFTWARE\WOW6432Node\EA Games\FIFA 15','HKCU:\SOFTWARE\EA Games\FIFA 15'); foreach($r in $reg){try{$p=Get-ItemProperty $r -ErrorAction Stop; foreach($n in 'Install Dir','InstallDir','InstallLocation'){if($p.PSObject.Properties.Name -contains $n){$v=$p.$n; if($v){$c+=$v}}}}catch{}}; $c += @('C:\Games\FIFA 15','C:\Program Files\EA Games\FIFA 15\Game','C:\Program Files\EA Games\FIFA 15','C:\Program Files (x86)\Origin Games\FIFA 15','C:\Program Files\Origin Games\FIFA 15','C:\Program Files (x86)\EA Games\FIFA 15\Game','C:\Program Files (x86)\EA Games\FIFA 15'); foreach($x in $c){if(Test-Path (Join-Path $x 'fifa15.exe')){Write-Output $x; break}; if(Test-Path (Join-Path $x 'Game\fifa15.exe')){Write-Output (Join-Path $x 'Game'); break}}"`) do if not defined GAME set "GAME=%%G"
)

if not defined GAME (
    echo FIFA 15 was not found automatically.
    set /p "GAME=Folder containing fifa15.exe: "
)

if defined GAME if "!GAME:~-1!"=="\" set "GAME=!GAME:~0,-1!"

if not exist "%GAME%\fifa15.exe" (
    echo ERROR: fifa15.exe was not found in:
    echo   "%GAME%"
    goto :fail
)

rem ---- the game folder must be writable by this account -------------
>"%GAME%\.localfut-write-test" echo ok 2>nul
if not exist "%GAME%\.localfut-write-test" (
    echo ERROR: "%GAME%" is not writable by this account.
    echo Right-click DEPLOY_TO_GAME.cmd and choose "Run as administrator",
    echo or move FIFA 15 out of Program Files.
    goto :fail
)
del /q "%GAME%\.localfut-write-test" >nul 2>nul

echo Deploying hook files to: %GAME%
echo.

rem ---- stop anything holding the files open --------------------------
if exist "%SRC%\STOP_LOCAL_FUT15.cmd" call "%SRC%\STOP_LOCAL_FUT15.cmd" /quiet >nul 2>nul
taskkill /IM fifa15.exe /F >nul 2>nul

rem ---- back up the originals, once, before first overwrite -----------
if not exist "%BACKUP%" mkdir "%BACKUP%" >nul 2>nul
for %%F in (%HOOKFILES%) do (
    if exist "%GAME%\%%F" if not exist "%BACKUP%\%%F" copy /y "%GAME%\%%F" "%BACKUP%\%%F" >nul
)

rem ---- copy only what changed ---------------------------------------
robocopy "%SRC%" "%GAME%" %HOOKFILES% /NJH /NJS /NDL /NP /R:1 /W:1 >nul
if errorlevel 8 (
    echo ERROR: Could not copy the hook files into "%GAME%".
    echo Close FIFA 15 and any Local FUT window, then try again.
    goto :fail
)

rem ---- the Cards DLL also lives in the DLC tree, when present --------
set "CARDS_DLC=%GAME%\dlc\dlc_CardsDLL\dlc\CardsDLLzf.dll"
if exist "%CARDS_DLC%" (
    if not exist "%BACKUP%\dlc_CardsDLL" mkdir "%BACKUP%\dlc_CardsDLL" >nul 2>nul
    if not exist "%BACKUP%\dlc_CardsDLL\CardsDLLzf.dll" copy /y "%CARDS_DLC%" "%BACKUP%\dlc_CardsDLL\CardsDLLzf.dll" >nul
    copy /y "%SRC%\CardsDLLzf.dll" "%CARDS_DLC%" >nul
    echo Updated the Cards DLL in the DLC folder as well.
)

rem ---- record where the game lives, for server.py and the launcher ----
if not exist "%STATE%" mkdir "%STATE%" >nul 2>nul
set "JSON_GAME=%GAME%"
set "JSON_PAYLOAD=%SRC%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$o=[ordered]@{game_dir=$env:JSON_GAME; payload_dir=$env:JSON_PAYLOAD; written=(Get-Date).ToString('o')}; Set-Content -LiteralPath $env:INSTALL_JSON -Value (ConvertTo-Json $o) -Encoding utf8"
if not exist "%INSTALL_JSON%" (
    echo ERROR: Could not write "%INSTALL_JSON%".
    goto :fail
)

echo.
echo Done.
echo   Game folder    : %GAME%
echo   Payload stays  : %SRC%
echo   Config written : %INSTALL_JSON%
echo   Originals saved: %BACKUP%
echo.
echo server.py now finds the game through install.json, so editing it
echo here takes effect on the next start with no redeploy.
if defined QUIET exit /b 0
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
