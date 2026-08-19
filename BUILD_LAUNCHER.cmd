@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Build FIFA 15 Local FUT Steam launcher

rem Builds FIFA15LocalFUT.exe from FIFA15LocalFUT_Launcher.cs using the C#
rem compiler that ships with the .NET Framework in Windows. No SDK install and
rem no administrator rights are required.

set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if not exist "%CSC%" (
    echo ERROR: Could not find the .NET Framework C# compiler.
    pause
    exit /b 1
)

rem The game folder supplies the icon, so Steam shows the FIFA artwork.
set "GAME=%~1"
if not defined GAME set "GAME=C:\Games\FIFA 15"
set "ICONARG="
if exist "%GAME%\fifapc.ico" set "ICONARG=/win32icon:"%GAME%\fifapc.ico""

echo Compiling FIFA15LocalFUT.exe...
"%CSC%" /nologo /target:winexe /platform:x86 /optimize+ ^
    /out:"%~dp0FIFA15LocalFUT.exe" ^
    %ICONARG% ^
    /reference:System.dll ^
    /reference:System.Windows.Forms.dll ^
    "%~dp0FIFA15LocalFUT_Launcher.cs"
if errorlevel 1 (
    echo.
    echo ERROR: Build failed.
    pause
    exit /b 2
)

echo Build OK: %~dp0FIFA15LocalFUT.exe
echo.

rem Keep a copy in payload\ so reinstalling the package redeploys the launcher,
rem and drop it straight into the game folder for immediate use.
copy /y "%~dp0FIFA15LocalFUT.exe" "%~dp0payload\FIFA15LocalFUT.exe" >nul
if exist "%GAME%\fifa15.exe" (
    copy /y "%~dp0FIFA15LocalFUT.exe" "%GAME%\FIFA15LocalFUT.exe" >nul
    echo Installed to: %GAME%\FIFA15LocalFUT.exe
) else (
    echo NOTE: "%GAME%" has no fifa15.exe, so nothing was installed there.
    echo       Pass the game folder as an argument to this script.
)

echo.
pause
exit /b 0
