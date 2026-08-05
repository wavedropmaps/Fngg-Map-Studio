@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo    FNGG Local Map Tool - starting up
echo ==========================================
echo.

REM --- Find Python. "python" on PATH is the common case, but the Windows
REM --- launcher (py) is what you get from python.org installs that skip PATH.
set "PY="
where python >nul 2>&1
if %ERRORLEVEL%==0 set "PY=python"
if not defined PY (
    where py >nul 2>&1
    if !ERRORLEVEL!==0 set "PY=py -3"
)
if not defined PY (
    where python3 >nul 2>&1
    if !ERRORLEVEL!==0 set "PY=python3"
)

if not defined PY (
    echo [ERROR] Python 3 not found on PATH.
    echo.
    echo Install it from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" during setup, then run this again.
    echo.
    pause
    exit /b 1
)

echo Using Python: !PY!

REM --- Warn early if nothing has been downloaded yet. The tool serves tiles
REM --- from this archive, so with no versions it opens to a blank map and
REM --- looks broken - better to say so here than let you wonder why.
set "ARCHIVE=%USERPROFILE%\FNGGMapDownloader"
if not exist "%ARCHIVE%" (
    echo.
    echo [WARNING] No map archive at "%ARCHIVE%".
    echo Run run.bat first and download at least one map version,
    echo otherwise the map will be blank.
    echo.
)

REM --- Open the browser AFTER the server is listening. This used to run before
REM --- the server started, so the first load hit a dead port and you had to
REM --- refresh by hand. This spawns a helper that waits, then opens.
start "" cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:8765"

echo.
echo Server starting at http://127.0.0.1:8765
echo Your browser will open in a moment. Close this window to stop the server.
echo.

!PY! localmaptool\server.py
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] Server exited with code %RC%.
    echo If the port is already in use, another copy may still be running.
    echo.
)

pause
exit /b %RC%
