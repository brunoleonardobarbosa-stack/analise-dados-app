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

# --- Localiza o worktree dev ---
$testRoot = Join-Path (Split-Path $projectRoot) "analise-dados-app-teste"
if (Test-Path "$testRoot\.git") {
    Push-Location $testRoot
} else {
    # fallback: usar diretorio atual se estiver na dev
    $branch = git rev-parse --abbrev-ref HEAD 2>$null
    if ($branch -ne "dev") {
        Write-Host "ERRO: Nao encontrei o worktree de teste em $testRoot" -ForegroundColor Red
        exit 1
    }
}

# --- Verifica se ha alteracoes nao commitadas na dev ---
$dirty = git status --porcelain 2>$null
if ($dirty) {
    Write-Host "ERRO: Existem alteracoes nao commitadas na branch dev." -ForegroundColor Red
    Write-Host "Faca commit das alteracoes antes de promover:" -ForegroundColor Yellow
    Write-Host "  cd $testRoot" -ForegroundColor Gray
    Write-Host "  git add -A" -ForegroundColor Gray
    Write-Host "  git commit -m 'descricao da melhoria'" -ForegroundColor Gray
    Pop-Location -ErrorAction SilentlyContinue
    exit 1
}
Pop-Location -ErrorAction SilentlyContinue

# --- Confirma com o usuario ---
Write-Host "Isso vai aplicar TODAS as melhorias da branch dev na branch main." -ForegroundColor Yellow
Write-Host "O ambiente de TRABALHO sera atualizado." -ForegroundColor Yellow
Write-Host ""
$confirm = Read-Host "Deseja continuar? (s/n)"
if ($confirm -notin @("s", "S", "sim", "Sim")) {
    Write-Host "Operacao cancelada." -ForegroundColor Gray
    exit 0
}

# --- Faz merge da dev na main (diretorio principal já está em main) ---
Write-Host ""
Write-Host "Fazendo merge da dev na main..." -ForegroundColor Cyan
Set-Location $projectRoot
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

Write-Host ""
Write-Host "O worktree de teste continua em: $testRoot" -ForegroundColor Gray
Write-Host "Proximo passo: rode .\start_trabalho.ps1 para subir o ambiente atualizado." -ForegroundColor Cyan
