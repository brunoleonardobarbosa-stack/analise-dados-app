param(
    [switch]$BuildExe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host "\n=== $Name ===" -ForegroundColor Cyan
    & $Action
    Write-Host "[OK] $Name" -ForegroundColor Green
}

$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonCmd = if (Test-Path $venvPython) { $venvPython } else { "python" }

Write-Host "Projeto: $projectRoot"
Write-Host "Python: $pythonCmd"

Invoke-Step -Name "Health check" -Action {
    & $pythonCmd "health_check.py"
}

Invoke-Step -Name "Compilacao Python" -Action {
    & $pythonCmd -m compileall "app.py" "run_app.py" "health_check.py"
}

Invoke-Step -Name "Dependencias principais" -Action {
    & $pythonCmd -c "import pandas, streamlit, plotly, openpyxl, reportlab; print('Dependencias principais ok')"
}

if ($BuildExe) {
    Invoke-Step -Name "Build do executavel" -Action {
        & $pythonCmd -m PyInstaller --noconfirm "EngenhariaClinica.spec"
    }
}

Write-Host "\nChecklist de pre-entrega concluido com sucesso." -ForegroundColor Green
if ($BuildExe) {
    Write-Host "Executavel atualizado em dist\\EngenhariaClinica.exe" -ForegroundColor Green
}
