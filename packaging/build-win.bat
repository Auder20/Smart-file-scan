@echo off
setlocal enabledelayedexpansion

:: ============================================================
::  Smart File Organizer — Windows Installer Builder
::  Genera: SmartFileOrganizer-1.0.0-setup.exe
::
::  Requisitos:
::    - Java 21 JDK  (con jpackage incluido)
::    - Python 3.11+
::    - Maven 3.8+
::    - Inno Setup 6  (https://jrsoftware.org/isdl.php)
:: ============================================================

set APP_NAME=SmartFileOrganizer
set APP_VERSION=1.0.0
set MAIN_CLASS=com.smartfileorganizer.Main
set DIST_DIR=dist\win
set BACKEND_DIST=dist\win\backend
set FRONTEND_DIST=dist\win\frontend
set INSTALLER_DIR=dist\installer

echo.
echo [INFO] ================================================
echo [INFO]  Smart File Organizer — Windows Package Builder
echo [INFO] ================================================
echo.

:: ── 1. Verificar herramientas ─────────────────────────────────────────────────

echo [STEP 1/8] Verificando herramientas necesarias...

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
    echo [ERROR] jpackage no encontrado. Asegurate de tener JDK 21 completo.
    goto :error
)
echo [OK] jpackage encontrado

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python no encontrado.
    goto :error
)
echo [OK] Python encontrado

mvn --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Maven no encontrado.
    goto :error
)
echo [OK] Maven encontrado

set INNO_PATH=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set INNO_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set INNO_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
if %INNO_PATH%=="" (
    echo [ERROR] Inno Setup 6 no encontrado. Descargalo desde: https://jrsoftware.org/isdl.php
    goto :error
)
echo [OK] Inno Setup encontrado en %INNO_PATH%

:: ── 2. Limpiar ────────────────────────────────────────────────────────────────

echo.
echo [STEP 2/8] Limpiando builds anteriores...
if exist "%DIST_DIR%"      rmdir /s /q "%DIST_DIR%"
if exist "%INSTALLER_DIR%" rmdir /s /q "%INSTALLER_DIR%"
mkdir "%BACKEND_DIST%"
mkdir "%FRONTEND_DIST%"
mkdir "%INSTALLER_DIR%"
echo [OK] Directorios limpios

:: ── 3. Empaquetar backend con PyInstaller ─────────────────────────────────────

echo.
echo [STEP 3/8] Empaquetando backend Python con PyInstaller...

cd backend

if exist ".venv-pkg" rmdir /s /q ".venv-pkg"
python -m venv .venv-pkg
call .venv-pkg\Scripts\activate.bat

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
pip install --quiet pyinstaller

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
    --hidden-import=multiprocessing ^
    --hidden-import=sqlite3 ^
    --collect-all fastapi ^
    --collect-all pydantic ^
    --collect-all uvicorn ^
    --collect-all starlette ^
    --collect-all sqlalchemy ^
    --noconfirm ^
    main.py

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller fallo.
    call deactivate
    cd ..
    goto :error
)

call deactivate
cd ..
echo [OK] Backend empaquetado: %BACKEND_DIST%\sfo-backend.exe

:: ── 4. Compilar frontend con Maven ────────────────────────────────────────────

echo.
echo [STEP 4/8] Compilando frontend con Maven...

cd frontend
mvn clean package -DskipTests -q

if %errorlevel% neq 0 (
    echo [ERROR] Maven fallo al compilar el frontend.
    cd ..
    goto :error
)

cd ..
echo [OK] Frontend compilado

:: ── 5. Empaquetar frontend con jpackage ───────────────────────────────────────

echo.
echo [STEP 5/8] Empaquetando frontend con jpackage...

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
    --java-options "--add-opens=javafx.graphics/com.sun.javafx.application=ALL-UNNAMED"

if %errorlevel% neq 0 (
    echo [ERROR] jpackage fallo.
    goto :error
)

echo [OK] Frontend empaquetado: %FRONTEND_DIST%\%APP_NAME%

