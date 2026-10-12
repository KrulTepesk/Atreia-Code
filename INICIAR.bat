@echo off
cd /d "%~dp0"
if not exist .venv (
  echo Primeira execucao: instalando dependencias, aguarde...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe overlay\main.py
