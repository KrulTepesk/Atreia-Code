@echo off
rem Gera saida\AtreiaCode-Setup.exe (so precisa rodar no PC de quem distribui o programa)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "build_tools\build.ps1"
if errorlevel 1 (
  echo.
  echo Deu erro. Tire um print desta janela e mande.
)
pause
