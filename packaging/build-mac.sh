#!/usr/bin/env bash
# ============================================================
#  Smart File Organizer — macOS Package Builder
#  Genera: SmartFileOrganizer-1.0.0.dmg
#
#  Requisitos en la maquina que ejecuta este script:
#    - Java 21 JDK  (con jpackage)
#    - Python 3.11+
#    - Maven 3.8+
#    - Xcode Command Line Tools (para create-dmg / hdiutil)
#    - create-dmg (opcional, para DMG bonito):
#        brew install create-dmg
#
#  El .dmg resultante NO requiere nada instalado
#  en la maquina del usuario final.
#
#  NOTA: Para distribuir en Mac App Store o sin el aviso
#  de Gatekeeper necesitas una Apple Developer ID (~$99/año).
#  Sin firma el usuario hace: clic derecho → Abrir → Abrir.
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

# Opcional: firma de código (requiere Apple Developer ID)
# Deja vacío para omitir firma (usuarios verán advertencia Gatekeeper)
SIGN_IDENTITY=""
# SIGN_IDENTITY="Developer ID Application: Tu Nombre (XXXXXXXXXX)"

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

# ── Detectar arquitectura ──────────────────────────────────────────────────────
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

# Xcode CLI tools
xcode-select -p >/dev/null 2>&1 || error "Xcode Command Line Tools no encontrado.\n  Instala con: xcode-select --install"
ok "Xcode Command Line Tools encontrado"

# Java
command -v java >/dev/null 2>&1 || {
    warn "Java no encontrado. Instalando con Homebrew..."
    brew install --cask temurin@21
}
JAVA_VER=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
[[ "$JAVA_VER" -ge 21 ]] || error "Necesitas Java 21+. Tienes Java $JAVA_VER."
ok "Java $JAVA_VER encontrado"

command -v jpackage >/dev/null 2>&1 || error "jpackage no encontrado. Asegurate de tener el JDK completo."
ok "jpackage encontrado"

# Python
command -v python3 >/dev/null 2>&1 || {
    warn "Python3 no encontrado. Instalando con Homebrew..."
    brew install python@3.11
}
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Python $PY_VER encontrado"

# Maven
command -v mvn >/dev/null 2>&1 || {
    warn "Maven no encontrado. Instalando con Homebrew..."
    brew install maven
}
ok "Maven encontrado"

# create-dmg (opcional, para DMG con fondo personalizado)
if command -v create-dmg >/dev/null 2>&1; then
    USE_CREATE_DMG=true
    ok "create-dmg encontrado (DMG con estilo)"
else
    USE_CREATE_DMG=false
    warn "create-dmg no encontrado. Se usara hdiutil (DMG basico)."
    warn "Para instalar: brew install create-dmg"
fi

# ── 2. Limpiar directorios previos ─────────────────────────────────────────────

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
    --collect-all fastapi \
    --collect-all pydantic \
    --target-arch "$ARCH" \
    --noconfirm \
    main.py

deactivate
cd ..
ok "Backend empaquetado: $BACKEND_DIST/sfo-backend"

# ── 4. Compilar frontend con Maven ─────────────────────────────────────────────

step "4/7" "Compilando frontend con Maven..."
cd frontend
mvn clean package -DskipTests -q -Djavafx.platform="$JAVAFX_PLATFORM"
cd ..
ok "Frontend compilado"

# ── 5. Empaquetar frontend con jpackage ────────────────────────────────────────

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

# Agregar firma si se configuró
if [[ -n "$SIGN_IDENTITY" ]]; then
    JPACKAGE_ARGS+=(--mac-sign --mac-signing-key-user-name "$SIGN_IDENTITY")
    info "Firmando con: $SIGN_IDENTITY"
fi

jpackage "${JPACKAGE_ARGS[@]}"

ok "Frontend empaquetado: $FRONTEND_DIST/$APP_NAME.app"

# ── 6. Crear bundle .app que lanza backend + frontend ─────────────────────────

step "6/7" "Configurando bundle .app unificado..."

APP_BUNDLE="$FRONTEND_DIST/$APP_NAME.app"

# Copiar backend dentro del .app bundle
mkdir -p "$APP_BUNDLE/Contents/MacOS/backend"
cp "$BACKEND_DIST/sfo-backend" "$APP_BUNDLE/Contents/MacOS/backend/"
chmod +x "$APP_BUNDLE/Contents/MacOS/backend/sfo-backend"

# Renombrar el launcher original de jpackage y crear uno nuevo que arranca ambos
ORIGINAL_LAUNCHER="$APP_BUNDLE/Contents/MacOS/$APP_NAME"
mv "$ORIGINAL_LAUNCHER" "$APP_BUNDLE/Contents/MacOS/${APP_NAME}-ui"

cat > "$ORIGINAL_LAUNCHER" << LAUNCHER
#!/bin/bash
# Launcher principal del bundle .app
# Arranca el backend FastAPI y luego el frontend JavaFX

DIR="\$(cd "\$(dirname "\$0")" && pwd)"
BACKEND="\$DIR/backend/sfo-backend"
FRONTEND="\$DIR/${APP_NAME}-ui"

# Directorio de datos del usuario
DATA_DIR="\$HOME/.smartfileorganizer"
mkdir -p "\$DATA_DIR"

# Crear .env si no existe
if [ ! -f "\$DATA_DIR/.env" ]; then
    cat > "\$DATA_DIR/.env" << 'ENV'
HOST_SCAN_PATH=/Users
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
REDIS_HOST=localhost
REDIS_PORT=6379
HOST_ROOT=
DB_PATH=~/.smartfileorganizer/sfo.db
ENV
fi

# Arrancar backend
export DB_PATH="\$DATA_DIR/sfo.db"
"\$BACKEND" &
BACKEND_PID=\$!

# Esperar a que el backend esté listo
for i in \$(seq 1 20); do
    if curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Arrancar frontend
"\$FRONTEND"
FRONTEND_EXIT=\$?

# Apagar backend
kill "\$BACKEND_PID" 2>/dev/null
wait "\$BACKEND_PID" 2>/dev/null

exit \$FRONTEND_EXIT
LAUNCHER

chmod +x "$ORIGINAL_LAUNCHER"

# Quitar atributos de cuarentena de Gatekeeper en los binarios
xattr -cr "$APP_BUNDLE" 2>/dev/null || true

ok "Bundle .app configurado"

# ── 7. Crear DMG ───────────────────────────────────────────────────────────────

step "7/7" "Creando DMG..."

DMG_OUTPUT="$INSTALLER_DIR/${APP_NAME}-${APP_VERSION}.dmg"

if [[ "$USE_CREATE_DMG" == true ]]; then
    # DMG con fondo personalizado y layout tipo "arrastra a Applications"
    create-dmg \
        --volname "$APP_DISPLAY_NAME" \
        --volicon "$APP_BUNDLE/Contents/Resources/$APP_NAME.icns" \
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
    # DMG basico con hdiutil (incluido en macOS)
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
info "DMG generado:"
info "  $DMG_OUTPUT"
info ""
info "El usuario instala arrastrando la app a la carpeta Applications."
info "No requiere instalar Java, Python ni nada mas."
if [[ -z "$SIGN_IDENTITY" ]]; then
    warn ""
    warn "Sin firma de codigo: el usuario vera un aviso de Gatekeeper."
    warn "Instruccion para el usuario: clic derecho -> Abrir -> Abrir."
    warn "Para firmar, configura SIGN_IDENTITY en este script."
fi
echo "========================================================="