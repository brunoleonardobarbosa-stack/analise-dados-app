<#
.SYNOPSIS
    Sobe o ambiente de TESTE (branch dev) na porta 3002.
    Usa git worktree em diretorio separado para rodar junto com o ambiente de trabalho.
#>
param(
    [int]$Port = 3002
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$testRoot   = Join-Path (Split-Path $projectRoot) "analise-dados-app-teste"

# --- Garante que o worktree existe ---
if (-not (Test-Path "$testRoot\app.py")) {
    Write-Host "Criando worktree para branch dev..." -ForegroundColor Cyan
    Push-Location $projectRoot
    git worktree add $testRoot dev 2>$null
    Pop-Location
}

# --- Garante junction do .venv ---
if (-not (Test-Path "$testRoot\.venv\Scripts\Activate.ps1")) {
    cmd /c mklink /J "$testRoot\.venv" "$projectRoot\.venv" 2>$null
}

Set-Location $testRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host "   AMBIENTE DE TESTE  (branch dev)"      -ForegroundColor Yellow
Write-Host "   Porta: $Port"                          -ForegroundColor Yellow
Write-Host "   Dir:   $testRoot"                      -ForegroundColor Yellow
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
& "$testRoot\.venv\Scripts\streamlit.exe" run app.py `
    --server.port $Port `
    --browser.serverAddress localhost `
    --theme.primaryColor "#FF9800"
