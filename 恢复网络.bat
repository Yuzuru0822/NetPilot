@echo off
setlocal
set "PS1=%~dp0scripts\reset_network.ps1"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%PS1%\"'"
