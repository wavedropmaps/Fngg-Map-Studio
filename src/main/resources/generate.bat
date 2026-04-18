@echo off
setlocal

REM Set the directory containing the map images
set "mapDir=maps"

REM Set the output file
set "outputFile=maps_list.txt"

REM Check if the map directory exists
if not exist "%mapDir%" (
    echo The directory "%mapDir%" does not exist.
    exit /b 1
)

REM Create or clear the output file
> "%outputFile%" (
    for /r "%mapDir%" %%f in (*.jpg) do (
        REM Get the relative path of the file
        set "filePath=%%~f"
        setlocal enabledelayedexpansion
        set "relativePath=!filePath:%mapDir%\=!"
        echo !relativePath!
        endlocal
    )
)

echo The maps list has been generated in "%outputFile%".
endlocal