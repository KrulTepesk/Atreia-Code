; Inno Setup: transforma dist\AtreiaCode no instalador AtreiaCode-Setup.exe
#define AppName "Atreia Code"
#define AppVersion "1.0.0"
#define AppExe "AtreiaCode.exe"
; nome antigo do programa (para atualizar quem já tinha instalado)
#define OldExe "Aion2Overlay.exe"
#define OldName "Aion 2 Overlay"
; instalador oficial do Npcap (baixado na hora da instalação; a licença gratuita não permite embutir)
#define NpcapUrl "https://npcap.com/dist/npcap-1.89.exe"

[Setup]
AppId={{6C1E7A52-3F0B-4F57-9C2B-A2A10E2C0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Atreia Code
DefaultDirName={localappdata}\Programs\AtreiaCode
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; instala só para o usuário atual: não pede senha de administrador
PrivilegesRequired=lowest
OutputDir=..\saida
OutputBaseFilename=AtreiaCode-Setup
SetupIconFile=..\overlay\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
; o programa cria esse "mutex" enquanto está aberto: o instalador avisa e pede para fechar
AppMutex=Aion2OverlayMutex
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
Source: "..\dist\AtreiaCode\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; limpa a versão com o nome antigo (o AppId é o mesmo, então é uma atualização)
Type: files; Name: "{app}\{#OldExe}"
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
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  NpcapPage: TOutputMsgWizardPage;
  NpcapReady: Boolean;

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
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#AppExe} /F', '', SW_HIDE, ewWaitUntilTerminated, R);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM {#OldExe} /F', '', SW_HIDE, ewWaitUntilTerminated, R);
  Sleep(800);
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
    DownloadPage.Add('{#NpcapUrl}', 'npcap-setup.exe', '');
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
        NpcapReady := True;
      except
        NpcapReady := False;
        MsgBox('Não consegui baixar o Npcap agora (sem internet ou o site mudou o endereço).' + #13#10 +
               'O Atreia Code será instalado normalmente. Depois é só usar o botão "Instalar Npcap" na aba DPS.',
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
