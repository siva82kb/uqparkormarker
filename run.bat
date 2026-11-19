@echo off
rem UQ Parkour Annotator: double-click this file to start the app.
rem
rem The first time, it downloads what the app needs (a small tool called uv,
rem then Python and the packages) into the .runtime folder next to this file.
rem Nothing is installed anywhere else on the computer. After that it starts
rem the app and opens it in your browser. Windows only.

setlocal
cd /d "%~dp0"
title UQ Parkour Annotator

rem Everything downloaded stays inside this folder, so deleting the folder
rem removes it all.
set "RUNTIME=%~dp0.runtime"
set "UV=%RUNTIME%\uv.exe"
set "UV_PYTHON_INSTALL_DIR=%RUNTIME%\python"
set "UV_CACHE_DIR=%RUNTIME%\cache"
if not defined PARKOUR_PORT set "PARKOUR_PORT=5000"
set "ADDRESS=http://127.0.0.1:%PARKOUR_PORT%"

rem ---- Is the app already running? Then just open it. ----
powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient('127.0.0.1', %PARKOUR_PORT%)).Close(); exit 0 } catch { exit 1 }"
if errorlevel 1 goto :not_running
echo The app is already running. Opening it in your browser.
start "" "%ADDRESS%"
exit /b 0

:not_running
if exist "%UV%" goto :have_uv
echo.
echo  First start on this computer.
echo  The app will now download what it needs. This needs the internet
echo  and can take a few minutes. Please wait.
echo.
echo  Step 1 of 2: downloading the installer tool...
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = 'Tls12'; $zip = Join-Path $env:RUNTIME 'uv.zip'; Invoke-WebRequest -UseBasicParsing 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' -OutFile $zip; Expand-Archive -Force $zip $env:RUNTIME; Remove-Item $zip"
if not exist "%UV%" goto :no_download
echo  Step 2 of 2: downloading Python and the packages...
goto :set_up

:have_uv
echo  Checking that everything is in place...

:set_up
"%UV%" sync --frozen
if errorlevel 1 goto :no_setup

echo.
echo  The app is starting. Your browser will open in a moment.
echo.
echo  Leave this window open while you work.
echo  To stop the app, close this window.
echo.

rem Open the browser as soon as the app answers (it can take a few seconds).
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 120; $i++) { try { (New-Object Net.Sockets.TcpClient('127.0.0.1', %PARKOUR_PORT%)).Close(); Start-Process '%ADDRESS%'; break } catch { Start-Sleep -Milliseconds 500 } }"

"%UV%" run --frozen python app.py
echo.
echo  The app has stopped.
pause
exit /b 0

:no_download
echo.
echo  The download did not work. Check that this computer is connected to the
echo  internet, then double-click run.bat again.
pause
exit /b 1

:no_setup
echo.
echo  Setting up did not finish. Check that this computer is connected to the
echo  internet, then double-click run.bat again. If it keeps failing, send a
echo  photo of this window to the study team.
pause
exit /b 1
