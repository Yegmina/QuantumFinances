# Q-FIN Hardware Preparation

This folder prepares a Q-FIN scenario run for real quantum-computer execution.

Default behavior is intentionally dry-run. A real hardware job is submitted only when a provider script is run with `--submit`.

## Provider Targets


| Target             | Status               | Use                                                                                               |
| ------------------ | -------------------- | ------------------------------------------------------------------------------------------------- |
| IBM Quantum        | Ready                | Qiskit Runtime `SamplerV2` hardware submission with a tiny circuit and saved receipt.             |
| IQM Quantum Stack  | Ready                | Qiskit-on-IQM submission when the hackathon IQM endpoint and quantum computer name are available. |
| QMill Platform     | Package ready        | Exports QASM, manifest, and input payload for QMill upload/compression workflows.                 |
| LUMI Supercomputer | Classical support    | Use for large parameter sweeps or preprocessing, not as a QPU target.                             |
| Google AI Studio   | Not quantum hardware | Useful for product AI, not for quantum circuit execution.                                         |


## 1. Create A Hardware Payload

Start the Q-FIN backend, then export one run:

```powershell
cd quantum_hardware
python .\scripts\prepare_run_payload.py `
  --backend-url http://127.0.0.1:8088 `
  --event "Company becomes the biggest in its market after AI investment and market growth" `
  --out .\inputs\latest_run.json
```

Use `--no-ai` if you only want the local baseline while preparing provider credentials.

## 2. IBM Quantum

Install dependencies:

```powershell
py -m venv .venv-ibm
.\.venv-ibm\Scripts\Activate.ps1
pip install -r requirements-ibm.txt
```

Create a dry-run QASM and receipt:

```powershell
python .\scripts\ibm_sampler_v2_submit.py --input .\inputs\latest_run.json --dry-run
```

Check account credentials before submitting:

```powershell
$env:IBM_QUANTUM_TOKEN="your-token"
$env:IBM_QUANTUM_CHANNEL="ibm_quantum_platform"

python .\scripts\check_ibm_account.py
```

Submit a real small job only after the credential check prints hardware backend names:

```powershell
python .\scripts\ibm_sampler_v2_submit.py `
  --input .\inputs\latest_run.json `
  --shots 256 `
  --submit `
  --wait
```

Optional:

```powershell
$env:IBM_BACKEND="ibm_brisbane"
$env:IBM_QUANTUM_INSTANCE="your-instance"
```

Keep the first hardware run tiny. IBM Open Plan access is limited, so 128-256 shots is enough for the hackathon proof.

## 3. IQM Quantum Stack

IQM Resonance uses `https://resonance.iqm.tech` plus a quantum-computer name such as `sirius`, `emerald`, or `garnet`. The official Qiskit path is provided by `iqm-client[qiskit]`.

On this Windows machine the latest IQM stack installs cleanly in WSL, not in native Windows Python. The WSL runtime is already prepared at:

```text
~/qf-miniconda/bin/python
```

Generate an API token from the IQM Resonance dashboard, then run:

```powershell
wsl bash -lc 'cd /mnt/c/path/to/QuantumFinances && export IQM_TOKEN="your-token" && ~/qf-miniconda/bin/python quantum_hardware/scripts/check_iqm_account.py'
```

Dry-run the Q-FIN circuit:

```powershell
wsl bash -lc 'cd /mnt/c/path/to/QuantumFinances && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_qiskit_submit.py --input quantum_hardware/inputs/latest_run.json --dry-run --shots 128'
```

Submit to IQM Sirius:

```powershell
wsl bash -lc 'cd /mnt/c/path/to/QuantumFinances && export IQM_TOKEN="your-token" && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_qiskit_submit.py --input quantum_hardware/inputs/latest_run.json --shots 128 --submit --wait'
```

Submit the temporal QML circuit:

```powershell
wsl bash -lc 'cd /mnt/c/path/to/QuantumFinances && export IQM_TOKEN="your-token" && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_temporal_qml_submit.py --input quantum_hardware/inputs/latest_run.json --shots 128 --iterations 60 --submit --wait'
```

Run the automatic temporal QML batch and rebuild the paper:

```powershell
powershell -ExecutionPolicy Bypass -File quantum_hardware\scripts\run_iqm_batch_and_build_paper.ps1
```

