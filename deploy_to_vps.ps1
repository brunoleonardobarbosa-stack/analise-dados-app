param(
    [Parameter(Mandatory = $true)]
    [string]$ServerIp,

    [string]$User = "root",
    [int]$Port = 22,
    [string]$RemoteDir = "/opt/analise-dados-app",
    [string]$KeyPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-NativeProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "$Label falhou com codigo de saida $($proc.ExitCode)."
    }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Comando '$Name' nao encontrado. Instale/OpenSSH no Windows e tente novamente."
    }
}

Assert-Command "ssh"
Assert-Command "scp"
Assert-Command "tar"

$archivePath = Join-Path $projectRoot "deploy_package.tgz"
$remoteArchive = "/tmp/analise-dados-app.tgz"

if (Test-Path $archivePath) {
    Remove-Item $archivePath -Force -ErrorAction SilentlyContinue
}

Write-Host "Gerando pacote de deploy..."
$tarArgs = @(
    "-czf", $archivePath,
    "--exclude", ".venv",
    "--exclude", "__pycache__",
    "--exclude", "build",
    "--exclude", "dist",
    "--exclude", ".git",
    "--exclude", "deploy_package.tgz",
    "."
)
Invoke-NativeProcess -Label "Empacotamento (tar)" -FilePath "tar" -Arguments $tarArgs

if (-not (Test-Path $archivePath)) {
    throw "Falha ao gerar pacote de deploy."
}

$sshArgs = @("-p", "$Port", "-o", "StrictHostKeyChecking=accept-new")
$scpArgs = @("-P", "$Port", "-o", "StrictHostKeyChecking=accept-new")

if ($KeyPath -ne "") {
    if (-not (Test-Path $KeyPath)) {
        throw "Arquivo de chave SSH nao encontrado: $KeyPath"
    }
    $sshArgs += @("-i", $KeyPath)
    $scpArgs += @("-i", $KeyPath)
}

Write-Host "Enviando pacote para $User@$ServerIp..."
$scpAllArgs = @()
$scpAllArgs += $scpArgs
$scpAllArgs += @($archivePath, "$User@${ServerIp}:$remoteArchive")
Invoke-NativeProcess -Label "Transferencia (scp)" -FilePath "scp" -Arguments $scpAllArgs

$remoteCmd = @"
set -e
mkdir -p '$RemoteDir'
rm -rf '$RemoteDir'/*
tar -xzf '$remoteArchive' -C '$RemoteDir' --strip-components=1
cd '$RemoteDir'
bash deploy/vps/install_public_site.sh
"@

Write-Host "Executando instalacao na VPS..."
$sshAllArgs = @()
$sshAllArgs += $sshArgs
$sshAllArgs += @("$User@$ServerIp", $remoteCmd)
Invoke-NativeProcess -Label "Instalacao remota (ssh)" -FilePath "ssh" -Arguments $sshAllArgs

Write-Host "Deploy concluido."
Write-Host "Acesse: http://$ServerIp"
