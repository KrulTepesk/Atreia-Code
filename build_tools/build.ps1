# Gera saida\MetaOverlay-Setup.exe. Baixa sozinho o que faltar (Python e Inno Setup)
# dentro de build_tools, sem mexer no resto do PC e sem pedir administrador.
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"

$Tools = $PSScriptRoot
$Root  = Split-Path $Tools -Parent
Set-Location $Root

function Step($t) { Write-Host ""; Write-Host "==> $t" -ForegroundColor Yellow }

# ---------------------------------------------------------------- Python
Step "Procurando Python"
$py = $null
$local = Join-Path $Tools "_python\python.exe"
$force = [bool]$env:ATREIA_FORCE_PORTABLE_PY      # usado no teste automático do GitHub
if (Test-Path $local) { $py = $local }
if (-not $py -and -not $force) {
    foreach ($v in "3.12", "3.13", "3.11") {
        try {
            $p = & py "-$v" -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $p) { $py = $p.Trim(); break }
        } catch {}
    }
}
if (-not $py -and -not $force) {
    # "python" no PATH (ignora o atalho falso da Microsoft Store, que fica em WindowsApps)
    try {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source -notlike "*WindowsApps*") {
            $ver = & $cmd.Source -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
            if ($LASTEXITCODE -eq 0 -and [int]$ver -ge 311 -and [int]$ver -le 313) { $py = $cmd.Source }
        }
    } catch {}
}
if (-not $py) {
    # Python "portátil": o pacote oficial em .zip (NuGet do python.org). Não usa instalador,
    # então não conflita com Python que já exista no PC e não pede administrador.
    Step "Baixando Python 3.12 (só para montar o programa; fica em build_tools\_python)"
    $zip = Join-Path $env:TEMP "python-3.12.7.zip"
    $tmp = Join-Path $env:TEMP "python-3.12.7-pkg"
    $ok = $false
    foreach ($url in "https://www.nuget.org/api/v2/package/python/3.12.7",
                     "https://globalcdn.nuget.org/packages/python.3.12.7.nupkg") {
        try {
            Invoke-WebRequest $url -OutFile $zip -UseBasicParsing
            if ((Get-Item $zip).Length -gt 5MB) { $ok = $true; break }
        } catch {}
    }
    if (-not $ok) { throw "Não deu para baixar o Python. Confira a internet e tente de novo." }
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    Expand-Archive $zip -DestinationPath $tmp -Force
    $target = Join-Path $Tools "_python"
    if (Test-Path $target) { Remove-Item $target -Recurse -Force }
    Move-Item (Join-Path $tmp "tools") $target
    $py = $local
    if (-not (Test-Path $py)) { throw "A instalação do Python falhou." }
    try { & $py -m ensurepip --upgrade *> $null } catch {}
}
Write-Host "Python: $py"

# ---------------------------------------------------------------- dependências
$venv = Join-Path $Tools "_venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    Step "Criando ambiente isolado"
    & $py -m venv $venv
}
$vpy = "$venv\Scripts\python.exe"
Step "Instalando bibliotecas (alguns minutos na primeira vez)"
& $vpy -m pip install --upgrade pip --quiet
& $vpy -m pip install -r (Join-Path $Root "requirements.txt") pyinstaller --quiet
if ($LASTEXITCODE -ne 0) { throw "pip falhou" }

# ---------------------------------------------------------------- ícones das habilidades
Step "Baixando os ícones das habilidades (só na primeira vez)"
& $vpy -m pip install pillow --quiet
& $vpy (Join-Path $Tools "baixar_icones.py")

# ---------------------------------------------------------------- .exe
Step "Montando o MetaOverlay.exe"
& $vpy -m PyInstaller --noconfirm --clean `
    --distpath (Join-Path $Root "dist") --workpath (Join-Path $Tools "_work") `
    (Join-Path $Tools "MetaOverlay.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }

# ---------------------------------------------------------------- instalador
function Find-Iscc {
    @(
        (Join-Path $Tools "_inno\ISCC.exe"),
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}

function Test-Exe($path) {
    # um .exe de verdade começa com "MZ" e tem mais de 1 MB (página HTML não passa nisso)
    if (-not (Test-Path $path)) { return $false }
    if ((Get-Item $path).Length -lt 1MB) { return $false }
    $b = [System.IO.File]::ReadAllBytes($path)[0..1]
    return ($b[0] -eq 0x4D -and $b[1] -eq 0x5A)
}

Step "Procurando Inno Setup"
$iscc = Find-Iscc
if (-not $iscc -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    Step "Instalando Inno Setup pelo winget"
    & winget install -e --id JRSoftware.InnoSetup --scope user --silent `
        --accept-package-agreements --accept-source-agreements | Out-Host
    $iscc = Find-Iscc
}
if (-not $iscc) {
    Step "Baixando Inno Setup (fica em build_tools\_inno)"
    $is = Join-Path $env:TEMP "innosetup.exe"
    $urls = @(
        "https://files.jrsoftware.org/is/6/innosetup-6.5.4.exe",
        "https://files.jrsoftware.org/is/6/innosetup-6.4.3.exe",
        "https://jrsoftware.org/download.php/is.exe?site=1"
    )
    foreach ($u in $urls) {
        try {
            Remove-Item $is -ErrorAction SilentlyContinue
            Invoke-WebRequest $u -OutFile $is -UserAgent "Mozilla/5.0" -MaximumRedirection 10
            if (Test-Exe $is) { Write-Host "Baixado de $u"; break }
        } catch { Write-Host "Falhou: $u" }
    }
    if (Test-Exe $is) {
        Start-Process $is -Wait -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER", `
            "/DIR=`"$(Join-Path $Tools '_inno')`""
        $iscc = Find-Iscc
    }
}

New-Item -ItemType Directory -Force (Join-Path $Root "saida") | Out-Null
if ($iscc) {
    Step "Gerando o instalador"
    & $iscc (Join-Path $Tools "instalador.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup falhou" }
    $out = Join-Path $Root "saida\MetaOverlay-Setup.exe"
} else {
    # sem Inno Setup: entrega a versão portátil (zip, é só extrair e abrir o .exe)
    Step "Inno Setup indisponível: gerando versão portátil (.zip)"
    $out = Join-Path $Root "saida\MetaOverlay-Portatil.zip"
    Remove-Item $out -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $Root "dist\MetaOverlay") -DestinationPath $out
    Write-Host "Para gerar o instalador, instale o Inno Setup (jrsoftware.org) e rode de novo." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "PRONTO! $out" -ForegroundColor Green
Start-Process explorer.exe "/select,`"$out`""
