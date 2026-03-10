param(
    [int]$Port = 3001,
    [string]$Subdomain = "",
    [switch]$UseLocalTunnel,
    [switch]$KeepAlive,
    [switch]$NoTunnel,
    [switch]$StopOnly,
    [switch]$StatusOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$cloudflareScript = Join-Path $projectRoot "acesso_seguro_cloudflare.ps1"
if (-not $UseLocalTunnel -and (Test-Path $cloudflareScript)) {
    Write-Host "Modo padrao: Cloudflare Quick Tunnel (mais estavel para web)."
    & $cloudflareScript -Port $Port -QuickTunnel -KeepAlive:$KeepAlive -NoTunnel:$NoTunnel -StopOnly:$StopOnly -StatusOnly:$StatusOnly
    $exitCode = if (Test-Path variable:LASTEXITCODE) { [int]$LASTEXITCODE } else { 0 }
    exit $exitCode
}

$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python da .venv nao encontrado em $pythonExe"
}

$ltOut = Join-Path $projectRoot "lt_stdout.log"
$ltErr = Join-Path $projectRoot "lt_stderr.log"

function Get-RunAppProcesses {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*run_app.py*" }
}

function Get-LocalTunnelProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -like "*localtunnel*" -or
            $_.CommandLine -like "*loca.lt*" -or
            $_.CommandLine -like "*lt --port*"
        }
}

function Stop-TrackedProcesses {
    $run = Get-RunAppProcesses
    foreach ($p in $run) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $lt = Get-LocalTunnelProcesses
    foreach ($p in $lt) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    # Evita publicar versao antiga: encerra qualquer processo escutando na porta alvo.
    $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port -and $_.LocalAddress -in @('127.0.0.1', '0.0.0.0') }
    $listenerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($procId in $listenerPids) {
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
    }
}

function Show-Status {
    $run = @(Get-RunAppProcesses)
    $lt = @(Get-LocalTunnelProcesses)
    $listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port }

    Write-Host "RUN_APP: $($run.Count) processo(s)"
    if ($listen) {
        $addrs = ($listen | Select-Object -ExpandProperty LocalAddress -Unique) -join ", "
        Write-Host "PORTA LOCAL: $Port ativa em $addrs"
    } else {
        Write-Host "PORTA LOCAL: $Port inativa"
    }

    Write-Host "LOCALTUNNEL: $($lt.Count) processo(s)"
    if (Test-Path $ltOut) {
        $urlLine = Select-String -Path $ltOut -Pattern "your url is|https://" -CaseSensitive:$false | Select-Object -Last 1
        if ($urlLine) {
            Write-Host "URL registrada: $($urlLine.Line)"
        }
    }
}

if ($StopOnly) {
    Stop-TrackedProcesses
    Start-Sleep -Milliseconds 400
    Write-Host "Processos de app/tunel encerrados."
    exit 0
}

if ($StatusOnly) {
    Show-Status
    exit 0
}

Stop-TrackedProcesses
Start-Sleep -Milliseconds 600

Write-Host "Subindo app local em 127.0.0.1:$Port..."
$oldExternal = $env:ENG_CLINICA_EXTERNAL
$oldPort = $env:ENG_CLINICA_PORT
$env:ENG_CLINICA_EXTERNAL = "1"
$env:ENG_CLINICA_PORT = "$Port"
try {
    $null = Start-Process -FilePath $pythonExe -ArgumentList "run_app.py" -WorkingDirectory $projectRoot -PassThru
}
finally {
    if ($null -eq $oldExternal) { Remove-Item Env:\ENG_CLINICA_EXTERNAL -ErrorAction SilentlyContinue } else { $env:ENG_CLINICA_EXTERNAL = $oldExternal }
    if ($null -eq $oldPort) { Remove-Item Env:\ENG_CLINICA_PORT -ErrorAction SilentlyContinue } else { $env:ENG_CLINICA_PORT = $oldPort }
}

$maxWait = 25
$started = $false
for ($i = 0; $i -lt $maxWait; $i++) {
    $listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port }
    if ($listen) {
        $started = $true
        break
    }
    Start-Sleep -Seconds 1
}

if (-not $started) {
    throw "App nao iniciou na porta $Port em ate $maxWait segundos."
}

Write-Host "App local ativo na porta: $Port"

if ($NoTunnel) {
    exit 0
}

if (Test-Path $ltOut) { Remove-Item $ltOut -Force -ErrorAction SilentlyContinue }
if (Test-Path $ltErr) { Remove-Item $ltErr -Force -ErrorAction SilentlyContinue }

Write-Host "Subindo tunel externo (localtunnel)..."
$subdomainTrimmed = $Subdomain.Trim()
if ($subdomainTrimmed -eq "") {
    $subdomainTrimmed = "engclinica" + (Get-Date -Format "HHmmss")
}

$ltArgs = @{
    FilePath = "cmd.exe"
    ArgumentList = "/c npx --yes localtunnel --port $Port --subdomain $subdomainTrimmed"
    WorkingDirectory = $projectRoot
    RedirectStandardOutput = $ltOut
    RedirectStandardError = $ltErr
    PassThru = $true
}
$ltProc = Start-Process @ltArgs

Start-Sleep -Seconds 3

$url = "https://$subdomainTrimmed.loca.lt"

try {
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
    Write-Host "Link externo: $url (status $($resp.StatusCode))"
} catch {
    Write-Host "Link externo criado, mas validacao HTTP falhou neste momento: $url"
    Write-Host "Detalhe: $($_.Exception.Message)"
}

try {
    $tunnelPassword = (Invoke-WebRequest -Uri "https://loca.lt/mytunnelpassword" -UseBasicParsing -TimeoutSec 20).Content.Trim()
    if ($tunnelPassword) {
        Write-Host "Senha do tunnel (loca.lt): $tunnelPassword"
    }
}
catch {
    Write-Host "Nao foi possivel obter senha do tunnel automaticamente."
}

Write-Host "PID app(s): $((Get-RunAppProcesses | Select-Object -ExpandProperty ProcessId) -join ', ')"
Write-Host "PID tunnel: $($ltProc.Id)"
Write-Host "Subdomain usado: $subdomainTrimmed"
Write-Host "Logs do tunel: $ltOut | $ltErr"
