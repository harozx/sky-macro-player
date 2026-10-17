@echo off
setlocal
chcp 65001 >nul
title Sky Macro Player - Setup

pushd "%~dp0" || (
    echo [ERROR] Cannot open the application directory.
    pause
    exit /b 1
)

echo ==================================================
echo    SKY MACRO PLAYER - LOCAL SETUP
echo ==================================================
echo.
echo This setup creates an isolated .venv for this app.
echo It does not require Administrator rights.
echo.

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] Python 3.10 or newer was not found.
    echo Install Python from https://www.python.org/downloads/
    echo Enable "Add Python to PATH", then run setup.bat again.
    echo.
    pause
    popd
    exit /b 1
)

echo [1/3] Creating or repairing .venv...
%PYTHON_CMD% -m venv ".venv"
if errorlevel 1 goto :SetupFailed

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] The virtual environment was not created correctly.
    goto :SetupFailed
)

echo [2/3] Installing pinned dependencies...
".venv\Scripts\python.exe" -m pip install --requirement "requirements.txt"
if errorlevel 1 goto :SetupFailed

echo [3/3] Verifying the application runtime...
".venv\Scripts\python.exe" -c "import PySide6, pynput; print('Runtime verification passed.')"
if errorlevel 1 goto :SetupFailed

echo.
echo [OK] Setup completed. Starting Sky Macro Player...
start "" wscript.exe "%~dp0start.vbs"
popd
exit /b 0

:SetupFailed
echo.
echo [ERROR] Setup did not complete.
echo Check the messages above, your network connection, and available disk space.
echo No global Python packages were changed.
echo.
pause
popd
exit /b 1
