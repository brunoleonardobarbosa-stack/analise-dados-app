<#
.SYNOPSIS
    Sobe o ambiente de TRABALHO (producao) na porta 3001 (branch main).
    Somente codigo validado no teste deve chegar aqui.
#>
param(
    [int]$Port = 3001
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

# --- Garante estar na branch main ---
$branch = git rev-parse --abbrev-ref HEAD 2>$null
if ($branch -ne "main") {
    Write-Host "Alternando para branch main..." -ForegroundColor Cyan
    git stash --include-untracked 2>$null
    git checkout main
    git stash pop 2>$null
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   AMBIENTE DE TRABALHO  (branch main)" -ForegroundColor Green
Write-Host "   Porta: $Port"                         -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
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

# --- Sobe o app de trabalho ---
Write-Host "Iniciando Engenharia Clinica (TRABALHO) na porta $Port..." -ForegroundColor Green
& "$projectRoot\.venv\Scripts\streamlit.exe" run app.py `
    --server.port $Port `
    --browser.serverAddress localhost
