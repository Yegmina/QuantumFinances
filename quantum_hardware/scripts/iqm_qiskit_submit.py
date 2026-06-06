from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from common import (
    build_quantumfinances_circuit,
    circuit_fingerprint,
    circuit_to_qasm,
    job_id_from,
    load_payload,
    safe_backend_name,
    write_json,
)


DEFAULT_IQM_SERVER_URL = "https://resonance.iqm.tech"
DEFAULT_IQM_QUANTUM_COMPUTER = "sirius"


def import_iqm_provider():
    try:
        from iqm.qiskit_iqm import IQMProvider
    except Exception as exc:
        raise SystemExit(
            "Could not import IQMProvider. Install the Resonance stack with "
            "`pip install \"iqm-client[qiskit]\"`. If Windows installation fails, use WSL, qBraid, or Colab.\n"
            f"Import error: {exc}"
        ) from exc
    return IQMProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a QuantumFinances circuit through Qiskit-on-IQM.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "sample_run.json"))
    parser.add_argument("--out", default="")
    parser.add_argument("--shots", type=int, default=256)
    parser.add_argument("--server-url", default=os.getenv("IQM_SERVER_URL", DEFAULT_IQM_SERVER_URL))
    parser.add_argument("--quantum-computer", default=os.getenv("IQM_QUANTUM_COMPUTER", DEFAULT_IQM_QUANTUM_COMPUTER))
    parser.add_argument("--backend", default=os.getenv("IQM_BACKEND", ""))
    parser.add_argument("--token", default=os.getenv("IQM_TOKEN", ""))
    parser.add_argument("--tokens-file", default=os.getenv("IQM_TOKENS_FILE", ""))
    parser.add_argument("--optimization-level", type=int, default=1, choices=[0, 1, 2, 3])
    parser.add_argument("--measure-all", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Build circuit and receipt without submitting.")
    parser.add_argument("--submit", action="store_true", help="Actually submit a job to IQM.")
    parser.add_argument("--wait", action="store_true", help="Wait for result and save counts.")
    args = parser.parse_args()

    payload = load_payload(args.input)
    circuit, metadata = build_quantumfinances_circuit(payload, measure_all=args.measure_all)
    qasm = circuit_to_qasm(circuit)
    fingerprint = circuit_fingerprint(qasm)

    output_path = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / "receipts" / f"iqm_{fingerprint}.json"
    receipt = {
        "provider": "iqm",
        "mode": "dry_run" if not args.submit else "submitted",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(Path(args.input).resolve()),
        "inputRunId": payload.get("runId"),
        "shots": args.shots,
        "serverUrlConfigured": bool(args.server_url),
        "quantumComputerConfigured": bool(args.quantum_computer),
        "authConfigured": bool(args.token or args.tokens_file),
        "requestedBackend": args.backend or None,
        "hardwareJobSubmitted": False,
        "circuitFingerprint": fingerprint,
        "circuitDepth": circuit.depth(),
        "qubits": circuit.num_qubits,
        "metadata": metadata,
        "qasm": qasm,
    }

    if not args.submit:
        write_json(output_path, receipt)
        print(f"IQM dry-run receipt written: {output_path}")
        print("Set IQM_TOKEN and add --submit to run on IQM Resonance.")
        return

    if not args.server_url:
        raise SystemExit("IQM_SERVER_URL or --server-url is required for submission.")
    if not args.token and not os.getenv("IQM_TOKEN"):
        raise SystemExit("IQM_TOKEN is required for Resonance submission. Generate it in the IQM Resonance dashboard first.")

    from qiskit import transpile

    IQMProvider = import_iqm_provider()
    provider_kwargs = {}
    if args.quantum_computer:
        provider_kwargs["quantum_computer"] = args.quantum_computer
    if args.token:
        provider_kwargs["token"] = args.token
    if args.tokens_file:
        provider_kwargs["tokens_file"] = args.tokens_file
    provider = IQMProvider(args.server_url, **provider_kwargs)
    backend = provider.get_backend(args.backend) if args.backend else provider.get_backend()
    transpiled = transpile(circuit, backend=backend, optimization_level=args.optimization_level)
    job = backend.run(transpiled, shots=args.shots)

    receipt.update(
        {
            "mode": "submitted",
            "hardwareJobSubmitted": True,
            "backend": safe_backend_name(backend),
            "jobId": job_id_from(job),
            "transpiledDepth": transpiled.depth(),
            "transpiledQasm": circuit_to_qasm(transpiled),
        }
    )

    if args.wait:
        result = job.result()
        get_counts = getattr(result, "get_counts", None)
        receipt["counts"] = get_counts() if callable(get_counts) else {}
        receipt["resultRepr"] = repr(result)[:4000]

    write_json(output_path, receipt)
    print(f"IQM receipt written: {output_path}")
    print(f"Job id: {receipt.get('jobId')}")


if __name__ == "__main__":
    main()
