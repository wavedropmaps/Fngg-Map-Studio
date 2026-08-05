@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo    Building FNGG Map Studio .exe
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
    pause
    exit /b 1
)

!PY! -m pip install pyinstaller pywebview Pillow
if not !ERRORLEVEL!==0 (
    echo [ERROR] Dependency install failed.
    pause
    exit /b 1
)

REM Windows locks a running .exe, so PyInstaller's overwrite fails at the very
REM END of the build with a bare "PermissionError: Access is denied" stack trace.
REM Close it up front and say so, rather than burning a few minutes first.
tasklist /fi "IMAGENAME eq FNGGMapStudio.exe" 2>nul | find /i "FNGGMapStudio.exe" >nul
if !ERRORLEVEL!==0 (
    echo Closing a running FNGGMapStudio.exe so the build can overwrite it...
    taskkill /f /im "FNGGMapStudio.exe" >nul 2>&1
    timeout /t 2 /nobreak >nul
)

REM --add-data is what bundles the data files. Without them the exe builds fine
REM and then misbehaves at runtime, because PyInstaller can only infer imported
REM MODULES - it has no idea these exist:
REM   app/static -> the whole frontend; missing it serves a blank page
REM   app/data   -> the known-versions list; missing it empties the version picker
!PY! -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "FNGGMapStudio" ^
    --add-data "app/static;app/static" ^
    --add-data "app/data;app/data" ^
    main.py

set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo Done: dist\FNGGMapStudio.exe
) else (
    echo [ERROR] Build failed with code %RC%.
)
pause
exit /b %RC%
