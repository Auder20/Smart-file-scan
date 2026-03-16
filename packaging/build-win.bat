@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  Smart File Organizer — Windows Installer Builder
::  Genera: SmartFileOrganizer-1.0.0-setup.exe
::
::  Requisitos en la maquina que ejecuta este script:
::    - Java 21 JDK  (con jpackage incluido)
::    - Python 3.11+
::    - Maven 3.8+
::    - Inno Setup 6  (https://jrsoftware.org/isdl.php)
::
::  El instalador resultante NO requiere nada instalado
::  en la maquina del usuario final.
:: ============================================================

set APP_NAME=SmartFileOrganizer
set APP_VERSION=1.0.0
set MAIN_CLASS=com.smartfileorganizer.Main
set MODULE_PATH=com.smartfileorganizer
set DIST_DIR=dist\win
set BACKEND_DIST=dist\win\backend
set FRONTEND_DIST=dist\win\frontend
set INSTALLER_DIR=dist\installer

echo.
echo [INFO] ================================================
echo [INFO]  Smart File Organizer — Windows Package Builder
echo [INFO] ================================================
echo.

:: ── 1. Verificar herramientas ────────────────────────────────────────────────

echo [STEP 1/7] Verificando herramientas necesarias...

java -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Java no encontrado. Instala JDK 21 desde: https://adoptium.net/
    goto :error
)
for /f "tokens=3" %%i in ('java -version 2^>^&1 ^| findstr /i "version"') do set JAVA_VER=%%i
set JAVA_VER=!JAVA_VER:"=!
for /f "tokens=1 delims=." %%a in ("!JAVA_VER!") do set JAVA_MAJOR=%%a
if !JAVA_MAJOR! lss 21 (
    echo [ERROR] Necesitas Java 21+. Tienes Java !JAVA_MAJOR!.
    goto :error
)
echo [OK] Java !JAVA_MAJOR! encontrado

jpackage --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] jpackage no encontrado. Asegurate de tener JDK 21 completo, no solo JRE.
    goto :error
)
echo [OK] jpackage encontrado

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado. Instala Python 3.11+ desde: https://www.python.org/
    goto :error
)
echo [OK] Python encontrado

mvn --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Maven no encontrado. Instala Maven desde: https://maven.apache.org/
    goto :error
)
echo [OK] Maven encontrado

:: Buscar Inno Setup en ubicaciones comunes
set INNO_PATH=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set INNO_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
if %INNO_PATH%=="" (
    echo [ERROR] Inno Setup 6 no encontrado.
    echo [ERROR] Descargalo desde: https://jrsoftware.org/isdl.php
    echo [ERROR] Luego vuelve a ejecutar este script.
    goto :error
)
echo [OK] Inno Setup encontrado en %INNO_PATH%

:: ── 2. Limpiar directorios previos ──────────────────────────────────────────

echo.
echo [STEP 2/7] Limpiando builds anteriores...
if exist "%DIST_DIR%"      rmdir /s /q "%DIST_DIR%"
if exist "%INSTALLER_DIR%" rmdir /s /q "%INSTALLER_DIR%"
mkdir "%BACKEND_DIST%"
mkdir "%FRONTEND_DIST%"
mkdir "%INSTALLER_DIR%"
echo [OK] Directorios limpios

:: ── 3. Empaquetar backend con PyInstaller ────────────────────────────────────

echo.
echo [STEP 3/7] Empaquetando backend Python con PyInstaller...

cd backend

:: Crear/activar venv limpio para el empaquetado
if exist ".venv-pkg" rmdir /s /q ".venv-pkg"
python -m venv .venv-pkg
call .venv-pkg\Scripts\activate.bat

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

:: PyInstaller: un solo .exe que incluye Python + todas las dependencias
pyinstaller --onefile ^
    --name sfo-backend ^
    --distpath "..\%BACKEND_DIST%" ^
    --workpath "..\dist\win\pyinstaller-tmp" ^
    --specpath "..\dist\win" ^
    --hidden-import=uvicorn.logging ^
    --hidden-import=uvicorn.loops ^
    --hidden-import=uvicorn.loops.auto ^
    --hidden-import=uvicorn.protocols ^
    --hidden-import=uvicorn.protocols.http ^
    --hidden-import=uvicorn.protocols.http.auto ^
    --hidden-import=uvicorn.protocols.websockets ^
    --hidden-import=uvicorn.protocols.websockets.auto ^
    --hidden-import=uvicorn.lifespan ^
    --hidden-import=uvicorn.lifespan.on ^
    --hidden-import=anyio._backends._asyncio ^
    --hidden-import=anyio._backends._trio ^
    --collect-all fastapi ^
    --collect-all pydantic ^
    --noconfirm ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller fallo al empaquetar el backend.
    cd ..
    goto :error
)

call deactivate
cd ..
echo [OK] Backend empaquetado: %BACKEND_DIST%\sfo-backend.exe

:: ── 4. Compilar frontend con Maven ──────────────────────────────────────────

echo.
echo [STEP 4/7] Compilando frontend con Maven...

cd frontend

:: Agregar plugin shade al vuelo si no existe en pom.xml
:: (para generar un fat-jar con todas las dependencias)
mvn clean package -DskipTests ^
    -Dmaven.compiler.source=21 ^
    -Dmaven.compiler.target=21

if %errorlevel% neq 0 (
    echo [ERROR] Maven fallo al compilar el frontend.
    cd ..
    goto :error
)

cd ..
echo [OK] Frontend compilado

:: ── 5. Empaquetar frontend con jpackage ─────────────────────────────────────

echo.
echo [STEP 5/7] Empaquetando frontend con jpackage (incluye JRE)...

