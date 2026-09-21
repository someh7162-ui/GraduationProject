@echo off
setlocal
set "ROOT=%~dp0"
start "" /b wscript.exe "%ROOT%scripts\toggle_project.vbs" "%ROOT%"
exit /b 0
