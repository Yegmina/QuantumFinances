param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$Seeds = "41,42,43,44,45",
    [string]$Shots = "64,128",
    [int]$Iterations = 60,
    [string]$OutDir = "quantum_hardware/experiments",
    [switch]$SkipHardware
)

$ErrorActionPreference = "Stop"

function ConvertFrom-SecureStringToPlainText {
    param([Security.SecureString]$Secure)
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secure)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

Set-Location $RepoRoot
New-Item -ItemType Directory -Force -Path "quantum_hardware\experiments" | Out-Null

if (-not $SkipHardware) {
    if (-not $env:IQM_TOKEN) {
        $secureToken = Read-Host "Paste IQM Resonance token" -AsSecureString
        $env:IQM_TOKEN = ConvertFrom-SecureStringToPlainText -Secure $secureToken
    }
    $env:WSLENV = "IQM_TOKEN/u"
    $submitFlags = "--submit --wait --stop-on-error"
}
else {
    $submitFlags = ""
}

try {
    $repoRootForWslPath = $RepoRoot -replace "\\", "/"
    $wslRepoRoot = (wsl wslpath -a $repoRootForWslPath).Trim()
    $batchCommand = @(
        "cd '$wslRepoRoot'",
        "&&",
        "`$HOME/qf-miniconda/bin/python",
        "quantum_hardware/scripts/iqm_batch_qml_experiments.py",
        "--input quantum_hardware/inputs/latest_run.json",
        "--seeds $Seeds",
        "--shots $Shots",
        "--iterations $Iterations",
        "--out-dir $OutDir",
        $submitFlags
    ) -join " "

    Write-Host "Running temporal QML batch..."
    wsl bash -lc $batchCommand

    Write-Host "Regenerating paper figures and tables..."
    py -3.13 paper\generate_artifacts.py

    Push-Location paper
    try {
        Write-Host "Rendering paper PDF..."
        pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build main.tex
        pdflatex -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build main.tex
    }
    finally {
        Pop-Location
    }

    Write-Host "Done."
    Write-Host "PDF: $RepoRoot\paper\build\main.pdf"
    Write-Host "Batch CSV: $RepoRoot\quantum_hardware\experiments\iqm_qml_batch_summary.csv"
}
finally {
    if (-not $SkipHardware) {
        Remove-Item Env:\IQM_TOKEN -ErrorAction SilentlyContinue
    }
}
