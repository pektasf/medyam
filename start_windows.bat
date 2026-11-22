@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
  echo [1/3] Python sanal ortami olusturuluyor...
  py -3 -m venv .venv
  if errorlevel 1 goto error
)
if not exist requirements.txt (
  echo HATA: requirements.txt bulunamadi.
  echo start_windows.bat ve requirements.txt ayni ana klasorde olmali.
  goto error
)
echo [2/3] Bagimliliklar kontrol ediliyor...
call .venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto error
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
if not exist .env copy .env.example .env >nul
echo [3/3] Eski Usul AI Studio v0.3 baslatiliyor...
start "Eski Usul AI Studio" http://127.0.0.1:8765
call .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
if errorlevel 1 goto error
goto end
:error
echo.
echo Bir hata olustu. Yukaridaki hata mesajini kontrol edin.
echo Python 3.11/3.12 ve requirements.txt dosyasinin proje ana klasorunde oldugundan emin olun.
pause
:end
endlocal
