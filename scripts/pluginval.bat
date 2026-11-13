@echo off
rem Run pluginval (strictness 10) on the built VST3.  Usage:  scripts\pluginval.bat [Release^|Debug]
rem pluginval 1.0.4 must be unpacked in tools\bin\pluginval-1.0.4 (see docs\DEPENDENCIES.md).
rem The log is written to build\pluginval_<config>.txt
setlocal
set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=Release
cd /d "%~dp0.."

set PV=tools\bin\pluginval-1.0.4\pluginval.exe
set VST=build\%CONFIG%\plugin\TransposePlugin_artefacts\%CONFIG%\VST3\Guitar Transpose.vst3

if not exist "%PV%" ( echo pluginval not found at %PV% & exit /b 1 )
if not exist "%VST%" ( echo plugin not built yet: %VST% & exit /b 1 )

"%PV%" --strictness-level 10 --timeout-ms 300000 --validate "%VST%" > "build\pluginval_%CONFIG%.txt"
set RESULT=%ERRORLEVEL%
findstr /c:"SUCCESS" /c:"FAILED" /c:"!!!" "build\pluginval_%CONFIG%.txt"
exit /b %RESULT%
