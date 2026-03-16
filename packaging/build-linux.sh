#!/usr/bin/env bash
# ============================================================
#  Smart File Organizer — Linux Package Builder
#  Genera: SmartFileOrganizer-1.0.0-x86_64.AppImage
#
#  Requisitos en la maquina que ejecuta este script:
#    - Java 21 JDK  (con jpackage)
#    - Python 3.11+
#    - Maven 3.8+
#    - appimagetool  (se descarga automaticamente si no existe)
#    - fuse2 o fuse3 (para montar AppImage en pruebas)
#      Ubuntu/Debian: sudo apt install fuse libfuse2
#      Fedora:        sudo dnf install fuse fuse-libs
#
#  El AppImage resultante NO requiere nada instalado
#  en la maquina del usuario final.
# ============================================================
set -euo pipefail

APP_NAME="SmartFileOrganizer"
APP_VERSION="1.0.0"
MAIN_CLASS="com.smartfileorganizer.Main"
DIST_DIR="dist/linux"
BACKEND_DIST="$DIST_DIR/backend"
FRONTEND_DIST="$DIST_DIR/frontend"
APPDIR="$DIST_DIR/AppDir"
INSTALLER_DIR="dist/installer"

# Colores para output
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()      { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()    { echo -e "\n${BLUE}[STEP $1]${NC} $2"; }

echo ""
echo "========================================================="
echo "  Smart File Organizer — Linux Package Builder"
echo "========================================================="
echo ""

# ── 1. Verificar herramientas ──────────────────────────────────────────────────

step "1/7" "Verificando herramientas necesarias..."

# Java
command -v java >/dev/null 2>&1 || error "Java no encontrado. Instala JDK 21:\n  Ubuntu: sudo apt install openjdk-21-jdk\n  Fedora: sudo dnf install java-21-openjdk-devel"
JAVA_VER=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
[[ "$JAVA_VER" -ge 21 ]] || error "Necesitas Java 21+. Tienes Java $JAVA_VER."
ok "Java $JAVA_VER encontrado"

# jpackage
command -v jpackage >/dev/null 2>&1 || error "jpackage no encontrado. Asegurate de tener el JDK completo, no solo JRE."
ok "jpackage encontrado"

# Python
command -v python3 >/dev/null 2>&1 || error "Python3 no encontrado.\n  Ubuntu: sudo apt install python3.11 python3.11-venv\n  Fedora: sudo dnf install python3.11"
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
[[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 11 ]] || error "Necesitas Python 3.11+. Tienes Python $PY_MAJOR.$PY_MINOR."
ok "Python $PY_MAJOR.$PY_MINOR encontrado"

# Maven
command -v mvn >/dev/null 2>&1 || error "Maven no encontrado.\n  Ubuntu: sudo apt install maven\n  Fedora: sudo dnf install maven"
ok "Maven encontrado"

# appimagetool — descargar si no existe
if ! command -v appimagetool >/dev/null 2>&1; then
    warn "appimagetool no encontrado. Descargando..."
    ARCH=$(uname -m)
    TOOL_URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    curl -Lo /tmp/appimagetool "$TOOL_URL" || error "No se pudo descargar appimagetool."
    chmod +x /tmp/appimagetool
    APPIMAGETOOL="/tmp/appimagetool"
    ok "appimagetool descargado en /tmp"
else
    APPIMAGETOOL="appimagetool"
    ok "appimagetool encontrado"
fi

# ── 2. Limpiar directorios previos ─────────────────────────────────────────────

step "2/7" "Limpiando builds anteriores..."
rm -rf "$DIST_DIR" "$INSTALLER_DIR"
mkdir -p "$BACKEND_DIST" "$FRONTEND_DIST" "$APPDIR" "$INSTALLER_DIR"
ok "Directorios limpios"

# ── 3. Empaquetar backend con PyInstaller ──────────────────────────────────────

step "3/7" "Empaquetando backend Python con PyInstaller..."

cd backend

# Venv limpio para packaging
rm -rf .venv-pkg
python3 -m venv .venv-pkg
source .venv-pkg/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

# Generar binario único que incluye Python + todas las dependencias
pyinstaller --onefile \
    --name sfo-backend \
    --distpath "../$BACKEND_DIST" \
    --workpath "../$DIST_DIR/pyinstaller-tmp" \
    --specpath "../$DIST_DIR" \
    --hidden-import=uvicorn.logging \
    --hidden-import=uvicorn.loops \
    --hidden-import=uvicorn.loops.auto \
    --hidden-import=uvicorn.protocols \
    --hidden-import=uvicorn.protocols.http \
    --hidden-import=uvicorn.protocols.http.auto \
    --hidden-import=uvicorn.protocols.websockets \
    --hidden-import=uvicorn.protocols.websockets.auto \
    --hidden-import=uvicorn.lifespan \
    --hidden-import=uvicorn.lifespan.on \
    --hidden-import=anyio._backends._asyncio \
    --collect-all fastapi \
    --collect-all pydantic \
    --noconfirm \
    main.py

deactivate
cd ..
ok "Backend empaquetado: $BACKEND_DIST/sfo-backend"

# ── 4. Compilar frontend con Maven ─────────────────────────────────────────────

step "4/7" "Compilando frontend con Maven..."

cd frontend
mvn clean package -DskipTests -q
cd ..
ok "Frontend compilado"

# ── 5. Empaquetar frontend con jpackage ────────────────────────────────────────

step "5/7" "Empaquetando frontend con jpackage (incluye JRE)..."

# Genera una carpeta con el ejecutable + su propio JRE
jpackage \
    --type app-image \
    --name "$APP_NAME" \
    --app-version "$APP_VERSION" \
    --input frontend/target \
    --dest "$FRONTEND_DIST" \
    --main-jar frontend-1.0.0.jar \
    --main-class "$MAIN_CLASS" \
    --java-options "--enable-preview" \
    --java-options "-Xmx512m" \
    --java-options "--add-opens=javafx.graphics/com.sun.javafx.application=ALL-UNNAMED"

ok "Frontend empaquetado: $FRONTEND_DIST/$APP_NAME"

# ── 6. Construir estructura AppDir ─────────────────────────────────────────────

step "6/7" "Construyendo estructura AppImage..."

# Copiar frontend (con JRE incluido)
cp -r "$FRONTEND_DIST/$APP_NAME" "$APPDIR/frontend"

# Copiar backend (binario único, Python incluido)
cp "$BACKEND_DIST/sfo-backend" "$APPDIR/backend"
chmod +x "$APPDIR/backend/sfo-backend"

# Icono de la aplicación (placeholder — reemplaza con tu icono real .png 256x256)
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
# Si tienes un icono en resources, copiarlo:
# cp frontend/src/main/resources/icons/app-icon.png $APPDIR/usr/share/icons/hicolor/256x256/apps/smartfileorganizer.png
# Por ahora crear un placeholder válido de 1 pixel
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00\x00\x00\x01\x00\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' \
    > "$APPDIR/usr/share/icons/hicolor/256x256/apps/smartfileorganizer.png"

# .desktop file — requerido por AppImage
cat > "$APPDIR/smartfileorganizer.desktop" << 'DESKTOP'
[Desktop Entry]
Name=Smart File Organizer
Comment=Organiza y analiza tus archivos
Exec=SmartFileOrganizer
Icon=smartfileorganizer
Type=Application
Categories=Utility;FileManager;
Keywords=files;organizer;duplicates;scanner;
StartupNotify=true
DESKTOP

# AppRun — script que arranca backend + frontend
# AppImage llama a este archivo al ejecutarse
cat > "$APPDIR/AppRun" << 'APPRUN'
#!/usr/bin/env bash
# AppRun: punto de entrada de la AppImage
# Arranca el backend en segundo plano y luego el frontend

APPDIR="$(dirname "$(readlink -f "$0")")"
BACKEND="$APPDIR/backend/sfo-backend"
FRONTEND="$APPDIR/frontend/SmartFileOrganizer/bin/SmartFileOrganizer"

# Directorio de datos del usuario (para .env y la base de datos SQLite)
DATA_DIR="$HOME/.smartfileorganizer"
mkdir -p "$DATA_DIR"

# Crear .env si no existe
ENV_FILE="$DATA_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'ENV'
HOST_SCAN_PATH=/home
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
REDIS_HOST=localhost
REDIS_PORT=6379
HOST_ROOT=
DB_PATH=~/.smartfileorganizer/sfo.db
ENV
fi

# Arrancar backend
export DB_PATH="$DATA_DIR/sfo.db"
"$BACKEND" &
BACKEND_PID=$!

# Esperar a que el backend esté listo (max 10 segundos)
for i in $(seq 1 20); do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Arrancar frontend
"$FRONTEND"
FRONTEND_EXIT=$?

# Apagar backend al cerrar el frontend
kill "$BACKEND_PID" 2>/dev/null
wait "$BACKEND_PID" 2>/dev/null

exit $FRONTEND_EXIT
APPRUN

chmod +x "$APPDIR/AppRun"
ok "Estructura AppDir lista"

# ── 7. Generar AppImage ────────────────────────────────────────────────────────

step "7/7" "Generando AppImage con appimagetool..."

ARCH=$(uname -m)
OUTPUT_FILE="$INSTALLER_DIR/${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"

ARCH=$ARCH "$APPIMAGETOOL" "$APPDIR" "$OUTPUT_FILE"
chmod +x "$OUTPUT_FILE"

echo ""
echo "========================================================="
ok "LISTO"
info "AppImage generada:"
info "  $OUTPUT_FILE"
info ""
info "El usuario final puede ejecutarla con:"
info "  chmod +x ${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"
info "  ./${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"
info ""
info "No requiere instalar Java, Python ni nada mas."
echo "========================================================="