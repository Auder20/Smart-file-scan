#!/bin/bash
# FIX: usar heredoc con comillas DOBLES para que $APP_NAME se expanda.
# El script original usaba << 'LAUNCHER' (comillas simples), lo que hacía
# que "${APP_NAME}-ui" se escribiera literalmente en el script generado
# en vez de "SmartFileOrganizer-ui", y el frontend nunca arrancaba.
BUNDLE=$1
APP_NAME=$2

cat > "$BUNDLE/Contents/MacOS/$APP_NAME" << LAUNCHER
#!/bin/bash
DIR="\$(cd "\$(dirname "\$0")" && pwd)"
DATA="\$HOME/.smartfileorganizer"
mkdir -p "\$DATA"
export DB_PATH="\$DATA/sfo.db"
"\$DIR/backend/sfo-backend" &
BPID=\$!
for i in \$(seq 1 20); do
  curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 0.5
done
"\$DIR/${APP_NAME}-ui"
kill "\$BPID" 2>/dev/null
LAUNCHER

chmod +x "$BUNDLE/Contents/MacOS/$APP_NAME"
echo "Launcher macOS OK"