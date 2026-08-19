@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM  Commodity Options IV Percentile Dashboard - portable launcher
REM  Adapted for migration to other Windows devices (same account)
REM  ASCII only (no chcp needed, safe for any code page)
REM ============================================================

REM 1) Auto-detect WorkBuddy managed Python (any version dir)
set "PY="
for /d %%v in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if exist "%%v\python.exe" set "PY=%%v\python.exe"
)
if not defined PY (
    where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found. Install WorkBuddy or Python 3.10+ first.
    pause
    exit /b 1
)
echo [OK] Using Python: %PY%

REM 2) Switch to script directory so relative paths are correct
set "BASE=%~dp0"
cd /d "%BASE%"

REM 3) Create/reuse project venv; rebuild if unusable (e.g. copied from old device)
set "VENV=%BASE%venv"
set "VPY=%VENV%\Scripts\python.exe"
if not exist "%VPY%" (
    echo [..] Creating virtual environment...
    "%PY%" -m venv "%VENV%"
) else (
    "%VPY%" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo [..] venv unusable from old device, rebuilding...
        rmdir /s /q "%VENV%"
        "%PY%" -m venv "%VENV%"
    )
)

REM 3b) Verify venv usable, else give clear guidance instead of a crash
"%VPY%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Cannot create a usable virtual environment.
    echo        Close other Python windows and rerun this script,
    echo        or delete the venv folder manually and try again.
    pause
    exit /b 1
)

REM 4) Install dependency if missing (openpyxl only; Tsinghua mirror for speed)
"%VPY%" -m pip show openpyxl --disable-pip-version-check >nul 2>&1
if errorlevel 1 (
    echo [..] Installing openpyxl via Tsinghua mirror...
    "%VPY%" -m pip install -q --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple -r "%BASE%requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Dependency install failed. Check network and rerun.
        pause
        exit /b 1
    )
)

REM 5) Start server (auto port; browser opened by server; port auto-released)
echo [..] Starting server, browser will open automatically...
"%VPY%" "%BASE%server.py"
pause
