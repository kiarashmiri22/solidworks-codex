@echo off
setlocal
set "ROOT=%~dp0.."
set "PYTHON=%ROOT%\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    where py.exe >nul 2>nul
    if errorlevel 1 (
        echo SolidWorks Codex needs Python 3.11+ and the Windows py launcher. Install Python, then restart Codex. 1>&2
        exit /b 1
    )
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo SolidWorks Codex needs Python 3.11 or newer. 1>&2
        exit /b 1
    )
    py -3 -m venv "%ROOT%\.venv" 1>&2
    if errorlevel 1 exit /b 1
)

"%PYTHON%" -c "import mcp, win32com.client" >nul 2>nul
if errorlevel 1 (
    "%PYTHON%" -m pip install --disable-pip-version-check -r "%ROOT%\requirements.txt" 1>&2
    if errorlevel 1 exit /b 1
)

"%PYTHON%" -m solidworks_mcp
exit /b %ERRORLEVEL%
