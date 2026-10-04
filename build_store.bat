@echo off
REM Builds the Microsoft Store package:  dist\EditoraPDFEdit_<version>_x64.msix
REM Fill in store\store_config.json first (see store\README.md).
cd /d "%~dp0"

call setup_build.bat
if errorlevel 1 goto :error
call venv\Scripts\activate
set "EDITORA_ONEDIR=1"

echo.
echo Building the app folder ^(this takes a few minutes^)...
python -m PyInstaller --noconfirm --clean pdf_editor.spec
if errorlevel 1 goto :error

python store\make_msix.py
if errorlevel 1 goto :error
pause
exit /b 0

:error
echo.
echo Build failed - see the messages above.
pause
exit /b 1
