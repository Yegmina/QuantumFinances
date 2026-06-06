from __future__ import annotations

import argparse
import os


DEFAULT_IQM_SERVER_URL = "https://resonance.iqm.tech"
DEFAULT_IQM_QUANTUM_COMPUTER = "sirius"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check IQM Resonance credentials without submitting a job.")
    parser.add_argument("--server-url", default=os.getenv("IQM_SERVER_URL", DEFAULT_IQM_SERVER_URL))
    parser.add_argument("--quantum-computer", default=os.getenv("IQM_QUANTUM_COMPUTER", DEFAULT_IQM_QUANTUM_COMPUTER))
    parser.add_argument("--token", default="", help="Optional explicit token. Prefer IQM_TOKEN env var.")
    args = parser.parse_args()

    if not args.token and not os.getenv("IQM_TOKEN"):
        raise SystemExit("IQM_TOKEN is not set. Generate a token in IQM Resonance, then set IQM_TOKEN.")

    try:
        from iqm.qiskit_iqm import IQMProvider
    except Exception as exc:
        raise SystemExit(
            "Could not import IQMProvider. Install with `pip install \"iqm-client[qiskit]\"`.\n"
            f"Import error: {exc}"
        ) from exc

    try:
        provider_kwargs = {"quantum_computer": args.quantum_computer}
        if args.token:
            provider_kwargs["token"] = args.token
            os.environ.pop("IQM_TOKEN", None)
        provider = IQMProvider(args.server_url, **provider_kwargs)
        backend = provider.get_backend()
        print("IQM Resonance authentication OK.")
        print(f"Server: {args.server_url}")
        print(f"Quantum computer: {args.quantum_computer}")
        print(f"Backend: {backend}")
        target = getattr(backend, "target", None)
        if target is not None:
            print(f"Target qubits: {getattr(target, 'num_qubits', 'unknown')}")
            print(f"Operations: {sorted(str(name) for name in getattr(target, 'operation_names', []))}")
    except Exception as exc:
        raise SystemExit(
            "IQM Resonance check failed before any hardware job was submitted.\n"
            f"Provider error: {exc}"
        ) from exc


if __name__ == "__main__":
    main()
