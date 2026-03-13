#!/usr/bin/env bash
set -euo pipefail

echo "[INFO] Smart File Organizer Build Script for macOS"
echo ==================================================

# Check for Homebrew
echo "[INFO] Checking Homebrew installation..."
if ! command -v brew >/dev/null 2>&1; then
    echo "[INFO] Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Add Homebrew to PATH for current session
    if [ -x /opt/homebrew/bin/brew ]; then
        # Apple Silicon
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        # Intel
        eval "$(/usr/local/bin/brew shellenv)"
    fi
else
    echo "[OK] Homebrew found"
fi

# Check and install Java 17+
echo "[INFO] Checking Java installation..."
if ! command -v java >/dev/null 2>&1; then
    echo "[INFO] Installing OpenJDK 17..."
    brew install openjdk@17
    
    # Set up JAVA_HOME
    if [ -x /opt/homebrew/bin/brew ]; then
        # Apple Silicon
        export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
        echo 'export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home' >> ~/.zshrc
    else
        # Intel
        export JAVA_HOME=/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
        echo 'export JAVA_HOME=/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home' >> ~/.zshrc
    fi
else
    echo "[OK] Java found"
fi

# Verify Java version
JAVA_VERSION=$(java -version 2>&1 | head -n1 | cut -d'"' -f2 | cut -d'.' -f1)
if [ "$JAVA_VERSION" -lt 17 ]; then
    echo "[ERROR] Java version $JAVA_VERSION is too old. Installing OpenJDK 17..."
    brew install openjdk@17
    
    # Set up JAVA_HOME
    if [ -x /opt/homebrew/bin/brew ]; then
        export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
    else
        export JAVA_HOME=/usr/local/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
    fi
fi

# Check and install Python 3.11+
echo "[INFO] Checking Python installation..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "[INFO] Installing Python 3.11..."
    brew install python@3.11
else
    echo "[OK] Python3 found"
fi

# Verify Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || [ "$PYTHON_MINOR" -lt 11 ]; then
    echo "[INFO] Python version $PYTHON_MAJOR.$PYTHON_MINOR is too old. Installing Python 3.11..."
    brew install python@3.11
fi

# Check and install Maven
echo "[INFO] Checking Maven installation..."
if ! command -v mvn >/dev/null 2>&1; then
    echo "[INFO] Installing Maven..."
    brew install maven
else
    echo "[OK] Maven found"
fi

echo "[OK] All dependencies found"

# Detect architecture
ARCH=$(uname -m)
echo "[INFO] Detected architecture: $ARCH"

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

# Build frontend with architecture-specific flags
echo "[INFO] Building frontend with Maven..."
cd frontend
if [ "$ARCH" = "arm64" ]; then
    echo "[INFO] Using Apple Silicon (arm64) JavaFX configuration"
    mvn clean package -DskipTests -Djavafx.platform=mac-aarch64
else
    echo "[INFO] Using Intel (x86_64) JavaFX configuration"
    mvn clean package -DskipTests
fi
cd ..

# Create .env file if not exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "[INFO] Creating .env from .env.example"
        cp .env.example .env
        
        # Set HOST_SCAN_PATH to user's home directory
        sed -i '' "s|HOST_SCAN_PATH=.*|HOST_SCAN_PATH=$HOME|g" .env
    else
        echo "[WARN] .env.example not found, creating minimal .env"
        echo "HOST_SCAN_PATH=$HOME" > .env
        echo "BACKEND_HOST=127.0.0.1" >> .env
        echo "BACKEND_PORT=8000" >> .env
        echo "REDIS_HOST=localhost" >> .env
        echo "REDIS_PORT=6379" >> .env
        echo "HOST_ROOT=" >> .env
    fi
fi

# Run xattr to bypass Gatekeeper on the compiled JAR
echo "[INFO] Applying macOS compatibility attributes..."
if [ -f "frontend/target/*.jar" ]; then
    find frontend/target -name "*.jar" -exec xattr -cr {} \;
    echo "[OK] Gatekeeper bypass applied to JAR files"
else
    echo "[WARN] No JAR files found to apply Gatekeeper bypass"
fi

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
echo "[INFO] Build script completed"