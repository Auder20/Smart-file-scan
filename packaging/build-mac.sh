#!/usr/bin/env bash
# ============================================================
#  Smart File Organizer — macOS Package Builder
#  Genera: SmartFileOrganizer-1.0.0.dmg
#
#  Requisitos:
#    - Java 21 JDK  (con jpackage)
#    - Python 3.11+
#    - Maven 3.8+
#    - Xcode Command Line Tools
#    - create-dmg (opcional): brew install create-dmg
# ============================================================
set -euo pipefail

APP_NAME="SmartFileOrganizer"
APP_DISPLAY_NAME="Smart File Organizer"
APP_VERSION="1.0.0"
BUNDLE_ID="com.smartfileorganizer.app"
MAIN_CLASS="com.smartfileorganizer.Main"
DIST_DIR="dist/mac"
BACKEND_DIST="$DIST_DIR/backend"
FRONTEND_DIST="$DIST_DIR/frontend"
INSTALLER_DIR="dist/installer"
SIGN_IDENTITY=""

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
step()  { echo -e "\n${BLUE}[STEP $1]${NC} $2"; }

echo ""
echo "========================================================="
echo "  Smart File Organizer — macOS Package Builder"
echo "========================================================="
echo ""

ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    info "Arquitectura: Apple Silicon (arm64)"
    JAVAFX_PLATFORM="mac-aarch64"
else
    info "Arquitectura: Intel (x86_64)"
    JAVAFX_PLATFORM="mac"
fi

# ── 1. Verificar herramientas ──────────────────────────────────────────────────

step "1/7" "Verificando herramientas necesarias..."

xcode-select -p >/dev/null 2>&1 || error "Xcode Command Line Tools no encontrado.\n  Instala con: xcode-select --install"
ok "Xcode Command Line Tools encontrado"

command -v java >/dev/null 2>&1 || { warn "Java no encontrado. Instalando..."; brew install --cask temurin@21; }
JAVA_VER=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
[[ "$JAVA_VER" -ge 21 ]] || error "Necesitas Java 21+. Tienes Java $JAVA_VER."
ok "Java $JAVA_VER encontrado"

command -v jpackage >/dev/null 2>&1 || error "jpackage no encontrado."
ok "jpackage encontrado"

command -v python3 >/dev/null 2>&1 || { warn "Python3 no encontrado. Instalando..."; brew install python@3.11; }
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PY_VER encontrado"

command -v mvn >/dev/null 2>&1 || { warn "Maven no encontrado. Instalando..."; brew install maven; }
ok "Maven encontrado"

if command -v create-dmg >/dev/null 2>&1; then
    USE_CREATE_DMG=true; ok "create-dmg encontrado"
else
    USE_CREATE_DMG=false; warn "create-dmg no encontrado. Se usara hdiutil. Para instalar: brew install create-dmg"
fi

# ── 2. Limpiar ─────────────────────────────────────────────────────────────────

step "2/7" "Limpiando builds anteriores..."
rm -rf "$DIST_DIR" "$INSTALLER_DIR"
mkdir -p "$BACKEND_DIST" "$FRONTEND_DIST" "$INSTALLER_DIR"
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
    --target-arch "$ARCH" \
    --noconfirm \
    main.py

deactivate
cd ..
ok "Backend empaquetado: $BACKEND_DIST/sfo-backend"

# ── 4. Compilar frontend ────────────────────────────────────────────────────────

step "4/7" "Compilando frontend con Maven..."
cd frontend
mvn clean package -DskipTests -q -Djavafx.platform="$JAVAFX_PLATFORM"
cd ..
ok "Frontend compilado"

# ── 5. Empaquetar con jpackage ─────────────────────────────────────────────────

step "5/7" "Empaquetando frontend con jpackage (incluye JRE)..."

JPACKAGE_ARGS=(
    --type app-image
    --name "$APP_NAME"
    --app-version "$APP_VERSION"
    --input frontend/target
    --dest "$FRONTEND_DIST"
    --main-jar frontend-1.0.0.jar
    --main-class "$MAIN_CLASS"
    --java-options "--enable-preview"
    --java-options "-Xmx512m"
    --java-options "--add-opens=javafx.graphics/com.sun.javafx.application=ALL-UNNAMED"
    --mac-package-identifier "$BUNDLE_ID"
    --mac-package-name "$APP_DISPLAY_NAME"
)

if [[ -n "$SIGN_IDENTITY" ]]; then
    JPACKAGE_ARGS+=(--mac-sign --mac-signing-key-user-name "$SIGN_IDENTITY")
fi

jpackage "${JPACKAGE_ARGS[@]}"
ok "Frontend empaquetado: $FRONTEND_DIST/$APP_NAME.app"

# ── 6. Configurar bundle ───────────────────────────────────────────────────────

step "6/7" "Configurando bundle .app unificado..."

APP_BUNDLE="$FRONTEND_DIST/$APP_NAME.app"
mkdir -p "$APP_BUNDLE/Contents/MacOS/backend"
cp "$BACKEND_DIST/sfo-backend" "$APP_BUNDLE/Contents/MacOS/backend/"
chmod +x "$APP_BUNDLE/Contents/MacOS/backend/sfo-backend"

# FIX: renombrar launcher original antes de crear el nuevo
mv "$APP_BUNDLE/Contents/MacOS/$APP_NAME" "$APP_BUNDLE/Contents/MacOS/${APP_NAME}-ui"

# FIX: usar heredoc con comillas dobles para que $APP_NAME se expanda correctamente
# El script original usaba << 'LAUNCHER' (comillas simples) lo que impedía la expansión
cat > "$APP_BUNDLE/Contents/MacOS/$APP_NAME" << LAUNCHER
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

chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
xattr -cr "$APP_BUNDLE" 2>/dev/null || true
ok "Bundle .app configurado"

# ── 7. Crear DMG ───────────────────────────────────────────────────────────────

step "7/7" "Creando DMG..."

DMG_OUTPUT="$INSTALLER_DIR/${APP_NAME}-${APP_VERSION}.dmg"

if [[ "$USE_CREATE_DMG" == true ]]; then
    create-dmg \
        --volname "$APP_DISPLAY_NAME" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "${APP_NAME}.app" 150 185 \
        --hide-extension "${APP_NAME}.app" \
        --app-drop-link 450 185 \
        --no-internet-enable \
        "$DMG_OUTPUT" \
        "$FRONTEND_DIST/"
else
    TEMP_DMG="$DIST_DIR/temp.dmg"
    hdiutil create -size 800m -fs HFS+ -volname "$APP_DISPLAY_NAME" "$TEMP_DMG"
    MOUNT_POINT=$(hdiutil attach "$TEMP_DMG" | grep Volumes | awk '{print $3}')
    cp -r "$APP_BUNDLE" "$MOUNT_POINT/"
    ln -s /Applications "$MOUNT_POINT/Applications"
    hdiutil detach "$MOUNT_POINT"
    hdiutil convert "$TEMP_DMG" -format UDZO -o "$DMG_OUTPUT"
    rm "$TEMP_DMG"
fi

echo ""
echo "========================================================="
ok "LISTO"
info "DMG: $DMG_OUTPUT"
[[ -z "$SIGN_IDENTITY" ]] && warn "Sin firma: el usuario vera aviso de Gatekeeper. Clic derecho -> Abrir."
echo "========================================================="