@echo off
setlocal enabledelayedexpansion

echo [INFO] Smart File Organizer Build Script for Windows
echo ====================================================

REM Check Java 17+
echo [INFO] Checking Java installation...
java -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Java not found. Please install Java 17 or later:
    echo [ERROR] https://adoptium.net/
    goto :error
)

for /f "tokens=3" %%i in ('java -version 2^>^&1 ^| findstr /i "version"') do set JAVA_VERSION=%%i
set JAVA_VERSION=!JAVA_VERSION:"=!
for /f "tokens=1,2 delims=." %%a in ("!JAVA_VERSION!") do set JAVA_MAJOR=%%a & set JAVA_MINOR=%%b

if !JAVA_MAJOR! lss 17 (
    echo [ERROR] Java version !JAVA_MAJOR! is too old. Please install Java 17 or later:
    echo [ERROR] https://adoptium.net/
    goto :error
)

echo [OK] Java !JAVA_MAJOR!.!JAVA_MINOR! found

REM Check Python 3.11+
echo [INFO] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.11 or later:
    echo [ERROR] https://www.python.org/downloads/
    goto :error
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
for /f "tokens=1,2 delims=." %%a in ("!PYTHON_VERSION!") do set PYTHON_MAJOR=%%a & set PYTHON_MINOR=%%b

if !PYTHON_MAJOR! lss 3 (
    echo [ERROR] Python version !PYTHON_MAJOR! is too old. Please install Python 3.11 or later:
    echo [ERROR] https://www.python.org/downloads/
    goto :error
)

if !PYTHON_MINOR! lss 11 (
    echo [ERROR] Python version !PYTHON_MAJOR!.!PYTHON_MINOR! is too old. Please install Python 3.11 or later:
    echo [ERROR] https://www.python.org/downloads/
    goto :error
)

echo [OK] Python !PYTHON_MAJOR!.!PYTHON_MINOR! found

REM Check Maven
echo [INFO] Checking Maven installation...
mvn --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Maven not found. Please install Apache Maven:
    echo [ERROR] https://maven.apache.org/download.cgi
    goto :error
)

echo [OK] All dependencies found

REM Create backend virtual environment
echo [INFO] Creating Python virtual environment...
if not exist "backend\.venv" (
    cd backend
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment
        goto :error
    )
    cd ..
)

echo [INFO] Activating virtual environment and installing dependencies...
call backend\.venv\Scripts\activate.bat
pip install -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies
    goto :error
)

REM Build frontend
echo [INFO] Building frontend with Maven...
cd frontend
mvn clean package -DskipTests
if %errorlevel% neq 0 (
    echo [ERROR] Maven build failed
    cd ..
    goto :error
)
cd ..

REM Create .env file if not exists
if not exist ".env" (
    if exist ".env.example" (
        echo [INFO] Creating .env from .env.example
        copy .env.example .env
    ) else (
        echo [WARN] .env.example not found, creating minimal .env
        echo HOST_SCAN_PATH=C:\Users > .env
        echo BACKEND_HOST=127.0.0.1 >> .env
        echo BACKEND_PORT=8000 >> .env
        echo REDIS_HOST=localhost >> .env
        echo REDIS_PORT=6379 >> .env
        echo HOST_ROOT= >> .env
    )
)

REM Start backend
echo [INFO] Starting backend server...
start /min cmd /c "call backend\.venv\Scripts\activate.bat ^&^& cd backend ^&^& uvicorn main:app --host 127.0.0.1 --port 8000"

REM Wait for backend to start
echo [INFO] Waiting for backend to start...
timeout /t 3 /nobreak >nul

REM Launch frontend
echo [INFO] Launching frontend application...
cd frontend
mvn javafx:run
cd ..

REM Cleanup: kill backend process
echo [INFO] Stopping backend server...
taskkill /f /im uvicorn.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1

echo [OK] Application closed successfully
goto :end

:error
echo [ERROR] Build failed. Please check the error messages above.
pause
exit /b 1

:end
echo [INFO] Build script completed
pause