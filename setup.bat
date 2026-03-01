@echo off
echo Setting up API Interceptor Pro...

echo.
echo 1. Installing pip if needed...
python -m ensurepip --default-pip

echo.
echo 2. Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo 3. Testing the setup...
echo Testing configuration...
timeout /t 2 >nul
python -c "from config import TARGET_IPS, INTERCEPT_ALL; print('Configuration OK')"

echo.
echo 4. Setup complete!
echo.
echo Usage:
echo   python main.py         # Start GUI (default)
echo   python main.py gui     # Start GUI only
echo   python main.py proxy   # Start Proxy only
echo.
echo Configuration:
echo   - Edit config.py to set target IPs
echo   - Or use: python setup_ip_filter.py
echo.
echo After starting:
echo   - Configure browser proxy to: 127.0.0.1:8081
echo   - Open GUI at: http://127.0.0.1:8082
echo   - Install certificate from: http://mitm.it
echo   - Start proxy separately if needed: python main.py proxy
echo.
pause
