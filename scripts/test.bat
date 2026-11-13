@echo off
rem Build, then run the tp_core unit tests.  Usage:  scripts\test.bat [Release^|Debug]
setlocal
set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=Release
call "%~dp0build.bat" %CONFIG% || exit /b 1
"%~dp0..\build\%CONFIG%\tests\tp_tests.exe"
