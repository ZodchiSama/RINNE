; Inno Setup script for the Rinne installer. Built by CI:
;   iscc /DAppVersion=0.5.0 /DSourceDir=dist\Rinne packaging\windows\rinne.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\Rinne"
#endif

[Setup]
AppId={{37836B52-28BA-47C5-820A-FF90C2A131FF}
AppName=Rinne
AppVersion={#AppVersion}
AppVerName=Rinne {#AppVersion}
AppPublisher=Zodchi
AppPublisherURL=https://github.com/ZodchiSama/RINNE
AppSupportURL=https://github.com/ZodchiSama/RINNE/issues
AppContact=zodchi.san@proton.me
DefaultDirName={autopf}\Rinne
DefaultGroupName=Rinne
DisableProgramGroupPage=yes
; Per-user install by default (no admin prompt); users can choose "all users" instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\..\LICENSE
SetupIconFile=..\..\rinne\assets\icon.ico
UninstallDisplayIcon={app}\Rinne.exe
UninstallDisplayName=Rinne
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=Rinne-Setup-{#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; AppUserModelID matches the one Rinne sets at startup, so the taskbar and notifications show Rinne.
Name: "{group}\Rinne"; Filename: "{app}\Rinne.exe"; AppUserModelID: "Zodchi.Rinne"
Name: "{autodesktop}\Rinne"; Filename: "{app}\Rinne.exe"; AppUserModelID: "Zodchi.Rinne"; Tasks: desktopicon

[Run]
Filename: "{app}\Rinne.exe"; Description: "{cm:LaunchProgram,Rinne}"; Flags: nowait postinstall skipifsilent

; Your library and settings (%APPDATA%\rinne) are kept on uninstall.
