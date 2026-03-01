@echo off
setlocal

cd /d "%~dp0"

echo [1/4] Verifying Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python is not available on PATH.
  exit /b 1
)

echo [2/4] Ensuring pytest tooling is installed...
python -c "import pytest" >nul 2>&1
if errorlevel 1 (
  echo Installing pytest...
  python -m pip install pytest
  if errorlevel 1 (
    echo ERROR: Failed to install pytest.
    exit /b 1
  )
)

python -c "import pytest_asyncio" >nul 2>&1
if errorlevel 1 (
  echo Installing pytest-asyncio...
  python -m pip install pytest-asyncio
  if errorlevel 1 (
    echo ERROR: Failed to install pytest-asyncio.
    exit /b 1
  )
)

echo [3/4] Running unit tests...
python -m pytest -q
if errorlevel 1 (
  echo ERROR: Unit tests failed.
  exit /b 1
)

echo [4/4] Running smoke test...
powershell -NoProfile -ExecutionPolicy Bypass -File ".\smoke_test.ps1"
if errorlevel 1 (
  echo ERROR: Smoke test failed.
  exit /b 1
)

echo.
echo All tests passed.
exit /b 0
