; Inno Setup: transforma dist\MetaOverlay no instalador MetaOverlay-Setup.exe
#define AppName "Meta Overlay"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "MetaOverlay.exe"
; nomes antigos do programa (para atualizar quem já tinha instalado)
#define OldExe "Aion2Overlay.exe"
#define OldName "Aion 2 Overlay"
#define OldExe2 "AtreiaCode.exe"
#define OldName2 "Atreia Code"
; instalador oficial do Npcap (baixado na hora da instalação; a licença gratuita não permite embutir)
#define NpcapUrl "https://npcap.com/dist/npcap-1.89.exe"
; SHA-256 do instalador do Npcap (o build confere a assinatura e passa com /DNpcapSha256=...);
; o download só é aceito se bater
#ifndef NpcapSha256
  #define NpcapSha256 "8aed85e900d783d1308506e919587d3e540451947af8a82f2d04f819e44305cc"
#endif

[Setup]
AppId={{6C1E7A52-3F0B-4F57-9C2B-A2A10E2C0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Meta Overlay
DefaultDirName={localappdata}\Programs\MetaOverlay
; sempre na pasta nova: a versão anterior é desinstalada antes (ver PrepareToInstall)
UsePreviousAppDir=no
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; instala só para o usuário atual: não pede senha de administrador
PrivilegesRequired=lowest
OutputDir=..\saida
OutputBaseFilename=MetaOverlay-Setup
SetupIconFile=..\overlay\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
; o programa aberto (inclusive como administrador) é fechado pelo sinal "fechar" em PrepareToInstall /
; InitializeUninstall; o AppMutex não é usado porque ele só mostrava "feche o programa" e travava a instalação
CloseApplications=force
RestartApplications=no
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"
Name: "startup"; Description: "Abrir junto com o Windows"; GroupDescription: "Opções:"; Flags: unchecked
Name: "npcap"; Description: "Instalar o Npcap (necessário para o medidor de DPS)"; GroupDescription: "Medidor de DPS:"; Check: not NpcapInstalled

[Files]
Source: "..\dist\MetaOverlay\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; atualização: apaga TODOS os arquivos do programa da versão anterior antes de copiar os novos
; (as configurações ficam em %APPDATA%\Aion2Overlay e não são apagadas)
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\*.exe"
Type: files; Name: "{app}\*.dll"
Type: files; Name: "{app}\{#OldExe}"
Type: files; Name: "{group}\{#OldName2}.lnk"
Type: files; Name: "{group}\Desinstalar {#OldName2}.lnk"
Type: files; Name: "{userdesktop}\{#OldName2}.lnk"
Type: files; Name: "{userstartup}\{#OldName2}.lnk"
Type: files; Name: "{group}\{#OldName}.lnk"
Type: files; Name: "{group}\Desinstalar {#OldName}.lnk"
Type: files; Name: "{userdesktop}\{#OldName}.lnk"
Type: files; Name: "{userstartup}\{#OldName}.lnk"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--replace"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  NpcapPage: TOutputMsgWizardPage;
  NpcapReady: Boolean;

{ sinal "fechar" do programa: funciona mesmo se ele estiver aberto como administrador
  (o taskkill do instalador, que roda sem administrador, não consegue fechar nesse caso) }
function OpenEventW(dwDesiredAccess: Cardinal; bInheritHandle: Integer; lpName: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(hEvent: THandle): Integer;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Integer;
  external 'CloseHandle@kernel32.dll stdcall';

procedure AskAppToQuit;
var
  H: THandle;
  I: Integer;
begin
  H := OpenEventW($0002, 0, 'Local\MetaOverlayQuit');
  if H <> 0 then
  begin
    SetEvent(H);
    CloseHandle(H);
    { espera o programa fechar sozinho (até ~6 s) }
    for I := 1 to 30 do
    begin
      Sleep(200);
      if not CheckForMutexes('Aion2OverlayMutex') then
        Break;
    end;
  end;
end;

const
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C1E7A52-3F0B-4F57-9C2B-A2A10E2C0001}_is1';

{ Desinstala a versão que já estava no PC (qualquer nome/pasta antiga) antes de instalar a nova,
  para não sobrar arquivo velho misturado. As configurações do usuário não são tocadas. }
procedure RemoveOldVersion;
var
  Cmd, OldDir: String;
  R: Integer;
begin
  OldDir := '';
  if not RegQueryStringValue(HKCU, UninstKey, 'InstallLocation', OldDir) then
    RegQueryStringValue(HKLM, UninstKey, 'InstallLocation', OldDir);
  if RegQueryStringValue(HKCU, UninstKey, 'UninstallString', Cmd) or
     RegQueryStringValue(HKLM, UninstKey, 'UninstallString', Cmd) then
  begin
    Cmd := RemoveQuotes(Cmd);
    if FileExists(Cmd) then
    begin
      Exec(Cmd, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, R);
      Sleep(1500);   { o desinstalador termina num processo separado }
    end;
  end;
  { sobras que o desinstalador não conhece: só os arquivos do programa, nunca outras coisas da pasta }
  OldDir := RemoveBackslashUnlessRoot(OldDir);
  if (OldDir <> '') and DirExists(OldDir) then
  begin
    DelTree(OldDir + '\_internal', True, True, True);
    DeleteFile(OldDir + '\{#OldExe}');
    DeleteFile(OldDir + '\{#OldExe2}');
    DeleteFile(OldDir + '\{#AppExe}');
    RemoveDir(OldDir);   { só some se ficou vazia }
  end;
end;

function InitializeUninstall(): Boolean;
begin
  AskAppToQuit;
  Result := True;
end;

function NpcapInstalled: Boolean;
begin
  Result := DirExists(ExpandConstant('{sys}\Npcap')) or FileExists(ExpandConstant('{sys}\wpcap.dll'));
end;

procedure InitializeWizard;
begin
  NpcapPage := CreateOutputMsgPage(wpSelectDir,
    'Sobre o Npcap', 'Componente usado pelo medidor de DPS',
    'O medidor de DPS precisa de um componente chamado Npcap para funcionar.' + #13#10 + #13#10 +
    'O que ele faz: o Npcap é um driver de rede para Windows que deixa um programa ler uma CÓPIA ' +
    'dos dados que chegam e saem pela sua internet (o mesmo usado pelo Wireshark, um programa ' +
    'conhecido de análise de rede). O medidor de DPS usa isso para ler só o tráfego do Aion 2 e ' +
    'calcular o dano. Ele não altera, não bloqueia e não envia nada para lugar nenhum, e não mexe ' +
    'nos arquivos do jogo.' + #13#10 + #13#10 +
    'Se você marcar a opção na próxima tela, o instalador baixa o Npcap do site oficial e abre o ' +
    'instalador dele no final (o Windows vai pedir permissão de administrador).' + #13#10 + #13#10 +
    'Não vai usar o DPS? Pode desmarcar: todo o resto do overlay funciona sem o Npcap, e dá para ' +
    'instalar depois pela aba DPS do programa.');
  DownloadPage := CreateDownloadPage('Baixando o Npcap', 'Aguarde o download do instalador oficial...', nil);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  R: Integer;
begin
  { fecha o overlay se ainda estiver aberto (inclusive na bandeja) }
  AskAppToQuit;
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExe} /F', '', SW_HIDE, ewWaitUntilTerminated, R);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#OldExe} /F', '', SW_HIDE, ewWaitUntilTerminated, R);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#OldExe2} /F', '', SW_HIDE, ewWaitUntilTerminated, R);
  Sleep(800);
  RemoveOldVersion;
  Result := '';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = NpcapPage.ID) and NpcapInstalled;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpReady) and WizardIsTaskSelected('npcap') then
  begin
    DownloadPage.Clear;
    DownloadPage.Add('{#NpcapUrl}', 'npcap-setup.exe', '{#NpcapSha256}');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        NpcapReady := True;
      except
        NpcapReady := False;
        MsgBox('Não consegui baixar o Npcap agora (sem internet ou o site mudou o endereço).' + #13#10 +
               'O Meta Overlay será instalado normalmente. Depois é só usar o botão "Instalar Npcap" na aba DPS.',
               mbInformation, MB_OK);
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  R: Integer;
begin
  if (CurStep = ssPostInstall) and NpcapReady then
  begin
    MsgBox('Agora vai abrir o instalador oficial do Npcap.' + #13#10 + #13#10 +
           'Deixe marcada a opção "Install Npcap in WinPcap API-compatible Mode" e vá clicando em I Agree / Install / Next.' + #13#10 +
           'O Windows vai pedir permissão de administrador: clique em Sim.', mbInformation, MB_OK);
    if not ShellExec('', ExpandConstant('{tmp}\npcap-setup.exe'), '', '', SW_SHOW, ewWaitUntilTerminated, R) then
      MsgBox('Não foi possível abrir o instalador do Npcap. Você pode instalar depois pela aba DPS do programa.',
             mbInformation, MB_OK);
  end;
end;
