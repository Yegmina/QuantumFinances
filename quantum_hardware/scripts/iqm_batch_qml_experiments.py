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


CLASS_LABELS = {
    "00": "stable",
    "01": "aligned_up",
    "10": "aligned_down",
    "11": "uncertain",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_receipt(before: set[Path], receipts_dir: Path) -> Path | None:
    after = set(receipts_dir.glob("iqm_qml_*.json"))
    new_files = sorted(after - before, key=lambda item: item.stat().st_mtime, reverse=True)
    if new_files:
        return new_files[0]
    existing = sorted(after, key=lambda item: item.stat().st_mtime, reverse=True)
    return existing[0] if existing else None


def probabilities_from_counts(counts: dict[str, int]) -> dict[str, float]:
    total = sum(int(value) for value in counts.values())
    if total <= 0:
        return {label: 0.0 for label in CLASS_LABELS.values()}
    return {CLASS_LABELS.get(key, key): int(value) / total for key, value in counts.items()}


def run_one(args: argparse.Namespace, seed: int, shots: int, iterations: int) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    receipts_dir = root / "receipts"
    before = set(receipts_dir.glob("iqm_qml_*.json"))
    cmd = [
        sys.executable,
        str(Path(__file__).with_name("iqm_temporal_qml_submit.py")),
        "--input",
        args.input,
        "--shots",
        str(shots),
        "--iterations",
        str(iterations),
        "--seed",
        str(seed),
    ]
    if args.submit:
        cmd.append("--submit")
        if args.wait:
            cmd.append("--wait")
    else:
        cmd.append("--dry-run")
    if args.quantum_computer:
        cmd.extend(["--quantum-computer", args.quantum_computer])

    completed = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parents[2]), text=True, capture_output=True)
    receipt_path = latest_receipt(before, receipts_dir)
    record: dict[str, Any] = {
        "seed": seed,
        "shots": shots,
        "iterations": iterations,
        "returnCode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "receiptPath": str(receipt_path) if receipt_path else "",
    }
    if receipt_path and receipt_path.exists():
        receipt = read_json(receipt_path)
        record.update(
            {
                "jobId": receipt.get("jobId", ""),
                "hardwareJobSubmitted": receipt.get("hardwareJobSubmitted", False),
                "circuitDepth": receipt.get("circuitDepth", 0),
                "transpiledDepth": receipt.get("transpiledDepth", 0),
                "counts": receipt.get("counts", {}),
                "hardwareProbabilities": probabilities_from_counts(receipt.get("counts", {})),
                "inferenceProbabilities": (receipt.get("qml") or {}).get("inferenceProbabilities", {}),
                "trainingHistory": (receipt.get("qml") or {}).get("trainingHistory", []),
            }
        )
    if completed.returncode != 0 and args.stop_on_error:
        raise SystemExit(f"Batch job failed for seed={seed}, shots={shots}.\n{completed.stderr}")
    return record


def write_summary(out_dir: Path, records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "submit": args.submit,
        "wait": args.wait,
        "input": args.input,
        "records": records,
    }
    (out_dir / "iqm_qml_batch_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    with (out_dir / "iqm_qml_batch_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "seed",
                "shots",
                "iterations",
                "hardwareJobSubmitted",
                "jobId",
                "circuitDepth",
                "transpiledDepth",
                "stable",
                "aligned_up",
                "aligned_down",
                "uncertain",
                "receiptPath",
            ],
        )
        writer.writeheader()
        for record in records:
            probs = record.get("hardwareProbabilities") or record.get("inferenceProbabilities") or {}
            writer.writerow(
                {
                    "seed": record.get("seed"),
                    "shots": record.get("shots"),
                    "iterations": record.get("iterations"),
                    "hardwareJobSubmitted": record.get("hardwareJobSubmitted"),
                    "jobId": record.get("jobId", ""),
                    "circuitDepth": record.get("circuitDepth", ""),
                    "transpiledDepth": record.get("transpiledDepth", ""),
                    "stable": probs.get("stable", ""),
                    "aligned_up": probs.get("aligned_up", ""),
                    "aligned_down": probs.get("aligned_down", ""),
                    "uncertain": probs.get("uncertain", ""),
                    "receiptPath": record.get("receiptPath", ""),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated QuantumFinances temporal QML experiments on IQM or dry-run.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.json"))
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "experiments"))
    parser.add_argument("--seeds", default="41,42,43,44,45")
    parser.add_argument("--shots", default="64,128")
    parser.add_argument("--iterations", type=int, default=60)
    parser.add_argument("--quantum-computer", default=os.getenv("IQM_QUANTUM_COMPUTER", "sirius"))
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    args = parser.parse_args()

    if args.submit and not os.getenv("IQM_TOKEN"):
        raise SystemExit("IQM_TOKEN is required for real batch submission. Set it in the environment first.")

    seeds = [int(item.strip()) for item in args.seeds.split(",") if item.strip()]
    shot_values = [int(item.strip()) for item in args.shots.split(",") if item.strip()]
    records = []
    for seed in seeds:
        for shots in shot_values:
            print(f"Running temporal QML experiment seed={seed} shots={shots} submit={args.submit}")
            records.append(run_one(args, seed=seed, shots=shots, iterations=args.iterations))

    write_summary(Path(args.out_dir), records, args)
    print(f"Wrote batch summary: {Path(args.out_dir) / 'iqm_qml_batch_summary.json'}")
    print(f"Wrote batch table: {Path(args.out_dir) / 'iqm_qml_batch_summary.csv'}")


if __name__ == "__main__":
    main()
