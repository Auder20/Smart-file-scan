#!/bin/bash
BUNDLE=$1
APP_NAME=$2
cat > "$BUNDLE/Contents/MacOS/$APP_NAME" << 'LAUNCHER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
DATA="$HOME/.smartfileorganizer"
mkdir -p "$DATA"
export DB_PATH="$DATA/sfo.db"
"$DIR/backend/sfo-backend" &
BPID=$!
for i in $(seq 1 20); do
  curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 0.5
done
"$DIR/${APP_NAME}-ui"
kill "$BPID" 2>/dev/null
LAUNCHER
# Reemplazar APP_NAME en el script
sed -i "s/\${APP_NAME}/$APP_NAME/g" "$BUNDLE/Contents/MacOS/$APP_NAME"
chmod +x "$BUNDLE/Contents/MacOS/$APP_NAME"
echo "Launcher macOS OK"