:: jpackage genera una carpeta con el ejecutable + JRE propio
:: El usuario final NO necesita Java instalado
jpackage ^
    --type app-image ^
    --name "%APP_NAME%" ^
    --app-version "%APP_VERSION%" ^
    --input frontend\target ^
    --dest "%FRONTEND_DIST%" ^
    --main-jar frontend-1.0.0.jar ^
    --main-class "%MAIN_CLASS%" ^
    --java-options "--enable-preview" ^
    --java-options "-Xmx512m" ^
    --java-options "--add-opens=javafx.graphics/com.sun.javafx.application=ALL-UNNAMED" ^
    --win-console

if %errorlevel% neq 0 (
    echo [ERROR] jpackage fallo. Asegurate de que frontend\target\frontend-1.0.0.jar existe.
    goto :error
)

echo [OK] Frontend empaquetado: %FRONTEND_DIST%\%APP_NAME%

:: ── 6. Generar script Inno Setup ────────────────────────────────────────────

echo.
echo [STEP 6/7] Generando script de Inno Setup...

:: Construir la ruta absoluta para el script ISS
set SCRIPT_ROOT=%CD%

(
echo #define MyAppName      "%APP_NAME%"
echo #define MyAppVersion   "%APP_VERSION%"
echo #define MyAppPublisher "Smart File Organizer"
echo #define MyAppExeName   "%APP_NAME%.exe"
echo #define FrontendDir    "%SCRIPT_ROOT%\%FRONTEND_DIST%\%APP_NAME%"
echo #define BackendExe     "%SCRIPT_ROOT%\%BACKEND_DIST%\sfo-backend.exe"
echo.
echo [Setup]
echo AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
echo AppName={#MyAppName}
echo AppVersion={#MyAppVersion}
echo AppPublisher={#MyAppPublisher}
echo DefaultDirName={autopf}\{#MyAppName}
echo DefaultGroupName={#MyAppName}
echo AllowNoIcons=yes
echo OutputDir=%SCRIPT_ROOT%\%INSTALLER_DIR%
echo OutputBaseFilename=%APP_NAME%-%APP_VERSION%-setup
echo Compression=lzma2/ultra64
echo SolidCompression=yes
echo WizardStyle=modern
echo PrivilegesRequired=lowest
echo ArchitecturesAllowed=x64
echo ArchitecturesInstallIn64BitMode=x64
echo.
echo [Languages]
echo Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
echo Name: "english"; MessagesFile: "compiler:Default.isl"
echo.
echo [Tasks]
echo Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
echo Name: "startupicon"; Description: "Iniciar con Windows"; GroupDescription: "Inicio automatico"; Flags: unchecked
echo.
echo [Files]
echo ; Frontend (JavaFX app con JRE incluido^)
echo Source: "{#FrontendDir}\*"; DestDir: "{app}\frontend"; Flags: ignoreversion recursesubdirs createallsubdirs
echo ; Backend (Python empaquetado^)
echo Source: "{#BackendExe}";    DestDir: "{app}\backend"; Flags: ignoreversion
echo ; Archivo de configuracion por defecto
echo Source: "%SCRIPT_ROOT%\.env"; DestDir: "{app}"; DestName: ".env.default"; Flags: ignoreversion
echo.
echo [Icons]
echo Name: "{group}\{#MyAppName}";           Filename: "{app}\frontend\{#MyAppExeName}"
echo Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
echo Name: "{autodesktop}\{#MyAppName}";      Filename: "{app}\frontend\{#MyAppExeName}"; Tasks: desktopicon
echo.
echo [Registry]
echo ; Arranque automatico con Windows (opcional^)
echo Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ^
echo       ValueType: string; ValueName: "{#MyAppName}-backend"; ^
echo       ValueData: """{app}\backend\sfo-backend.exe"""; ^
echo       Flags: uninsdeletevalue; Tasks: startupicon
echo.
echo [Run]
echo ; Crear .env en el directorio de instalacion si no existe
echo Filename: "{cmd}"; Parameters: "/c if not exist ""{app}\.env"" copy ""{app}\.env.default"" ""{app}\.env"""; Flags: runhidden
echo ; Abrir la app al terminar la instalacion (opcional^)
echo Filename: "{app}\frontend\{#MyAppExeName}"; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent
echo.
echo [Code]
echo procedure CurStepChanged(CurStep: TSetupStep^);
echo var
echo   EnvFile: string;
echo   Lines: TArrayOfString;
echo begin
echo   if CurStep = ssPostInstall then
echo   begin
echo     EnvFile := ExpandConstant('{app}\.env'^);
echo     if not FileExists(EnvFile^) then
echo     begin
echo       SetArrayLength(Lines, 4^);
echo       Lines[0] := 'HOST_SCAN_PATH=C:\Users';
echo       Lines[1] := 'BACKEND_HOST=127.0.0.1';
echo       Lines[2] := 'BACKEND_PORT=8000';
echo       Lines[3] := 'HOST_ROOT=';
echo       SaveStringsToFile(EnvFile, Lines, False^);
echo     end;
echo   end;
echo end;
) > "%INSTALLER_DIR%\installer.iss"

echo [OK] Script ISS generado

:: ── 7. Compilar instalador con Inno Setup ────────────────────────────────────

echo.
echo [STEP 7/7] Compilando instalador .exe con Inno Setup...

%INNO_PATH% "%INSTALLER_DIR%\installer.iss"

if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup fallo al compilar el instalador.
    goto :error
)

echo.
echo ============================================================
echo  LISTO
echo  Instalador generado en:
echo  %INSTALLER_DIR%\%APP_NAME%-%APP_VERSION%-setup.exe
echo ============================================================
echo.
goto :end

:error
echo.
echo [ERROR] El proceso de empaquetado fallo. Revisa los mensajes anteriores.
pause
exit /b 1

:end
pause