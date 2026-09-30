@echo off
rem belgeee panelini yerelde baslatir. Bu dosyaya cift tiklamak yeterlidir.
rem Sunucuyu durdurmak icin bu pencerede Ctrl+C.

rem Turkce karakterler konsolda dogru gorunsun (Python ciktisi UTF-8).
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:8000"

if not exist "%PY%" (
  echo HATA: %PY% bulunamadi.
  echo Sanal ortam eksik. Depo kokunde once sunu calistirin:
  echo     python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -e .
  echo.
  pause
  exit /b 1
)

echo [1/3] Veritabani semasi kontrol ediliyor...
"%PY%" -m alembic upgrade head
if errorlevel 1 (
  echo.
  echo HATA: Sema guncellenemedi. Sunucu baslatilmadi.
  pause
  exit /b 1
)

echo.
echo [2/3] Tarayici birazdan acilacak: %URL%
start "" /b powershell -NoProfile -Command "Start-Sleep 4; Start-Process '%URL%'" >nul 2>&1

echo [3/3] Sunucu baslatiliyor. Durdurmak icin Ctrl+C.
echo.
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Sunucu durdu.
pause
