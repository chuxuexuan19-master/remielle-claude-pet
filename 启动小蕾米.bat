@echo off
rem Xiaolemi desktop pet - double-click to start / summon (no console window)
rem Interpreter lookup order: python.txt -> pythonw on PATH -> python on PATH
rem NOTE: keep this file ASCII-only. cmd parses .bat in the system codepage,
rem       and multi-byte UTF-8 here breaks the parser.
cd /d "%~dp0"

set "PYW="
if exist "python.txt" set /p PYW=<python.txt
if defined PYW if not exist "%PYW%" set "PYW="

if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PYW set "PYW=%%i"
if not defined PYW for /f "delims=" %%i in ('where python 2^>nul ^| findstr /v /i "WindowsApps"') do if not defined PYW set "PYW=%%i"

if not defined PYW (
  echo.
  echo   Python not found. Install Python or Anaconda first,
  echo   then double-click  install.bat  again.
  echo.
  pause
  exit /b 1
)

start "" "%PYW%" "%~dp0pet.py"
exit /b 0
