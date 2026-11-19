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

rem ---- What is on the app's port? (run_check.ps1 explains the answers.) ----
call :look
if "%ON_STATE%"=="mine" goto :already_running
if "%ON_STATE%"=="other" goto :other_copy
if "%ON_STATE%"=="unknown" goto :other_program
goto :not_running

:already_running
echo  The app is already running. Opening it in your browser.
start "" "%ADDRESS%"
exit /b 0

:other_copy
rem Only one copy of the app runs at a time, so that there is one address.
echo.
echo  Another copy of the app is running, from:
echo    %ON_FOLDER%
if defined ON_BUSY echo  It is in the middle of %ON_BUSY%. If you close it, that work
if defined ON_BUSY echo  stops, and carries on the next time that copy is started.
echo.
choice /c YN /n /m " Close it and start this copy instead? (Y/N) "
if errorlevel 2 goto :kept
taskkill /PID %ON_PID% /T /F >nul 2>&1
set "TRIES=0"
:wait_closed
call :look
if "%ON_STATE%"=="free" goto :not_running
set /a TRIES+=1
if %TRIES% geq 10 goto :not_closed
ping -n 2 127.0.0.1 >nul
goto :wait_closed

:kept
echo.
echo  Nothing was changed. The other copy is still running.
pause
exit /b 0

:not_closed
echo.
echo  The other copy could not be closed. Close its black window, then
echo  double-click run.bat again.
pause
exit /b 1

:other_program
echo.
echo  The app cannot start: another program is using its address
echo  (%ADDRESS%).
if defined ON_PROGRAM echo  The program is: %ON_PROGRAM%
echo  Close that program, then double-click run.bat again.
pause
exit /b 1

:look
rem Sets ON_STATE (free, mine, other, unknown) and what goes with it.
for %%v in (STATE FOLDER PID BUSY PROGRAM) do set "ON_%%v="
for /f "usebackq tokens=1,* delims==" %%a in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_check.ps1" %PARKOUR_PORT%`) do set "ON_%%a=%%b"
if not defined ON_STATE set "ON_STATE=free"
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
