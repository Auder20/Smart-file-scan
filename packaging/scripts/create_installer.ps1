param([string]$Version, [string]$Root, [string]$AppName)

$iss = @"
#define MyAppName    "$AppName"
#define MyAppVersion "$Version"
#define AppDir       "$Root\dist\win\frontend\$AppName"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Smart File Organizer
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=$Root\dist\installer
OutputBaseFilename=$AppName-$Version-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}";            Filename: "{app}\SmartFileOrganizerLauncher.vbs"
Name: "{autodesktop}\{#MyAppName}";       Filename: "{app}\SmartFileOrganizerLauncher.vbs"; Tasks: desktopicon
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "wscript.exe"; Parameters: """{app}\SmartFileOrganizerLauncher.vbs"""; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent
"@

New-Item -ItemType Directory -Force dist/installer | Out-Null
$iss | Out-File -FilePath dist/installer/installer.iss -Encoding UTF8
Write-Host "ISS generado OK"
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" dist\installer\installer.iss