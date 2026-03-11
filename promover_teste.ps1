<#
.SYNOPSIS
    Promove as alteracoes validadas do TESTE (dev) para TRABALHO (main).
    Faz merge da branch dev na main de forma segura.
#>

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PROMOVER TESTE -> TRABALHO"           -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Verifica se ha alteracoes nao commitadas na dev ---
$branch = git rev-parse --abbrev-ref HEAD 2>$null
if ($branch -eq "dev") {
    $dirty = git status --porcelain 2>$null
    if ($dirty) {
        Write-Host "ERRO: Existem alteracoes nao commitadas na branch dev." -ForegroundColor Red
        Write-Host "Faca commit das alteracoes antes de promover:" -ForegroundColor Yellow
        Write-Host "  git add -A" -ForegroundColor Gray
        Write-Host "  git commit -m 'descricao da melhoria'" -ForegroundColor Gray
        exit 1
    }
}

# --- Confirma com o usuario ---
Write-Host "Isso vai aplicar TODAS as melhorias da branch dev na branch main." -ForegroundColor Yellow
Write-Host "O ambiente de TRABALHO sera atualizado." -ForegroundColor Yellow
Write-Host ""
$confirm = Read-Host "Deseja continuar? (s/n)"
if ($confirm -notin @("s", "S", "sim", "Sim")) {
    Write-Host "Operacao cancelada." -ForegroundColor Gray
    exit 0
}

# --- Vai para main e faz merge ---
Write-Host ""
Write-Host "Alternando para main..." -ForegroundColor Cyan
git checkout main
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO ao alternar para main." -ForegroundColor Red
    exit 1
}

Write-Host "Fazendo merge da dev na main..." -ForegroundColor Cyan
git merge dev --no-ff -m "Promove melhorias validadas no teste para trabalho"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERRO: Conflito no merge! Resolva manualmente:" -ForegroundColor Red
    Write-Host "  1. Edite os arquivos com conflito" -ForegroundColor Yellow
    Write-Host "  2. git add -A" -ForegroundColor Gray
    Write-Host "  3. git commit" -ForegroundColor Gray
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "   SUCESSO! Melhorias promovidas."       -ForegroundColor Green
Write-Host "   Branch main atualizada."              -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Proximo passo: rode .\start_trabalho.ps1 para subir o ambiente atualizado." -ForegroundColor Cyan

# --- Volta para dev para continuar trabalhando ---
Write-Host ""
Write-Host "Voltando para branch dev..." -ForegroundColor Gray
git checkout dev
