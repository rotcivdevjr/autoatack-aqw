@echo off
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw autoatack_aqw.py
    exit /b
)
where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw autoatack_aqw.py
    exit /b
)
echo Python nao encontrado.
echo Instale em python.org e marque a opcao "Add Python to PATH".
pause
