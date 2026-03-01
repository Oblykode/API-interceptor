@echo off
setlocal

cd /d "%~dp0"

echo Setting up API Interceptor...
echo.

echo [1/5] Verifying Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python is not available on PATH.
  echo Install Python 3.11+ and re-run setup.bat.
  exit /b 1
)

echo [2/5] Ensuring pip...
python -m ensurepip --default-pip >nul 2>&1

echo [3/5] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 (
  echo ERROR: Failed to upgrade pip.
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: Failed to install requirements.
  exit /b 1
)

echo [4/5] Validating project imports...
python -c "from app.api.server import app; from app.core.config import get_settings as g; s=g(); print('APP_OK', app.title); print('UI', s.ui_host, s.ui_port); print('PROXY', s.proxy_host, s.proxy_port)"
if errorlevel 1 (
  echo ERROR: Import/validation failed.
  exit /b 1
)

echo [5/5] Optional test run...
choice /C YN /N /T 5 /D N /M "Run full tests now? [Y/N] (auto N in 5s): "
if errorlevel 2 goto skip_tests

call run_tests.bat
if errorlevel 1 (
  echo ERROR: Tests failed. Review output above.
  exit /b 1
)

:skip_tests
echo.
echo Setup complete.
echo.
echo Usage:
echo   python main.py         ^(default: starts GUI + proxy^)
echo   python main.py gui     ^(GUI/API only^)
echo   python main.py proxy   ^(proxy only^)
echo.
echo Recommended next steps:
echo   1) Start app: python main.py
echo   2) Open UI at the configured UI host/port shown above
echo   3) Configure browser proxy to configured PROXY host/port shown above
echo   4) Visit http://mitm.it in proxied browser and install cert for HTTPS
echo.
pause
exit /b 0
