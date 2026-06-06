from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CLASS_NAMES = ["stable", "event_aligned", "event_divergent", "uncertain"]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def probabilities_from_counts(counts: dict[str, int]) -> dict[str, float]:
    total = sum(int(value) for value in counts.values())
    if total <= 0:
        return {label: 0.0 for label in CLASS_NAMES}
    mapping = {"00": "stable", "01": "event_aligned", "10": "event_divergent", "11": "uncertain"}
    return {mapping.get(key, key): int(value) / total for key, value in counts.items()}


def run_one(args: argparse.Namespace, seed: int, shots: int, latent_dim: int) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    repo_root = Path(__file__).resolve().parents[2]
    receipts_dir = root / "receipts"
    mode = "hardware" if args.submit else "dryrun"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = receipts_dir / f"iqm_semantic_qml_batch_{mode}_seed{seed}_shots{shots}_q{latent_dim}_{stamp}.json"
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("iqm_semantic_embedding_qml_submit.py")),
        "--input",
        args.input,
        "--embeddings",
        args.embeddings,
        "--out",
        str(output_path),
        "--shots",
        str(shots),
        "--iterations",
        str(args.iterations),
        "--seed",
        str(seed),
        "--latent-dim",
        str(latent_dim),
        "--layers",
        str(args.layers),
        "--max-statevector-qubits",
        str(args.max_statevector_qubits),
    ]
    if args.submit:
        cmd.append("--submit")
        if args.wait:
            cmd.append("--wait")
    else:
        cmd.append("--dry-run")
    if args.quantum_computer:
        cmd.extend(["--quantum-computer", args.quantum_computer])

    completed = subprocess.run(cmd, cwd=str(repo_root), text=True, capture_output=True)

    def display_path(path: Path) -> str:
        try:
            return path.relative_to(repo_root).as_posix()
        except ValueError:
            return str(path)

    def scrub(text: str) -> str:
        return text.replace(str(repo_root), "<repo>").replace(str(repo_root).replace("\\", "/"), "<repo>")

    record: dict[str, Any] = {
        "seed": seed,
        "shots": shots,
        "latentDim": latent_dim,
        "iterations": args.iterations,
        "returnCode": completed.returncode,
        "stdout": scrub(completed.stdout.strip()),
        "stderr": scrub(completed.stderr.strip()),
        "receiptPath": display_path(output_path),
    }
    if output_path.exists():
        receipt = read_json(output_path)
        record.update(
            {
                "jobId": receipt.get("jobId", ""),
                "hardwareJobSubmitted": receipt.get("hardwareJobSubmitted", False),
                "circuitDepth": receipt.get("circuitDepth", 0),
                "transpiledDepth": receipt.get("transpiledDepth", 0),
                "qubits": receipt.get("qubits", 0),
                "counts": receipt.get("counts", {}),
                "hardwareProbabilities": probabilities_from_counts(receipt.get("counts", {})),
                "inferenceProbabilities": (receipt.get("qml") or {}).get("inferenceProbabilities", {}),
                "trainingHistory": (receipt.get("qml") or {}).get("trainingHistory", []),
            }
        )
    if completed.returncode != 0 and args.stop_on_error:
        raise SystemExit(f"Semantic batch job failed seed={seed} shots={shots} q={latent_dim}.\n{completed.stderr}")
    return record


def write_summary(out_dir: Path, records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "submit": args.submit,
        "wait": args.wait,
        "input": args.input,
        "embeddings": args.embeddings,
        "records": records,
    }
    (out_dir / "iqm_semantic_qml_batch_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with (out_dir / "iqm_semantic_qml_batch_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "seed",
                "shots",
                "latentDim",
                "iterations",
                "hardwareJobSubmitted",
                "jobId",
                "qubits",
                "circuitDepth",
                "transpiledDepth",
                "stable",
                "event_aligned",
                "event_divergent",
                "uncertain",
                "receiptPath",
            ],
        )
        writer.writeheader()
        for record in records:
            probabilities = record.get("hardwareProbabilities") or record.get("inferenceProbabilities") or {}
            writer.writerow(
                {
                    "seed": record.get("seed"),
                    "shots": record.get("shots"),
                    "latentDim": record.get("latentDim"),
                    "iterations": record.get("iterations"),
                    "hardwareJobSubmitted": record.get("hardwareJobSubmitted"),
                    "jobId": record.get("jobId", ""),
                    "qubits": record.get("qubits", ""),
                    "circuitDepth": record.get("circuitDepth", ""),
                    "transpiledDepth": record.get("transpiledDepth", ""),
                    "stable": probabilities.get("stable", ""),
                    "event_aligned": probabilities.get("event_aligned", ""),
                    "event_divergent": probabilities.get("event_divergent", ""),
                    "uncertain": probabilities.get("uncertain", ""),
                    "receiptPath": record.get("receiptPath", ""),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated semantic-embedding QML experiments on IQM or dry-run.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.json"))
    parser.add_argument(
        "--embeddings",
        default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.embeddings.json"),
    )
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "experiments"))
    parser.add_argument("--seeds", default="41,42,43")
    parser.add_argument("--shots", default="512,1024")
    parser.add_argument("--latent-dims", default="8,10,12")
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--max-statevector-qubits", type=int, default=12)
    parser.add_argument("--quantum-computer", default=os.getenv("IQM_QUANTUM_COMPUTER", "sirius"))
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    if args.submit and not os.getenv("IQM_TOKEN"):
        raise SystemExit("IQM_TOKEN is required for real semantic-QML batch submission.")
    if not Path(args.embeddings).exists():
        raise SystemExit(
            f"Semantic embedding file not found: {args.embeddings}. "
            "Build it first with build_semantic_embeddings.py."
        )

    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
    shot_values = [int(item.strip()) for item in args.shots.split(",") if item.strip()]
    latent_dims = [int(item.strip()) for item in args.latent_dims.split(",") if item.strip()]
    records = []
    for latent_dim in latent_dims:
        for seed in seeds:
            for shots in shot_values:
                print(f"Running semantic QML seed={seed} shots={shots} q={latent_dim} submit={args.submit}")
                records.append(run_one(args, seed=seed, shots=shots, latent_dim=latent_dim))

    write_summary(Path(args.out_dir), records, args)
    print(f"Wrote semantic batch summary: {Path(args.out_dir) / 'iqm_semantic_qml_batch_summary.json'}")
    print(f"Wrote semantic batch table: {Path(args.out_dir) / 'iqm_semantic_qml_batch_summary.csv'}")


if __name__ == "__main__":
    main()
