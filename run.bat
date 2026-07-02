@echo off
set "JAVA_HOME=C:\Users\kiere\.gradle\jdks\eclipse_adoptium-21-amd64-windows\jdk-21.0.11+10"
cd /d "%~dp0"
call gradlew.bat run
pause
