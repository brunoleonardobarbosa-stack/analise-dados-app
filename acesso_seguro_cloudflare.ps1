param(
    [int]$Port = 3001,
    [string]$TunnelName = "engclinica",
    [string]$Hostname = "",
    [switch]$QuickTunnel,
    [switch]$AllowFixedHostname,
    [switch]$KeepAlive,
    [int]$HealthCheckSeconds = 20,
    [switch]$NoTunnel,
    [switch]$StopOnly,
    [switch]$StatusOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python da .venv nao encontrado em $pythonExe"
}

$cfOut = Join-Path $projectRoot "cf_stdout.log"
$cfErr = Join-Path $projectRoot "cf_stderr.log"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Comando '$Name' nao encontrado no PATH."
    }
}

function Resolve-CloudflaredPath {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $fallback = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\Cloudflare.cloudflared_Microsoft.Winget.Source_8wekyb3d8bbwe\cloudflared.exe"
    if (Test-Path $fallback) {
        return $fallback
    }

    throw "cloudflared nao encontrado. Instale com: winget install --id Cloudflare.cloudflared -e"
}

function Get-RunAppProcesses {
    Get-CimInstance Win32_Process |
        Where-Object { $_.Name -like "python*" -and $_.CommandLine -like "*run_app.py*" }
}

function Get-CloudflaredProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -like "cloudflared*" -and (
                $_.CommandLine -like "*tunnel run*" -or
                $_.CommandLine -like "*--url http://127.0.0.1:$Port*"
            )
        }
}

