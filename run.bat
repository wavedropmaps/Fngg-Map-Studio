@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo    FNGG Map Studio
echo ==========================================
echo.

set "PY="
where python >nul 2>&1
if %ERRORLEVEL%==0 set "PY=python"
if not defined PY (
    where py >nul 2>&1
    if !ERRORLEVEL!==0 set "PY=py -3"
)
if not defined PY (
    echo [ERROR] Python 3 not found on PATH.
    echo Install from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH", then run this again.
    echo.
    pause
    exit /b 1
)

!PY! -c "import PIL" >nul 2>&1
if not !ERRORLEVEL!==0 (
    echo Installing dependencies, one moment...
    !PY! -m pip install -r requirements.txt
    echo.
)

!PY! main.py %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [ERROR] Exited with code %RC%.
    pause
)
exit /b %RC%
