@echo off
rem Cria o app no SEU computador, para testar antes de publicar.
rem Precisa de Python 3 (e, para o instalador, do Inno Setup 6). Os usuarios NAO precisam.
cd /d "%~dp0.."
python -m pip install pyinstaller==6.11.1
python ferramentas\gerar_build_info.py --versao 1.0.0
python -m PyInstaller --noconfirm --clean --windowed --name "AutoAtack AQW" --icon assets\icone.ico --add-data "assets;assets" --version-file version_info.txt autoatack_aqw.py
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.0 instalador\autoatack_aqw.iss
    echo Instalador em: saida\AutoAtack-AQW-Setup-1.0.0.exe
) else (
    echo Inno Setup nao encontrado: criei so o app em "dist\AutoAtack AQW"
)
echo Obs.: neste build local a atualizacao automatica fica desligada.
pause
