from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from common import (
    build_quantumfinances_circuit,
    circuit_fingerprint,
    circuit_to_qasm,
    load_payload,
    write_json,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a QuantumFinances circuit package for QMill workflows.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "sample_run.json"))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "exports" / "qmill_package"))
    parser.add_argument("--measure-all", action="store_true")
    args = parser.parse_args()

    payload = load_payload(args.input)
    circuit, metadata = build_quantumfinances_circuit(payload, measure_all=args.measure_all)
    qasm = circuit_to_qasm(circuit)
    fingerprint = circuit_fingerprint(qasm)
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)

    qasm_path = output_dir / "circuit.qasm"
    payload_path = output_dir / "input_payload.json"
    manifest_path = output_dir / "manifest.json"

    qasm_path.write_text(qasm, encoding="utf-8")
    payload_path.write_text(Path(args.input).read_text(encoding="utf-8"), encoding="utf-8")
    write_json(
        manifest_path,
        {
            "provider": "qmill",
            "mode": "portable_package",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "inputRunId": payload.get("runId"),
            "circuitFingerprint": fingerprint,
            "qasmFile": qasm_path.name,
            "inputPayloadFile": payload_path.name,
            "circuitDepth": circuit.depth(),
            "qubits": circuit.num_qubits,
            "metadata": metadata,
            "notes": "Upload circuit.qasm and input_payload.json to the QMill platform workflow supplied by the hackathon pack.",
        },
    )
    print(f"QMill package written: {output_dir}")


if __name__ == "__main__":
    main()

