@echo off
node "%~dp0runtime.mjs" --apply
if errorlevel 1 pause
