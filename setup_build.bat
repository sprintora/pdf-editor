@echo off
REM Shared setup for build_exe.bat and build_store.bat:
REM   1. Python environment + packages   2. OCR engine (Tesseract)   3. OCR languages
cd /d "%~dp0"

REM ---- OCR languages to include (codes from https://github.com/tesseract-ocr/tessdata_fast) ----
REM e.g. add hin for Hindi, fra for French:  set "OCR_LANGS=eng sin tam hin fra"
set "OCR_LANGS=eng sin tam"

REM ---- 1. Python environment (prefers 3.12, whose packages are the most mature) ----
set "PYCMD=python"
py -3.12 -c "import sys" >nul 2>&1 && set "PYCMD=py -3.12"
if "%PYCMD%"=="python" py -3.13 -c "import sys" >nul 2>&1 && set "PYCMD=py -3.13"
if "%PYCMD%"=="python" py -3.11 -c "import sys" >nul 2>&1 && set "PYCMD=py -3.11"
if not exist venv\Scripts\python.exe (
    echo Creating the virtual environment with: %PYCMD%
    %PYCMD% -m venv venv
    if errorlevel 1 goto :fail
)
call venv\Scripts\activate
python -c "import sys; print('Python', sys.version.split()[0]); sys.exit(0 if sys.version_info < (3, 14) else 1)"
if errorlevel 1 echo NOTE: Python 3.14 is very new. If installing packages fails, delete the "venv" folder and install Python 3.12 first.
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :fail

REM ---- 2. OCR engine -> vendor\tesseract ----
if exist vendor\tesseract\tesseract.exe goto :have_engine
set "TESS_SRC="
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS_SRC=%ProgramFiles%\Tesseract-OCR"
if not defined TESS_SRC (
    echo Installing the Tesseract OCR engine with winget ^(Windows may ask for permission^)...
    winget install --id UB-Mannheim.TesseractOCR -e --silent --accept-package-agreements --accept-source-agreements
    if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS_SRC=%ProgramFiles%\Tesseract-OCR"
)
if not defined TESS_SRC (
    echo.
    echo Could not find or install the Tesseract OCR engine automatically.
    echo Install it from https://github.com/UB-Mannheim/tesseract/wiki ^(keep the default folder^)
    echo and then run this script again.
    goto :fail
)
echo Copying the OCR engine from "%TESS_SRC%" ...
robocopy "%TESS_SRC%" vendor\tesseract /E /XF unins000.exe unins000.dat /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
:have_engine

REM ---- 3. OCR languages -> vendor\tesseract\tessdata ----
if not exist ocr_languages mkdir ocr_languages
for %%L in (%OCR_LANGS%) do (
    if not exist "ocr_languages\%%L.traineddata" (
        echo Downloading OCR language: %%L
        powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/%%L.traineddata' -OutFile 'ocr_languages\%%L.traineddata' } catch { exit 1 }"
        if errorlevel 1 (
            echo Could not download %%L - skipping it.
            del "ocr_languages\%%L.traineddata" 2>nul
        )
    )
    if exist "ocr_languages\%%L.traineddata" copy /Y "ocr_languages\%%L.traineddata" "vendor\tesseract\tessdata\" >nul
)
echo.
echo OCR engine check:
"vendor\tesseract\tesseract.exe" --list-langs
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo Setup failed - see the messages above.
exit /b 1