The runner prompts for the IQM Resonance token, sends the configured batch of temporal-QML jobs, regenerates the figures and tables, and renders `paper\build\main.pdf`.

### Semantic Embedding QML

The compact PESTEL QML path uses 6 PESTEL values. For the research path, use real non-OpenAI sentence embeddings first, then project those high-dimensional vectors into a hardware-sized quantum feature map. The preferred production path is to pass embeddings from the upstream intelligence platform directly in `latest_run.embeddings.json`; the local builder below is for research and demos when the raw cluster text is available.

Build a semantic embedding payload from the ORACLE-style weekly cluster text:

```powershell
wsl bash -lc 'cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python -m pip install -r quantum_hardware/requirements-embeddings.txt'

wsl bash -lc 'cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python quantum_hardware/scripts/build_semantic_embeddings.py --input quantum_hardware/inputs/latest_run.json --out quantum_hardware/inputs/latest_run.embeddings.json --model intfloat/multilingual-e5-large-instruct'
```

That produces `latest_run.embeddings.json` with the original embedding dimension recorded. The file is intentionally git-ignored because real embeddings can become large and may contain semantic information from source data.

Model choices:

- `sentence-transformers/all-MiniLM-L6-v2`: 384-dimensional bootstrap model for low-disk local tests.
- `intfloat/multilingual-e5-large-instruct`: 1024-dimensional multilingual research model; requires more than 1 GB of free cache space.
- `Qwen/Qwen3-Embedding-4B`: up to 2560 dimensions for a larger research run; use only with enough disk/RAM/GPU.

The QPU still receives the projected circuit, not thousands of physical qubits. The receipt records both the original embedding dimension and the latent circuit size.

Dry-run the semantic embedding QML circuit:

```powershell
wsl bash -lc 'cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_semantic_embedding_qml_submit.py --input quantum_hardware/inputs/latest_run.json --embeddings quantum_hardware/inputs/latest_run.embeddings.json --latent-dim 8 --shots 512 --iterations 120 --dry-run'
```

Submit one semantic embedding QML job:

```powershell
wsl bash -lc 'cd /mnt/c/Users/teres/PycharmProjects/q-oracle-scenario-sim && ~/qf-miniconda/bin/python quantum_hardware/scripts/iqm_semantic_embedding_qml_submit.py --input quantum_hardware/inputs/latest_run.json --embeddings quantum_hardware/inputs/latest_run.embeddings.json --latent-dim 8 --shots 512 --iterations 120 --submit --wait'
```

Run a research batch over seeds, shot counts, and circuit sizes:

```powershell
powershell -ExecutionPolicy Bypass -File quantum_hardware\scripts\run_iqm_semantic_batch.ps1
```

The semantic runner uses the high-dimensional embeddings as the real data source, fits a transparent PCA plus seeded signed-random projection into `8..12` latent qubits by default, trains a variational classifier on week-to-week embedding transitions, and submits only the trained inference circuit to IQM hardware.

For a clean non-WSL setup, install dependencies:

```powershell
py -3.13 -m venv .venv-iqm
.\.venv-iqm\Scripts\Activate.ps1
pip install -r requirements-iqm.txt
```

Prepare provider settings from the hackathon pack:

```powershell
$env:IQM_SERVER_URL="https://resonance.iqm.tech"
$env:IQM_QUANTUM_COMPUTER="sirius"
$env:IQM_BACKEND="..."
$env:IQM_TOKEN="your-token"
```

Dry-run:

```powershell
python .\scripts\iqm_qiskit_submit.py --input .\inputs\latest_run.json --dry-run
```

Submit:

```powershell
python .\scripts\iqm_qiskit_submit.py `
  --input .\inputs\latest_run.json `
  --shots 256 `
  --submit `
  --wait
```

## 4. QMill Package

QMill hackathon access may expose a platform-specific UI or API. This exporter creates the portable artifacts to upload or compare there:

```powershell
python .\scripts\qmill_package.py --input .\inputs\latest_run.json --out .\exports\qmill_latest
```

Output:

- `circuit.qasm`
- `manifest.json`
- `input_payload.json`

## Receipt Rule

Only show a run as real hardware when the saved receipt includes:

- provider,
- backend,
- real job id,
- shots,
- circuit fingerprint,
- input run id,
- raw counts or a provider result reference.