function Stop-TrackedProcesses {
    $run = Get-RunAppProcesses
    foreach ($p in $run) {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    $cf = Get-CloudflaredProcesses
    foreach ($p in $cf) {
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
    $cf = @(Get-CloudflaredProcesses)
    $listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -eq $Port }

    Write-Host "RUN_APP: $($run.Count) processo(s)"
    if ($listen) {
        $addrs = ($listen | Select-Object -ExpandProperty LocalAddress -Unique) -join ", "
        Write-Host "PORTA LOCAL: $Port ativa em $addrs"
    } else {
        Write-Host "PORTA LOCAL: $Port inativa"
    }

    Write-Host "CLOUDFLARED: $($cf.Count) processo(s)"
    if (Test-Path $cfOut) {
        $urlLine = Select-String -Path $cfOut -Pattern "https://|trycloudflare.com" -CaseSensitive:$false | Select-Object -Last 1
        if ($urlLine) {
            Write-Host "URL registrada em log: $($urlLine.Line)"
        }
    }

    if ($Hostname -ne "") {
        Write-Host "Hostname configurado: https://$Hostname"
    }
}

function Start-QuickTunnel {
    param(
        [string]$CloudflaredExe,
        [string]$ProjectRoot,
        [string]$OutLog,
        [string]$ErrLog,
        [int]$LocalPort
    )

    if (Test-Path $OutLog) { Remove-Item $OutLog -Force -ErrorAction SilentlyContinue }
    if (Test-Path $ErrLog) { Remove-Item $ErrLog -Force -ErrorAction SilentlyContinue }

    $cfArgs = @("tunnel", "--url", "http://127.0.0.1:$LocalPort")
    $proc = Start-Process -FilePath $CloudflaredExe -ArgumentList $cfArgs -WorkingDirectory $ProjectRoot -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -PassThru

    $urlMatch = $null
    for ($i = 0; $i -lt 25; $i++) {
        Start-Sleep -Seconds 1
        $combinedText = ""
        if (Test-Path $OutLog) { $combinedText += (Get-Content $OutLog -Raw -ErrorAction SilentlyContinue) + "`n" }
        if (Test-Path $ErrLog) { $combinedText += (Get-Content $ErrLog -Raw -ErrorAction SilentlyContinue) + "`n" }

        $urlMatch = [regex]::Match($combinedText, "https://[a-z0-9-]+\.trycloudflare\.com", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($urlMatch.Success) {
            break
        }
    }

    $publicUrl = if ($urlMatch -and $urlMatch.Success) { $urlMatch.Value } else { "" }

    if ($publicUrl) {
        $latestUrlFile = Join-Path $ProjectRoot "ultima_url_web.txt"
        Set-Content -Path $latestUrlFile -Value $publicUrl -Encoding UTF8

        $desktopUrlFile = Join-Path $env:USERPROFILE "Desktop\ULTIMA_URL_EngenhariaClinica_Web.txt"
        Set-Content -Path $desktopUrlFile -Value $publicUrl -Encoding UTF8

        try {
            Start-Process $publicUrl | Out-Null
        }
        catch {
            # Nao interrompe inicializacao caso nao consiga abrir navegador automaticamente.
        }
    }

    return [pscustomobject]@{
        Proc = $proc
        Url = $publicUrl
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
    Write-Host "Executado com -NoTunnel. Apenas app local iniciado."
    exit 0
}

$cloudflaredExe = Resolve-CloudflaredPath

if (Test-Path $cfOut) { Remove-Item $cfOut -Force -ErrorAction SilentlyContinue }
if (Test-Path $cfErr) { Remove-Item $cfErr -Force -ErrorAction SilentlyContinue }

$cloudflaredConfig = Join-Path $env:USERPROFILE ".cloudflared\config.yml"
# Regra padrao de seguranca operacional: URL deve rotacionar a cada execucao.
# So permite hostname fixo quando explicitamente solicitado com -AllowFixedHostname.
$useQuickTunnel = $true
if ($AllowFixedHostname -and (Test-Path $cloudflaredConfig)) {
    $useQuickTunnel = $false
}

if (($Hostname -ne "") -and -not $AllowFixedHostname) {
    Write-Host "Hostname fixo ignorado para manter URL rotativa. Use -AllowFixedHostname para habilitar URL fixa."
}

Write-Host "Subindo tunel seguro (cloudflared)..."
if ($useQuickTunnel) {
    $quick = Start-QuickTunnel -CloudflaredExe $cloudflaredExe -ProjectRoot $projectRoot -OutLog $cfOut -ErrLog $cfErr -LocalPort $Port
    $cfProc = $quick.Proc
    $publicUrl = [string]$quick.Url

    if ($publicUrl) {
        Write-Host "URL publica (Quick Tunnel): $publicUrl"

        try {
            $resp = Invoke-WebRequest -Uri $publicUrl -UseBasicParsing -TimeoutSec 20
            Write-Host "Validacao HTTP: status $($resp.StatusCode)"
        }
        catch {
            Write-Host "Quick Tunnel iniciou, mas validacao HTTP ainda falhou para $publicUrl"
            Write-Host "Detalhe: $($_.Exception.Message)"
        }
    }
    else {
        Write-Host "Quick Tunnel iniciado, mas URL ainda nao apareceu no log."
    }

    if ($KeepAlive) {
        if ($HealthCheckSeconds -lt 5) { $HealthCheckSeconds = 5 }
        Write-Host "KeepAlive ativo: monitorando a cada $HealthCheckSeconds s. (Ctrl+C para encerrar)"
        $consecutiveFails = 0

        while ($true) {
            Start-Sleep -Seconds $HealthCheckSeconds

            $procAlive = $false
            if ($cfProc) {
                $procAlive = $null -ne (Get-Process -Id $cfProc.Id -ErrorAction SilentlyContinue)
            }

            $urlOk = $false
            if ($publicUrl) {
                try {
                    $status = (Invoke-WebRequest -Uri $publicUrl -UseBasicParsing -TimeoutSec 12).StatusCode
                    if ($status -ge 200 -and $status -lt 500) {
                        $urlOk = $true
                    }
                }
                catch {
                    $urlOk = $false
                }
            }

            if ($procAlive -and $urlOk) {
                $consecutiveFails = 0
                continue
            }

            $consecutiveFails += 1
            Write-Host "KeepAlive: falha detectada ($consecutiveFails/3)." 

            if ($consecutiveFails -lt 3) {
                continue
            }

            Write-Host "KeepAlive: reiniciando Quick Tunnel..."
            if ($cfProc) {
                Stop-Process -Id $cfProc.Id -Force -ErrorAction SilentlyContinue
            }

            $quick = Start-QuickTunnel -CloudflaredExe $cloudflaredExe -ProjectRoot $projectRoot -OutLog $cfOut -ErrLog $cfErr -LocalPort $Port
            $cfProc = $quick.Proc
            $publicUrl = [string]$quick.Url
            if ($publicUrl) {
                Write-Host "Nova URL publica (Quick Tunnel): $publicUrl"
            }
            $consecutiveFails = 0
        }
    }
}
else {
    $cfArgs = @("tunnel", "run", $TunnelName)
    $cfProc = Start-Process -FilePath $cloudflaredExe -ArgumentList $cfArgs -WorkingDirectory $projectRoot -RedirectStandardOutput $cfOut -RedirectStandardError $cfErr -PassThru

    Start-Sleep -Seconds 3

    if ($Hostname -ne "") {
        Write-Host "URL esperada: https://$Hostname"
        try {
            $resp = Invoke-WebRequest -Uri ("https://" + $Hostname) -UseBasicParsing -TimeoutSec 20
            Write-Host "Validacao HTTP: status $($resp.StatusCode)"
        }
        catch {
            Write-Host "Tunel iniciado, mas validacao HTTP ainda falhou para https://$Hostname"
            Write-Host "Detalhe: $($_.Exception.Message)"
        }
    }
    else {
        Write-Host "TunnelName: $TunnelName"
        Write-Host "Defina -Hostname para validar URL automaticamente."
    }
}

Write-Host "PID app(s): $((Get-RunAppProcesses | Select-Object -ExpandProperty ProcessId) -join ', ')"
Write-Host "PID cloudflared: $($cfProc.Id)"
Write-Host "Logs do tunel: $cfOut | $cfErr"
