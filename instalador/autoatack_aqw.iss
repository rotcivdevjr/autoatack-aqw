; Instalador do AutoAtack AQW (Inno Setup 6)
; Instala na pasta do usuário: não pede senha de administrador e o app consegue se atualizar.
; O AppId NUNCA pode mudar, senão o Windows trata cada versão como outro programa.

#define AppName "AutoAtack AQW"
#define AppExe "AutoAtack AQW.exe"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{656AA28D-D5E6-45D7-ACAE-49FC868BA2BE}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=AutoAtack AQW
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\AutoAtack AQW
DefaultGroupName={#AppName}
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\saida
OutputBaseFilename=AutoAtack-AQW-Setup-{#AppVersion}
SetupIconFile=..\assets\icone.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; numa atualização, apaga as bibliotecas da versão anterior antes de copiar as novas
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\AutoAtack AQW\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; sem "skipifsilent": depois de uma atualização silenciosa, o app abre de novo sozinho
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall
