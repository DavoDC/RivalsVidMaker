@echo off
cd /d "%~dp0.."
set "PYTHONPATH=%CD%\src"
where pythonw >nul 2>nul
if not errorlevel 1 goto run
echo Python was not found on PATH. Install Python 3.10 or newer, then run this file again.
goto end
:run
pythonw -m gui --launch %*
:end
exit /b 0
