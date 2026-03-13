#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Smart File Organizer Build Script for Linux"
echo ===================================================

# Detect package manager
detect_package_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        echo "apt-get"
    elif command -v dnf >/dev/null 2>&1; then
        echo "dnf"
    elif command -v pacman >/dev/null 2>&1; then
        echo "pacman"
    else
        echo "unknown"
    fi
}

PKG_MGR=$(detect_package_manager)

# Check Java 17+
echo "[INFO] Checking Java installation..."
if ! command -v java >/dev/null 2>&1; then
    echo "[ERROR] Java not found."
    case $PKG_MGR in
        apt-get)
            echo "[ERROR] Please install Java 17+: sudo apt-get update && sudo apt-get install openjdk-17-jdk"
            ;;
        dnf)
            echo "[ERROR] Please install Java 17+: sudo dnf install java-17-openjdk-devel"
            ;;
        pacman)
            echo "[ERROR] Please install Java 17+: sudo pacman -S jdk17-openjdk"
            ;;
        *)
            echo "[ERROR] Please install Java 17 or later from your distribution's package manager"
            ;;
    esac
    exit 1
fi

JAVA_VERSION=$(java -version 2>&1 | head -n1 | cut -d'"' -f2 | cut -d'.' -f1)
if [ "$JAVA_VERSION" -lt 17 ]; then
    echo "[ERROR] Java version $JAVA_VERSION is too old. Please install Java 17 or later."
    case $PKG_MGR in
        apt-get)
            echo "[ERROR] Run: sudo apt-get update && sudo apt-get install openjdk-17-jdk"
            ;;
        dnf)
            echo "[ERROR] Run: sudo dnf install java-17-openjdk-devel"
            ;;
        pacman)
            echo "[ERROR] Run: sudo pacman -S jdk17-openjdk"
            ;;
    esac
    exit 1
fi

echo "[OK] Java $JAVA_VERSION found"

# Check Python 3.11+
echo "[INFO] Checking Python installation..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "[ERROR] Python3 not found."
    case $PKG_MGR in
        apt-get)
            echo "[ERROR] Please install Python 3.11+: sudo apt-get install python3.11 python3.11-venv"
            ;;
        dnf)
            echo "[ERROR] Please install Python 3.11+: sudo dnf install python3.11 python3.11-pip"
            ;;
        pacman)
            echo "[ERROR] Please install Python 3.11+: sudo pacman -S python"
            ;;
        *)
            echo "[ERROR] Please install Python 3.11 or later from your distribution's package manager"
            ;;
    esac
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 11 ]; then
    echo "[ERROR] Python version $PYTHON_MAJOR.$PYTHON_MINOR is too old. Please install Python 3.11 or later."
    case $PKG_MGR in
        apt-get)
            echo "[ERROR] Run: sudo apt-get install python3.11 python3.11-venv"
            ;;
        dnf)
            echo "[ERROR] Run: sudo dnf install python3.11 python3.11-pip"
            ;;
        pacman)
            echo "[ERROR] Run: sudo pacman -S python"
            ;;
    esac
    exit 1
fi

echo "[OK] Python $PYTHON_MAJOR.$PYTHON_MINOR found"

# Check Maven
echo "[INFO] Checking Maven installation..."
if ! command -v mvn >/dev/null 2>&1; then
    echo "[ERROR] Maven not found."
    case $PKG_MGR in
        apt-get)
            echo "[ERROR] Please install Maven: sudo apt-get install maven"
            ;;
        dnf)
            echo "[ERROR] Please install Maven: sudo dnf install maven"
            ;;
        pacman)
            echo "[ERROR] Please install Maven: sudo pacman -S maven"
            ;;
        *)
            echo "[ERROR] Please install Apache Maven from your distribution's package manager"
            ;;
    esac
    exit 1
fi

echo "[OK] All dependencies found"

# Create backend virtual environment
echo "[INFO] Creating Python virtual environment..."
if [ ! -d "backend/.venv" ]; then
    cd backend
    python3 -m venv .venv
    cd ..
fi

echo "[INFO] Activating virtual environment and installing dependencies..."
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

# Build frontend
echo "[INFO] Building frontend with Maven..."
cd frontend
mvn clean package -DskipTests
cd ..

# Create .env file if not exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[INFO] Creating .env from .env.example"
        cp .env.example .env
    else
        echo "[WARN] .env.example not found, creating minimal .env"
        echo "HOST_SCAN_PATH=/home" > .env
        echo "BACKEND_HOST=127.0.0.1" >> .env
        echo "BACKEND_PORT=8000" >> .env
        echo "REDIS_HOST=localhost" >> .env
        echo "REDIS_PORT=6379" >> .env
        echo "HOST_ROOT=" >> .env
    fi
fi

# Detect graphical environment
echo "[INFO] Detecting graphical environment..."
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    echo "[WARN] No graphical environment detected (DISPLAY/WAYLAND_DISPLAY not set)"
    echo "[INFO] Starting backend only..."
    
    # Start backend only
    source backend/.venv/bin/activate
    cd backend
    uvicorn main:app --host 127.0.0.1 --port 8000 &
    BACKEND_PID=$!
    cd ..
    
    echo "[OK] Backend started with PID $BACKEND_PID"
    echo "[INFO] API available at: http://127.0.0.1:8000"
    echo "[INFO] Press Ctrl+C to stop the server"
    
    # Wait for interrupt
    trap "echo '[INFO] Stopping backend...'; kill $BACKEND_PID 2>/dev/null; exit 0" INT
    wait $BACKEND_PID
else
    echo "[OK] Graphical environment detected"
    
    # Start backend
    echo "[INFO] Starting backend server..."
    source backend/.venv/bin/activate
    cd backend
    uvicorn main:app --host 127.0.0.1 --port 8000 &
    BACKEND_PID=$!
    cd ..
    
    # Setup cleanup trap
    trap "echo '[INFO] Stopping backend...'; kill $BACKEND_PID 2>/dev/null" EXIT
    
    # Wait for backend to start
    echo "[INFO] Waiting for backend to start..."
    sleep 3
    
    # Launch frontend
    echo "[INFO] Launching frontend application..."
    cd frontend
    mvn javafx:run
    cd ..
    
    echo "[OK] Application closed successfully"
fi

echo "[INFO] Build script completed"