@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==========================================
echo    FNGG Map Downloader - starting up
echo ==========================================
echo.

REM ---------------------------------------------------------------
REM Find a JDK 21. The system default "java" on PATH is often too new
REM for Gradle 8.8's Kotlin-DSL script compiler, which makes the build
REM fail before it even starts - so we pin JAVA_HOME explicitly.
REM
REM Searched by wildcard rather than an exact version so this keeps
REM working when the Gradle-provisioned JDK gets a patch update.
REM ---------------------------------------------------------------
set "JDK="

for /d %%A in ("%USERPROFILE%\.gradle\jdks\*21*") do (
    for /d %%B in ("%%~fA\*") do (
        if exist "%%~fB\bin\java.exe" set "JDK=%%~fB"
    )
)

if not defined JDK (
    echo [ERROR] No JDK 21 found under "%USERPROFILE%\.gradle\jdks".
    echo.
    echo Gradle normally downloads this automatically on first build.
    echo If it is missing, open the project in IntelliJ IDEA and sync the
    echo Gradle project once - that will provision JDK 21 for you.
    echo.
    pause
    exit /b 1
)

set "JAVA_HOME=%JDK%"
echo Using JDK: %JAVA_HOME%
echo.
echo Building and launching (first run after a reboot can take 1-2 minutes)...
echo Close the app window to stop.
echo.

call "%~dp0gradlew.bat" run
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo [ERROR] Launch failed with exit code %RC%. See the output above.
    echo.
    pause
)

exit /b %RC%
