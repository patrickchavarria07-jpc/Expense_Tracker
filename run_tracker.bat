@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import tkinter, sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul
    if not errorlevel 1 (
        py -3 "%~dp0tracker.py"
        goto finished
    )
)
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import tkinter, sys; sys.exit(sys.version_info[:1] != (3,) or sys.version_info < (3, 8))" >nul 2>nul
    if not errorlevel 1 (
        python "%~dp0tracker.py"
        goto finished
    )
)
echo A usable Python 3.8 or newer installation with Tkinter was not found.
echo Install Python from https://www.python.org/downloads/
echo Include Tcl/Tk and select "Add Python to PATH" during installation.
pause
exit /b 1
:finished
if errorlevel 1 (
    echo.
    echo The tracker could not start or closed with an error. See the message above.
    pause
    exit /b 1
)
exit /b 0
