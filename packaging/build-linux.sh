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

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "\n${BLUE}[STEP $1]${NC} $2"; }

echo ""
echo "========================================================="
echo "  Smart File Organizer — Linux Package Builder"
echo "========================================================="
echo ""

# ── 1. Verificar herramientas ──────────────────────────────────────────────────

step "1/7" "Verificando herramientas necesarias..."

command -v java >/dev/null 2>&1 || error "Java no encontrado.\n  Ubuntu: sudo apt install openjdk-21-jdk\n  Fedora: sudo dnf install java-21-openjdk-devel"
JAVA_VER=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
[[ "$JAVA_VER" -ge 21 ]] || error "Necesitas Java 21+. Tienes Java $JAVA_VER."
ok "Java $JAVA_VER encontrado"

command -v jpackage >/dev/null 2>&1 || error "jpackage no encontrado. Asegurate de tener el JDK completo."
ok "jpackage encontrado"

command -v python3 >/dev/null 2>&1 || error "Python3 no encontrado.\n  Ubuntu: sudo apt install python3.11 python3.11-venv"
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PY_VER encontrado"

command -v mvn >/dev/null 2>&1 || error "Maven no encontrado.\n  Ubuntu: sudo apt install maven"
ok "Maven encontrado"

if ! command -v appimagetool >/dev/null 2>&1; then
    warn "appimagetool no encontrado. Descargando..."
    ARCH=$(uname -m)
    curl -Lo /tmp/appimagetool \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
    chmod +x /tmp/appimagetool
    APPIMAGETOOL="/tmp/appimagetool"
    ok "appimagetool descargado en /tmp"
else
    APPIMAGETOOL="appimagetool"
    ok "appimagetool encontrado"
fi

# ── 2. Limpiar ─────────────────────────────────────────────────────────────────

step "2/7" "Limpiando builds anteriores..."
rm -rf "$DIST_DIR" "$INSTALLER_DIR"
mkdir -p "$BACKEND_DIST" "$FRONTEND_DIST" "$APPDIR" "$INSTALLER_DIR"
ok "Directorios limpios"

# ── 3. Empaquetar backend con PyInstaller ──────────────────────────────────────

step "3/7" "Empaquetando backend Python con PyInstaller..."

cd backend
rm -rf .venv-pkg
python3 -m venv .venv-pkg
source .venv-pkg/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

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
    --hidden-import=anyio._backends._trio \
    --hidden-import=multiprocessing \
    --hidden-import=sqlite3 \
    --collect-all fastapi \
    --collect-all pydantic \
    --collect-all uvicorn \
    --collect-all starlette \
    --collect-all sqlalchemy \
    --noconfirm \
    main.py

deactivate
cd ..
ok "Backend empaquetado: $BACKEND_DIST/sfo-backend"

# ── 4. Compilar frontend ────────────────────────────────────────────────────────

step "4/7" "Compilando frontend con Maven..."
cd frontend
mvn clean package -DskipTests -q
cd ..
ok "Frontend compilado"

# ── 5. Empaquetar con jpackage ─────────────────────────────────────────────────

step "5/7" "Empaquetando frontend con jpackage (incluye JRE)..."

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

# ── 6. Construir AppDir ────────────────────────────────────────────────────────

step "6/7" "Construyendo estructura AppImage..."

cp -r "$FRONTEND_DIST/$APP_NAME" "$APPDIR/frontend"
cp "$BACKEND_DIST/sfo-backend" "$APPDIR/backend"
chmod +x "$APPDIR/backend/sfo-backend"

mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"
python3 packaging/scripts/gen_icon.py \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps/smartfileorganizer.png"
cp "$APPDIR/usr/share/icons/hicolor/256x256/apps/smartfileorganizer.png" \
    "$APPDIR/smartfileorganizer.png"

bash packaging/scripts/create_appdir.sh "$APPDIR" "$APP_NAME"
ok "AppDir listo"

# ── 7. Generar AppImage ────────────────────────────────────────────────────────

step "7/7" "Generando AppImage..."

ARCH=$(uname -m)
OUTPUT="$INSTALLER_DIR/${APP_NAME}-${APP_VERSION}-${ARCH}.AppImage"
ARCH=$ARCH "$APPIMAGETOOL" "$APPDIR" "$OUTPUT"
chmod +x "$OUTPUT"

echo ""
echo "========================================================="
ok "LISTO"
info "AppImage: $OUTPUT"
info "Ejecutar con: chmod +x $(basename $OUTPUT) && ./$(basename $OUTPUT)"
echo "========================================================="