# QuantumFinances Hardware Preparation

This folder prepares a QuantumFinances scenario run for real quantum-computer execution.

Default behavior is intentionally dry-run. A real hardware job is submitted only when a provider script is run with `--submit`.

## Provider Targets

| Target | Status | Use |
| --- | --- | --- |
| IBM Quantum | Ready | Qiskit Runtime `SamplerV2` hardware submission with a tiny circuit and saved receipt. |
| IQM Quantum Stack | Ready | Qiskit-on-IQM submission when the hackathon IQM endpoint and quantum computer name are available. |
| QMill Platform | Package ready | Exports QASM, manifest, and input payload for QMill upload/compression workflows. |
| LUMI Supercomputer | Classical support | Use for large parameter sweeps or preprocessing, not as a QPU target. |
| Google AI Studio | Not quantum hardware | Useful for product AI, not for quantum circuit execution. |

## 1. Create A Hardware Payload

Start the QuantumFinances backend, then export one run:

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

Install dependencies:

```powershell
py -m venv .venv-iqm
.\.venv-iqm\Scripts\Activate.ps1
pip install -r requirements-iqm.txt
```

Prepare provider settings from the hackathon pack:

```powershell
$env:IQM_SERVER_URL="https://..."
$env:IQM_QUANTUM_COMPUTER="..."
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
