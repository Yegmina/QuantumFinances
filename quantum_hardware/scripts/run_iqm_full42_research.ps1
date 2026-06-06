param(
    [string]$InputPath = "quantum_hardware\inputs\latest_run.json",
    [string]$EmbeddingPath = "quantum_hardware\inputs\latest_run.embeddings.json",
    [string]$Seeds = "41,42,43",
    [string]$Shots = "1024,2048",
    [string]$LatentDims = "8,10,12",
    [int]$Iterations = 160,
    [int]$Layers = 2,
    [switch]$NoWait,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

function Assert-RunInput {
    param([string]$Path)
    $payload = Get-Content $Path -Raw | ConvertFrom-Json
    if ([int]$payload.sourceConnection.snapshotCount -lt 40) {
        throw "Expected the full ORACLE snapshot archive, got $($payload.sourceConnection.snapshotCount) snapshots."
    }
    if ([int]$payload.weeklyPestelSeries.Count -lt 40) {
        throw "Expected at least 40 weekly PESTEL states, got $($payload.weeklyPestelSeries.Count)."
    }
    Write-Host "Run payload OK: $($payload.sourceConnection.snapshotCount) snapshots, $($payload.weeklyPestelSeries.Count) weeks, run $($payload.runId)"
}

function Assert-EmbeddingInput {
    param([string]$Path)
    $payload = Get-Content $Path -Raw | ConvertFrom-Json
    if ([int]$payload.embeddingDimension -ne 1024) {
        throw "Expected 1024-dimensional semantic embeddings, got $($payload.embeddingDimension)."
    }
    if ([int]$payload.weeks.Count -lt 40) {
        throw "Expected at least 40 weekly semantic embeddings, got $($payload.weeks.Count)."
    }
    Write-Host "Embedding payload OK: $($payload.embeddingModel), $($payload.embeddingDimension) dimensions, $($payload.weeks.Count) weeks"
}

Assert-RunInput $InputPath
Assert-EmbeddingInput $EmbeddingPath

if (-not $DryRun -and -not $env:IQM_TOKEN) {
    $secureToken = Read-Host "Paste IQM Resonance token" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    try {
        $env:IQM_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

$env:WSLENV = "IQM_TOKEN/u"

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = "quantum_hardware\experiments\full42_research_$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$outLog = Join-Path $runDir "iqm_full42_research.out.log"
$errLog = Join-Path $runDir "iqm_full42_research.err.log"

$flags = ""
if ($DryRun) {
    $flags = ""
}
else {
    $flags = "--submit"
    if (-not $NoWait) {
        $flags = "$flags --wait"
    }
    $flags = "$flags --stop-on-error"
}

$wslCommand = @"
cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_batch_semantic_qml_experiments.py --input quantum_hardware/inputs/latest_run.json --embeddings quantum_hardware/inputs/latest_run.embeddings.json --out-dir '$($runDir -replace '\\','/')' --seeds '$Seeds' --shots '$Shots' --latent-dims '$LatentDims' --iterations $Iterations --layers $Layers $flags
"@

Write-Host "Starting IQM full-42 research batch"
Write-Host "Seeds: $Seeds"
Write-Host "Shots: $Shots"
Write-Host "Latent dims: $LatentDims"
Write-Host "Iterations: $Iterations"
Write-Host "Layers: $Layers"
Write-Host "Stdout: $outLog"
Write-Host "Stderr: $errLog"

wsl bash -lc $wslCommand 1> $outLog 2> $errLog

if ($LASTEXITCODE -ne 0) {
    Write-Host "IQM batch failed. Last stderr lines:"
    Get-Content $errLog -Tail 40
    throw "IQM full-42 research batch failed with exit code $LASTEXITCODE"
}

Write-Host "IQM full-42 research batch finished."
Write-Host "Run directory: $runDir"
Write-Host "Summary JSON: $(Join-Path $runDir 'iqm_semantic_qml_batch_summary.json')"
Write-Host "Summary CSV: $(Join-Path $runDir 'iqm_semantic_qml_batch_summary.csv')"
Write-Host "Stdout: $outLog"
Write-Host "Stderr: $errLog"
