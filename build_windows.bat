@echo off
rem Builds dist\ExoApp\ExoApp.exe. Needs Python 3.12 or 3.13 from python.org.
cd /d "%~dp0"
py -3 -m venv .venv-win || goto :error
.venv-win\Scripts\python -m pip install --upgrade pip || goto :error
.venv-win\Scripts\pip install -r requirements.txt pyinstaller || goto :error
.venv-win\Scripts\pyinstaller --noconfirm --windowed --name ExoApp ^
    --icon assets\exoapp.ico --add-data "assets;assets" ^
    --hidden-import gui --hidden-import hid exoapp.py || goto :error
echo.
echo Valmis / Done: dist\ExoApp\ExoApp.exe
goto :eof
:error
echo Build failed.
exit /b 1
