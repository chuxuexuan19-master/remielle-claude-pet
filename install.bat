@echo off
rem Xiaolemi desktop pet - one-time setup on this computer (registers the Claude Code hooks)
rem Just double-click. It finds a Python, then hands over to install_hooks.py
rem NOTE: keep this file ASCII-only. cmd parses .bat in the system codepage,
rem       and multi-byte UTF-8 here breaks the parser.
cd /d "%~dp0"

set "PY="

rem 1) previously recorded interpreter
if exist "python.txt" set /p PY=<python.txt
if defined PY if not exist "%PY%" set "PY="

rem 2) the py launcher is the most reliable
if not defined PY where py >nul 2>nul && set "PY=py"

rem 3) pythonw / python on PATH, skipping the Microsoft Store stub
if not defined PY for /f "delims=" %%i in ('where pythonw 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%i"
if not defined PY for /f "delims=" %%i in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PY set "PY=%%i"

if not defined PY (
  echo.
  echo   Python not found on this computer.
  echo.
  echo   Install Miniconda or Anaconda, or the official Python
  echo   [tick "Add Python to PATH" during setup], then double-click
  echo   this file again.
  echo.
  echo   Miniconda: https://docs.conda.io/en/latest/miniconda.html
  echo   Python   : https://www.python.org/downloads/
  echo.
  pause
  exit /b 1
)

echo Using interpreter: %PY%
echo.
"%PY%" "%~dp0install_hooks.py" %*
echo.
pause
