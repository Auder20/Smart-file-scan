param([string]$AppDir)

New-Item -ItemType Directory -Force "$AppDir/backend" | Out-Null

$launcher = @"
@echo off
set DIR=%~dp0
set DATA_DIR=%APPDATA%\SmartFileOrganizer
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
start "" /B "%DIR%backend\sfo-backend.exe"
set /a tries=0
:wait
timeout /t 1 /nobreak >nul
curl -sf http://127.0.0.1:8000/api/health >nul 2>&1
if %errorlevel%==0 goto :ready
set /a tries+=1
if %tries% lss 15 goto :wait
:ready
start "" "%DIR%SmartFileOrganizer.exe"
"@
[System.IO.File]::WriteAllText("$AppDir\launcher.bat", $launcher)

$vbs = @"
Set WShell = CreateObject("WScript.Shell")
WShell.Run Chr(34) & WScript.ScriptFullName & "\..\launcher.bat" & Chr(34), 0, False
"@
[System.IO.File]::WriteAllText("$AppDir\SmartFileOrganizerLauncher.vbs", $vbs)
Write-Host "Launcher creado OK"