@echo off
REM Builds ONE self-contained file:  dist\Editora PDFEdit.exe  (includes the OCR engine)
cd /d "%~dp0"

call setup_build.bat
if errorlevel 1 goto :error
call venv\Scripts\activate
set "EDITORA_ONEDIR="

echo.
echo Building the exe ^(this takes a few minutes^)...
python -m PyInstaller --noconfirm --clean pdf_editor.spec
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Done!  Your app is:  dist\Editora PDFEdit.exe
echo ============================================================
pause
exit /b 0

:error
echo.
echo Build failed - see the messages above.
pause
exit /b 1
