#requires -Version 5
# Launch the FNGG Map Downloader desktop app (PowerShell equivalent of run.bat).

Set-Location $PSScriptRoot

Write-Host '=========================================='
Write-Host '   FNGG Map Downloader - starting up'
Write-Host '=========================================='
Write-Host ''

# The system default "java" on PATH is often too new for Gradle 8.8's Kotlin-DSL
# script compiler, which fails the build before it even starts - so pin JAVA_HOME.
# Matched by wildcard so a patch bump to the Gradle-provisioned JDK doesn't break this.
$jdk = Get-ChildItem -Path (Join-Path $env:USERPROFILE '.gradle\jdks') -Filter '*21*' -Directory -ErrorAction SilentlyContinue |
       ForEach-Object { Get-ChildItem -Path $_.FullName -Directory -ErrorAction SilentlyContinue } |
       Where-Object { Test-Path (Join-Path $_.FullName 'bin\java.exe') } |
       Select-Object -First 1

if (-not $jdk) {
    Write-Host "[ERROR] No JDK 21 found under $env:USERPROFILE\.gradle\jdks" -ForegroundColor Red
    Write-Host ''
    Write-Host 'Gradle normally downloads this automatically on first build.'
    Write-Host 'If it is missing, open the project in IntelliJ IDEA and sync the'
    Write-Host 'Gradle project once - that will provision JDK 21 for you.'
    Write-Host ''
    Read-Host 'Press Enter to close'
    exit 1
}

$env:JAVA_HOME = $jdk.FullName
Write-Host "Using JDK: $env:JAVA_HOME"
Write-Host ''
Write-Host 'Building and launching (first run after a reboot can take 1-2 minutes)...'
Write-Host 'Close the app window to stop.'
Write-Host ''

& .\gradlew.bat run
$rc = $LASTEXITCODE

if ($rc -ne 0) {
    Write-Host ''
    Write-Host "[ERROR] Launch failed with exit code $rc. See the output above." -ForegroundColor Red
    Write-Host ''
    Read-Host 'Press Enter to close'
}

exit $rc
