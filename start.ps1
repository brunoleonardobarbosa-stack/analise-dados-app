param(
    [int]$Port = 3001
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# --- Encerra qualquer processo usando a porta ---
$listeners = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($listeners) {
    Write-Host "Encerrando processo anterior na porta $Port..." -ForegroundColor Yellow
    $listeners | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

# --- Valida que a porta ficou livre ---
$still = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($still) {
    Write-Host "ERRO: porta $Port ainda ocupada. Tente encerrar manualmente." -ForegroundColor Red
    exit 1
}

# --- Sobe o app ---
Write-Host "Iniciando Engenharia Clinica na porta $Port..." -ForegroundColor Green
& "$projectRoot\.venv\Scripts\streamlit.exe" run app.py --server.port $Port
