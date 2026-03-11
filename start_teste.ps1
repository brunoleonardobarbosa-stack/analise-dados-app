<#
.SYNOPSIS
    Sobe o ambiente de TESTE (branch dev) na porta 3002.
    Todas as melhorias sao feitas aqui antes de ir para producao.
#>
param(
    [int]$Port = 3002
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# --- Garante estar na branch dev ---
$branch = git rev-parse --abbrev-ref HEAD 2>$null
if ($branch -ne "dev") {
    Write-Host "Alternando para branch dev..." -ForegroundColor Cyan
    git stash --include-untracked 2>$null
    git checkout dev
    git stash pop 2>$null
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "   AMBIENTE DE TESTE  (branch dev)"      -ForegroundColor Yellow
Write-Host "   Porta: $Port"                          -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

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

# --- Sobe o app de teste ---
Write-Host "Iniciando Engenharia Clinica (TESTE) na porta $Port..." -ForegroundColor Green
& "$projectRoot\.venv\Scripts\streamlit.exe" run app.py `
    --server.port $Port `
    --browser.serverAddress localhost `
    --theme.primaryColor "#FF9800"
