param(
    [string]$InputPath = "quantum_hardware\inputs\latest_run.json",
    [string]$EmbeddingPath = "quantum_hardware\inputs\latest_run.embeddings.json",
    [string]$Model = "intfloat/multilingual-e5-large-instruct",
    [string]$Seeds = "41,42,43",
    [string]$Shots = "512,1024",
    [string]$LatentDims = "8,10,12",
    [int]$Iterations = 120,
    [int]$Layers = 2,
    [ValidateSet("windows", "wsl")]
    [string]$EmbeddingRuntime = "windows",
    [switch]$SkipEmbeddingBuild,
    [switch]$SkipHardware
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

function Invoke-CheckedWsl {
    param([string]$Command)
    wsl bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed with exit code $LASTEXITCODE"
    }
}

function Invoke-CheckedNative {
    param([string[]]$Command)
    & $Command[0] @($Command[1..($Command.Length - 1)])
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

if (-not $env:IQM_TOKEN -and -not $SkipHardware) {
    $secureToken = Read-Host "Paste IQM Resonance token" -AsSecureString
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    )
    $env:IQM_TOKEN = $plainToken
}

$env:WSLENV = "IQM_TOKEN/u"

try {
    if (-not $SkipEmbeddingBuild) {
        if ($EmbeddingRuntime -eq "windows") {
            Invoke-CheckedNative @(
                "py",
                "-3.13",
                "quantum_hardware\scripts\build_semantic_embeddings.py",
                "--input",
                $InputPath,
                "--out",
                $EmbeddingPath,
                "--model",
                $Model
            )
        }
        else {
            Invoke-CheckedWsl "cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python -m pip install -q -r quantum_hardware/requirements-embeddings.txt && ~/qf-miniconda/bin/python quantum_hardware/scripts/build_semantic_embeddings.py --input '$($InputPath -replace '\\','/')' --out '$($EmbeddingPath -replace '\\','/')' --model '$Model'"
        }
    }

    $submitFlags = ""
    if (-not $SkipHardware) {
        $submitFlags = "--submit --wait --stop-on-error"
    }

    Invoke-CheckedWsl "cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_batch_semantic_qml_experiments.py --input '$($InputPath -replace '\\','/')' --embeddings '$($EmbeddingPath -replace '\\','/')' --seeds '$Seeds' --shots '$Shots' --latent-dims '$LatentDims' --iterations $Iterations --layers $Layers $submitFlags"
}
finally {
    if ($plainToken) {
        Remove-Item Env:\IQM_TOKEN -ErrorAction SilentlyContinue
    }
}
