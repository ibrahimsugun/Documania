@echo off
rem Documania panelini yerelde baslatir. Bu dosyaya cift tiklamak yeterlidir.
rem Sunucuyu durdurmak icin bu pencerede Ctrl+C.
rem .env'de TELEGRAM_BOT_TOKEN doluysa Telegram botu da ayri bir pencerede acilir (PRD 12.1.5).

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

echo [1/4] Veritabani semasi kontrol ediliyor...
"%PY%" -m alembic upgrade head
if errorlevel 1 (
  echo.
  echo HATA: Sema guncellenemedi. Sunucu baslatilmadi.
  pause
  exit /b 1
)

echo.
echo [2/4] Telegram botu kontrol ediliyor...
rem Token degeri ekrana YAZILMAZ: uygulamanin bot icin gordugu ayar (.env ya da ortam degiskeni)
rem yalniz dolu mu diye sorulur, cevap sadece cikis kodudur.
"%PY%" -c "import sys; from app.config import get_settings; t = get_settings().telegram_bot_token; sys.exit(0 if t is not None and t.get_secret_value().strip() else 1)" >nul 2>&1
if errorlevel 1 (
  echo Telegram botu kapali: .env'de TELEGRAM_BOT_TOKEN yok. Panel botsuz aciliyor.
) else (
  echo Telegram botu ayri pencerede aciliyor. Onceki bot penceresi aciksa once onu kapatin.
  start "Documania bot" cmd /k ""%PY%" -m app.telegram.bot"
)

echo.
echo [3/4] Tarayici birazdan acilacak: %URL%
start "" /b powershell -NoProfile -Command "Start-Sleep 4; Start-Process '%URL%'" >nul 2>&1

echo [4/4] Sunucu baslatiliyor. Durdurmak icin Ctrl+C.
echo.
"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo Sunucu durdu. Telegram botu ayri pencerededir; gerekiyorsa o pencereyi de kapatin.
pause
