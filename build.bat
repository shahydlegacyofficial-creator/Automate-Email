@echo off
REM Build LegacyAIEmailStudio.exe on a Windows PC (needs Python 3.10+ from python.org).
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip
pip install -r requirements-build.txt || goto :error
pyinstaller --noconfirm --clean packaging\LegacyAIEmailStudio.spec || goto :error

echo.
echo Done: dist\LegacyAIEmailStudio.exe
where iscc >nul 2>nul && (
    iscc packaging\installer.iss && echo Installer: dist\LegacyAIEmailStudio-Setup.exe
)
exit /b 0

:error
echo.
echo Build failed.
exit /b 1
