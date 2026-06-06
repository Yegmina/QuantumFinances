from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Check IBM Quantum credentials without submitting a job.")
    parser.add_argument("--channel", default=os.getenv("IBM_QUANTUM_CHANNEL", "ibm_quantum_platform"))
    parser.add_argument("--token", default=os.getenv("IBM_QUANTUM_TOKEN", ""))
    parser.add_argument("--instance", default=os.getenv("IBM_QUANTUM_INSTANCE", ""))
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if not args.token:
        raise SystemExit("IBM_QUANTUM_TOKEN is not set. Create a new IBM Quantum Platform API key and set it first.")

    from qiskit_ibm_runtime import QiskitRuntimeService

    kwargs = {"channel": args.channel, "token": args.token}
    if args.instance:
        kwargs["instance"] = args.instance

    try:
        service = QiskitRuntimeService(**kwargs)
        backends = service.backends(simulator=False, operational=True)
        print("IBM Quantum authentication OK.")
        print(f"Available operational hardware backends: {len(backends)}")
        for backend in backends[: args.limit]:
            name = backend.name() if callable(getattr(backend, "name", None)) else backend.name
            print(f"- {name}")
        try:
            usage = service.usage()
            print(f"Usage: {usage}")
        except Exception as exc:
            print(f"Usage check skipped: {exc}")
    except Exception as exc:
        raise SystemExit(
            "IBM Quantum authentication failed. No hardware job was submitted.\n"
            "Most likely causes: invalid/revoked API key, wrong IBM account, or missing instance/CRN.\n"
            f"Provider error: {exc}"
        ) from exc


if __name__ == "__main__":
    main()
