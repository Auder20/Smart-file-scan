#!/bin/bash
APPDIR=$1
APP_NAME=$2

cat > "$APPDIR/smartfileorganizer.desktop" << 'DESKTOP'
[Desktop Entry]
Name=Smart File Organizer
Comment=Organiza y analiza tus archivos
Exec=SmartFileOrganizer
Icon=smartfileorganizer
Type=Application
Categories=Utility;FileManager;
DESKTOP

cat > "$APPDIR/AppRun" << 'APPRUN'
#!/usr/bin/env bash
APPDIR="$(dirname "$(readlink -f "$0")")"
DATA="$HOME/.smartfileorganizer"
mkdir -p "$DATA"
export DB_PATH="$DATA/sfo.db"
"$APPDIR/backend/sfo-backend" &
BPID=$!
for i in $(seq 1 20); do
  curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 0.5
done
"$APPDIR/frontend/SmartFileOrganizer/bin/SmartFileOrganizer"
kill "$BPID" 2>/dev/null
APPRUN
chmod +x "$APPDIR/AppRun"
echo "AppDir OK"