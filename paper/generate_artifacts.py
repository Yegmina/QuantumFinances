from __future__ import annotations

import csv
import glob
import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
FIGURES = PAPER / "figures"
DATA = PAPER / "data"
PESTEL_KEYS = ["political", "economic", "social", "technological", "environmental", "legal"]
CLASS_KEYS = ["stable", "aligned_up", "aligned_down", "uncertain"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def latest_receipt(pattern: str) -> dict[str, Any]:
    files = sorted((Path(item) for item in glob.glob(str(ROOT / pattern))), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        return {}
    return load_json(files[0])


def receipt_by_job(job_id: str, pattern: str) -> dict[str, Any]:
    for item in sorted((Path(path) for path in glob.glob(str(ROOT / pattern))), key=lambda path: path.stat().st_mtime, reverse=True):
        data = load_json(item)
        if data.get("jobId") == job_id:
            return data
    return latest_receipt(pattern)


def percent(value: float) -> float:
    return 100.0 * float(value)


def write_pestel_csv(payload: dict[str, Any]) -> None:
    with (DATA / "pestel_timeline.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["week", *PESTEL_KEYS])
        for week in payload.get("weeklyPestelSeries", []):
            pestel = week.get("pestel") or {}
            writer.writerow([week.get("weekId", ""), *[pestel.get(key, 0.0) for key in PESTEL_KEYS]])


def plot_pestel(payload: dict[str, Any]) -> None:
    weeks = [item.get("weekId", f"W{index}") for index, item in enumerate(payload.get("weeklyPestelSeries", []))]
    x = np.arange(len(weeks))
    plt.figure(figsize=(9, 4.6))
    colors = ["#0b3b75", "#17823b", "#a33d2b", "#5a3c99", "#8b6b00", "#414141"]
    for key, color in zip(PESTEL_KEYS, colors, strict=True):
        values = [percent((item.get("pestel") or {}).get(key, 0.0)) for item in payload.get("weeklyPestelSeries", [])]
        plt.plot(x, values, marker="o", linewidth=2.2, label=key.title(), color=color)
    plt.xticks(x, weeks)
    plt.ylim(0, 70)
    plt.ylabel("Normalized vector value (%)")
    plt.title("Weekly PESTEL World-State Vectors")
    plt.grid(True, axis="y", alpha=0.25)
    plt.legend(ncol=3, fontsize=8)
    plt.tight_layout()
    plt.savefig(FIGURES / "pestel_timeline.png", dpi=220)
    plt.close()


def qml_probabilities(receipt: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    local = ((receipt.get("qml") or {}).get("inferenceProbabilities") or {})
    counts = receipt.get("counts") or {}
    total = sum(int(value) for value in counts.values())
    mapping = {"00": "stable", "01": "aligned_up", "10": "aligned_down", "11": "uncertain"}
    hardware = {key: 0.0 for key in CLASS_KEYS}
    if total > 0:
        for bitstring, count in counts.items():
            hardware[mapping.get(bitstring, bitstring)] = int(count) / total
    return local, hardware


def apply_hardware_archive(feature_receipt: dict[str, Any], qml_receipt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    archive_path = DATA / "hardware_results.json"
    if not archive_path.exists():
        return feature_receipt, qml_receipt
    archive = load_json(archive_path)
    feature = dict(feature_receipt)
    qml = dict(qml_receipt)
    if archive.get("featureCircuit"):
        feature.update(archive["featureCircuit"])
        feature["hardwareJobSubmitted"] = True
    if archive.get("temporalQml"):
        qml.update(archive["temporalQml"])
        qml["hardwareJobSubmitted"] = True
    return feature, qml


def plot_qml_comparison(receipt: dict[str, Any]) -> None:
    local, hardware = qml_probabilities(receipt)
    x = np.arange(len(CLASS_KEYS))
    width = 0.36
    plt.figure(figsize=(8.8, 4.6))
    plt.bar(x - width / 2, [percent(local.get(key, 0.0)) for key in CLASS_KEYS], width, label="Local statevector", color="#174A7C")
    plt.bar(x + width / 2, [percent(hardware.get(key, 0.0)) for key in CLASS_KEYS], width, label="IQM Sirius hardware", color="#C7502B")
    plt.xticks(x, [key.replace("_", " ").title() for key in CLASS_KEYS])
    plt.ylabel("Scenario probability (%)")
    plt.title("Temporal QML Inference: Local Model vs IQM Hardware Samples")
    plt.ylim(0, 65)
    plt.grid(True, axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "qml_local_vs_hardware.png", dpi=220)
    plt.close()


def plot_counts(receipt: dict[str, Any]) -> None:
    counts = receipt.get("counts") or {}
    labels = ["00", "01", "10", "11"]
    plt.figure(figsize=(7.5, 4.2))
    bars = plt.bar(labels, [counts.get(label, 0) for label in labels], color=["#174A7C", "#287D56", "#C7502B", "#777777"])
    plt.ylabel("Measured shots")
    plt.title(f"IQM Temporal QML Counts, Job {receipt.get('jobId', '')[:8]}...")
    plt.ylim(0, max([counts.get(label, 0) for label in labels] + [1]) * 1.25)
    for bar in bars:
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1, str(int(bar.get_height())), ha="center", fontsize=9)
    plt.tight_layout()
    plt.savefig(FIGURES / "iqm_qml_counts.png", dpi=220)
    plt.close()


def plot_pipeline() -> None:
    labels = [
        "News snapshots",
        "TRSG clusters",
        "Weekly PESTEL",
        "Temporal QML",
        "IQM sampling",
        "Scenario probabilities",
    ]
    plt.figure(figsize=(10, 2.6))
    ax = plt.gca()
    ax.axis("off")
    x_positions = np.linspace(0.05, 0.90, len(labels))
    for index, (x, label) in enumerate(zip(x_positions, labels, strict=True)):
        ax.add_patch(plt.Rectangle((x, 0.37), 0.12, 0.26, fill=True, color="#F2F6FA", ec="#123A5A", lw=1.4))
        ax.text(x + 0.06, 0.50, label, ha="center", va="center", fontsize=8.6, wrap=True)
        if index < len(labels) - 1:
            ax.annotate("", xy=(x_positions[index + 1] - 0.01, 0.50), xytext=(x + 0.13, 0.50), arrowprops={"arrowstyle": "->", "lw": 1.4, "color": "#123A5A"})
    ax.set_title("Q-ORACLE Experimental Pipeline", fontsize=12, weight="bold")
    plt.tight_layout()
    plt.savefig(FIGURES / "qoracle_pipeline.png", dpi=220)
    plt.close()


def plot_batch() -> None:
    summary_path = ROOT / "quantum_hardware" / "experiments" / "iqm_qml_batch_summary.json"
    if not summary_path.exists():
        return
    summary = load_json(summary_path)
    records = summary.get("records", [])
    seeds = [str(item.get("seed")) for item in records if item.get("shots") == 128]
    selected = [item for item in records if item.get("shots") == 128]
    has_hardware = any(item.get("hardwareJobSubmitted") and sum((item.get("counts") or {}).values()) > 0 for item in selected)

    def probabilities(record: dict[str, Any]) -> dict[str, float]:
        if has_hardware and record.get("hardwareJobSubmitted") and sum((record.get("counts") or {}).values()) > 0:
            return record.get("hardwareProbabilities") or {}
        return record.get("inferenceProbabilities") or {}

    stable = [percent(probabilities(item).get("stable", 0.0)) for item in selected]
    up = [percent(probabilities(item).get("aligned_up", 0.0)) for item in selected]
    if not seeds:
        return
    x = np.arange(len(seeds))
    plt.figure(figsize=(8.4, 4.4))
    plt.plot(x, stable, marker="o", label="Stable", color="#174A7C")
    plt.plot(x, up, marker="o", label="Aligned up", color="#287D56")
    plt.xticks(x, seeds)
    plt.xlabel("Training seed")
    plt.ylabel(("IQM hardware" if has_hardware else "Local QML") + " probability (%)")
    plt.title(("Hardware" if has_hardware else "Dry-run") + " Batch Temporal QML Sensitivity Across Seeds")
    plt.grid(True, axis="y", alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(FIGURES / "qml_batch_seed_sensitivity.png", dpi=220)
    plt.close()


def write_tables(payload: dict[str, Any], feature_receipt: dict[str, Any], qml_receipt: dict[str, Any]) -> None:
    local, hardware = qml_probabilities(qml_receipt)
    rows = []
    for key in CLASS_KEYS:
        rows.append(
            f"{key.replace('_', ' ').title()} & {percent(local.get(key, 0.0)):.1f}\\% & {percent(hardware.get(key, 0.0)):.1f}\\% \\\\"
        )
    pestel_latest = payload.get("weeklyPestelSeries", [])[-1].get("pestel", {})
    pestel_rows = [f"{key.title()} & {percent(pestel_latest.get(key, 0.0)):.1f}\\% \\\\" for key in PESTEL_KEYS]
    counts = qml_receipt.get("counts") or {}
    count_rows = [f"{bit} & {counts.get(bit, 0)} & {percent((counts.get(bit, 0) / max(1, sum(counts.values())))):.1f}\\% \\\\" for bit in ["00", "01", "10", "11"]]
    batch_summary = load_json(ROOT / "quantum_hardware" / "experiments" / "iqm_qml_batch_summary.json")
    batch_records = batch_summary.get("records", [])
    real_batch_records = [
        item for item in batch_records if item.get("hardwareJobSubmitted") and sum((item.get("counts") or {}).values()) > 0
    ]
    batch_mode = "IQM hardware" if real_batch_records else "Dry-run"
    batch_count = len(real_batch_records) if real_batch_records else len(batch_records)
    batch_shots = sum(int(item.get("shots", 0)) for item in (real_batch_records if real_batch_records else batch_records))

    tex = r"""
\begin{table}[t]
\centering
\small
\begin{tabular}{lrr}
\toprule
Class & Local QML & IQM hardware \\
\midrule
""" + "\n".join(rows) + r"""
\bottomrule
\end{tabular}
\caption{Temporal QML scenario distribution. The local column is the statevector prediction after classical training; the hardware column is sampled from IQM Sirius.}
\label{tab:qml-results}
\end{table}

\begin{table}[t]
\centering
\small
\begin{tabular}{lr}
\toprule
Dimension & Latest value \\
\midrule
""" + "\n".join(pestel_rows) + r"""
\bottomrule
\end{tabular}
\caption{Latest weekly PESTEL vector used for feature encoding.}
\label{tab:pestel-latest}
\end{table}

\begin{table}[t]
\centering
\small
\begin{tabular}{lrr}
\toprule
Bitstring & Count & Share \\
\midrule
""" + "\n".join(count_rows) + r"""
\bottomrule
\end{tabular}
\caption{Raw IQM temporal-QML hardware counts.}
\label{tab:counts}
\end{table}

\begin{table}[t]
\centering
\scriptsize
\begin{tabular}{lp{0.38\columnwidth}r}
\toprule
Experiment & Job ID & Shots \\
\midrule
Feature circuit & """ + str(feature_receipt.get("jobId", "")) + r""" & """ + str(feature_receipt.get("shots", "")) + r""" \\
Temporal QML & """ + str(qml_receipt.get("jobId", "")) + r""" & """ + str(qml_receipt.get("shots", "")) + r""" \\
\bottomrule
\end{tabular}
\caption{Verified IQM hardware jobs available at paper-generation time.}
\label{tab:hardware-jobs}
\end{table}

\begin{table}[t]
\centering
\small
\begin{tabular}{lr}
\toprule
Batch mode & """ + batch_mode + r""" \\
Records & """ + str(batch_count) + r""" \\
Total shots & """ + str(batch_shots) + r""" \\
\bottomrule
\end{tabular}
\caption{Automatic temporal-QML batch summary used for the seed-sensitivity figure.}
\label{tab:batch-summary}
\end{table}
"""
    (DATA / "tables.tex").write_text(tex, encoding="utf-8")


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    payload = load_json(ROOT / "quantum_hardware" / "inputs" / "latest_run.json")
    feature_receipt = receipt_by_job("019e9de2-2ab7-7653-9134-15e34fbe5926", "quantum_hardware/receipts/iqm_*.json")
    qml_receipt = receipt_by_job("019e9de9-956e-7622-ace6-80049a84a06c", "quantum_hardware/receipts/iqm_qml_*.json")
    feature_receipt, qml_receipt = apply_hardware_archive(feature_receipt, qml_receipt)

    write_pestel_csv(payload)
    plot_pestel(payload)
    plot_qml_comparison(qml_receipt)
    plot_counts(qml_receipt)
    plot_pipeline()
    plot_batch()
    write_tables(payload, feature_receipt, qml_receipt)
    print(f"Wrote figures to {FIGURES}")
    print(f"Wrote data tables to {DATA}")


if __name__ == "__main__":
    main()