:: ── 6. Crear launcher que arranca backend + frontend ──────────────────────────

echo.
echo [STEP 6/8] Creando launcher...

mkdir "%FRONTEND_DIST%\%APP_NAME%\backend"
copy "%BACKEND_DIST%\sfo-backend.exe" "%FRONTEND_DIST%\%APP_NAME%\backend\sfo-backend.exe" >nul

set LAUNCHER=%FRONTEND_DIST%\%APP_NAME%\launcher.bat
(
echo @echo off
echo set DIR=%%~dp0
echo set DATA_DIR=%%APPDATA%%\SmartFileOrganizer
echo if not exist "%%DATA_DIR%%" mkdir "%%DATA_DIR%%"
echo start "" /B "%%DIR%%backend\sfo-backend.exe"
echo set /a tries=0
echo :wait
echo timeout /t 1 /nobreak >nul
echo curl -sf http://127.0.0.1:8000/api/health >nul 2>&1
echo if %%errorlevel%%==0 goto :ready
echo set /a tries+=1
echo if %%tries%% lss 15 goto :wait
echo :ready
echo start "" "%%DIR%%%APP_NAME%.exe"
) > "%LAUNCHER%"

:: FIX: usar Left+InStrRev para extraer correctamente la carpeta del script
:: WScript.ScriptFullName devuelve la ruta completa del .vbs, no su directorio.
:: La concatenacion directa con "\..\launcher.bat" producía rutas inválidas.
set VBS_LAUNCHER=%FRONTEND_DIST%\%APP_NAME%\SmartFileOrganizerLauncher.vbs
(
echo Dim scriptDir
echo scriptDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
echo Set WShell = CreateObject("WScript.Shell"^)
echo WShell.Run Chr(34^) ^& scriptDir ^& "launcher.bat" ^& Chr(34^), 0, False
) > "%VBS_LAUNCHER%"

echo [OK] Launcher creado

:: ── 7. Generar script Inno Setup ─────────────────────────────────────────────

echo.
echo [STEP 7/8] Generando script de Inno Setup...

set SCRIPT_ROOT=%CD%

(
echo #define MyAppName      "%APP_NAME%"
echo #define MyAppVersion   "%APP_VERSION%"
echo #define MyAppPublisher "Smart File Organizer"
echo #define MyAppExeName   "%APP_NAME%.exe"
echo #define AppDir         "%SCRIPT_ROOT%\%FRONTEND_DIST%\%APP_NAME%"
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
echo Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
echo.
echo [Icons]
echo Name: "{group}\{#MyAppName}";            Filename: "{app}\SmartFileOrganizerLauncher.vbs"
echo Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
echo Name: "{autodesktop}\{#MyAppName}";       Filename: "{app}\SmartFileOrganizerLauncher.vbs"; Tasks: desktopicon
echo.
echo [Registry]
echo Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ^
echo       ValueType: string; ValueName: "{#MyAppName}"; ^
echo       ValueData: """{app}\SmartFileOrganizerLauncher.vbs"""; ^
echo       Flags: uninsdeletevalue; Tasks: startupicon
echo.
echo [Run]
echo Filename: "wscript.exe"; Parameters: """{app}\SmartFileOrganizerLauncher.vbs"""; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent
) > "%INSTALLER_DIR%\installer.iss"

echo [OK] Script ISS generado

:: ── 8. Compilar instalador ────────────────────────────────────────────────────

echo.
echo [STEP 8/8] Compilando instalador .exe con Inno Setup...

%INNO_PATH% "%INSTALLER_DIR%\installer.iss"

if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup fallo.
    goto :error
)

echo.
echo ============================================================
echo  LISTO
echo  Instalador: %INSTALLER_DIR%\%APP_NAME%-%APP_VERSION%-setup.exe
echo ============================================================
echo.
goto :end

:error
echo.
echo [ERROR] El proceso fallo. Revisa los mensajes anteriores.
pause
exit /b 1

:end
pause