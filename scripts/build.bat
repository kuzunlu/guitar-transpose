@echo off
rem Build the plugin.  Usage:  scripts\build.bat [Release^|Debug]
rem Output: build\<config>\plugin\TransposePlugin_artefacts\<config>\VST3\Guitar Transpose.vst3
setlocal
set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=Release

call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul || exit /b 1
cd /d "%~dp0.."

cmake -S . -B build\%CONFIG% -G Ninja -DCMAKE_BUILD_TYPE=%CONFIG% || exit /b 2
cmake --build build\%CONFIG% || exit /b 3
