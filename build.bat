@echo off
REM ==========================================================================
REM  Build VeriFace into a single dist\VeriFace.exe
REM  Usage: double-click, or run  build.bat  from a terminal.
REM ==========================================================================
setlocal
cd /d "%~dp0"

echo [1/4] Creating build virtual environment...
if not exist "build\venv" (
    python -m venv build\venv
    if errorlevel 1 goto :error
)

echo [2/4] Installing dependencies...
call build\venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :error

echo [3/4] Building single-file executable...
pyinstaller --clean --noconfirm VeriFace.spec
if errorlevel 1 goto :error

echo [4/4] Done.
echo.
echo   Built: %cd%\dist\VeriFace.exe
echo.
endlocal
exit /b 0

:error
echo.
echo   BUILD FAILED - see the messages above.
endlocal
exit /b 1
