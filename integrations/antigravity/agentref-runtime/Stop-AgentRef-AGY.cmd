@echo off
node "%~dp0runtime.mjs" --stop
if errorlevel 1 pause
