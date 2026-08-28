@echo off
rem Dvojklik spusti stanici bez Dockeru. Parametry se predaji dal:
rem   DinoStanice.cmd -Port 8123 -NoBrowser
title DinoStanice
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 pause
