@echo off
setlocal
cd /d "%~dp0"
set "FINDBACK_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%FINDBACK_PY%" (
    "%FINDBACK_PY%" -m findback.webapp --open
    goto finished
)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m findback.webapp --open
    goto finished
)
python -m findback.webapp --open
:finished
if errorlevel 1 pause
