from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from common import (
    build_quantumfinances_circuit,
    circuit_fingerprint,
    circuit_to_qasm,
    counts_from_ibm_sampler_result,
    job_id_from,
    load_payload,
    safe_backend_name,
    write_json,
)


def service_kwargs(args: argparse.Namespace) -> dict:
    kwargs = {"channel": args.channel}
    if args.token:
        kwargs["token"] = args.token
    if args.instance:
        kwargs["instance"] = args.instance
    return kwargs


def select_backend(service, backend_name: str | None, qubits: int):
    if backend_name:
        return service.backend(backend_name)
    try:
        return service.least_busy(operational=True, simulator=False, min_num_qubits=qubits)
    except TypeError:
        return service.least_busy(simulator=False, min_num_qubits=qubits)


def friendly_ibm_auth_error(exc: Exception) -> str:
    return (
        "IBM Quantum authentication failed before any hardware job was submitted.\n"
        "Create a new IBM Quantum Platform API key, set IBM_QUANTUM_TOKEN to that new value, "
        "and rerun scripts/check_ibm_account.py first.\n"
        f"Provider error: {exc}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a Q-FIN circuit through IBM Qiskit Runtime SamplerV2.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "sample_run.json"))
    parser.add_argument("--out", default="")
    parser.add_argument("--shots", type=int, default=256)
    parser.add_argument("--backend", default=os.getenv("IBM_BACKEND", ""))
    parser.add_argument("--channel", default=os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform"))
    parser.add_argument("--instance", default=os.getenv("IBM_QUANTUM_INSTANCE", ""))
    parser.add_argument("--token", default=os.getenv("IBM_QUANTUM_TOKEN", ""))
    parser.add_argument("--optimization-level", type=int, default=1, choices=[0, 1, 2, 3])
    parser.add_argument("--measure-all", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Build circuit and receipt without submitting.")
    parser.add_argument("--submit", action="store_true", help="Actually submit a job to IBM Quantum.")
    parser.add_argument("--wait", action="store_true", help="Wait for result and save counts.")
    args = parser.parse_args()

    payload = load_payload(args.input)
    circuit, metadata = build_quantumfinances_circuit(payload, measure_all=args.measure_all)
    qasm = circuit_to_qasm(circuit)
    fingerprint = circuit_fingerprint(qasm)

    output_path = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / "receipts" / f"ibm_{fingerprint}.json"
    receipt = {
        "provider": "ibm_quantum",
        "mode": "dry_run" if not args.submit else "submitted",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(Path(args.input).resolve()),
        "inputRunId": payload.get("runId"),
        "shots": args.shots,
        "channel": args.channel,
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
        print(f"IBM dry-run receipt written: {output_path}")
        print("Add --submit to send this circuit to IBM Quantum.")
        return

    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

    try:
        service = QiskitRuntimeService(**service_kwargs(args))
        backend = select_backend(service, args.backend or None, circuit.num_qubits)
    except Exception as exc:
        raise SystemExit(friendly_ibm_auth_error(exc)) from exc
    pass_manager = generate_preset_pass_manager(optimization_level=args.optimization_level, backend=backend)
    isa_circuit = pass_manager.run(circuit)

    sampler = Sampler(mode=backend)
    job = sampler.run([isa_circuit], shots=args.shots)
    receipt.update(
        {
            "mode": "submitted",
            "hardwareJobSubmitted": True,
            "backend": safe_backend_name(backend),
            "jobId": job_id_from(job),
            "transpiledDepth": isa_circuit.depth(),
            "transpiledQasm": circuit_to_qasm(isa_circuit),
        }
    )

    if args.wait:
        result = job.result()
        receipt["counts"] = counts_from_ibm_sampler_result(result)
        receipt["resultRepr"] = repr(result)[:4000]

    write_json(output_path, receipt)
    print(f"IBM receipt written: {output_path}")
    print(f"Job id: {receipt.get('jobId')}")


if __name__ == "__main__":
    main()
