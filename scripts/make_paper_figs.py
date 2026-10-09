"""Paper figures from the locked metric JSON files (no hand-entered numbers)."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / "outputs/test_main"
OUT = ROOT / "paper/figs"
NAMES = {"b0": "B0", "b1": "B1", "b2raw": "B2 (per-chunk)", "b2doc": "B2-doc", "b2": "B2-win",
         "ours_a0_b0.8_g0_k-0.2_tnone": "B3", "ours_a1_b0.8_g0.4_k-0.2_tnone": "Ours"}
ORDER = ["b0", "b1", "b2raw", "b2doc", "b2", "ours_a0_b0.8_g0_k-0.2_tnone", "ours_a1_b0.8_g0.4_k-0.2_tnone"]


def load() -> dict:
    m = json.loads((M / "metrics_final_system.json").read_text())
    m["b2doc"] = json.loads((M / "metrics_b2doc.json").read_text())["b2doc"]
    m["b1"] = json.loads((M / "metrics_b1.json").read_text())["b1"]
    return m


def tradeoff(m: dict) -> None:
    fig, ax = plt.subplots(figsize=(3.4, 2.6))
    for k in ORDER:
        o = m[k]["overall"]
        x, y = o["asr"]["rate"] * 100, o["answer_retention_attack"]["rate"] * 100
        lo, hi = o["asr"]["ci95"]
        ax.errorbar(x, y, xerr=[[x - lo * 100], [hi * 100 - x]], fmt="o", ms=4, capsize=2)
        label = {"b2": "B2-win = B3", "ours_a0_b0.8_g0_k-0.2_tnone": None}.get(k, NAMES[k])
        off = {"b0": (4, -11), "b1": (-12, 4), "b2raw": (-12, -12), "ours_a1_b0.8_g0.4_k-0.2_tnone": (8, 2), "b2": (6, -11)}.get(k, (5, 3))
        if label:
            ax.annotate(label, (x, y), textcoords="offset points", xytext=off, fontsize=7)
    ax.set_xlabel("Attack success rate (%), n=300")
    ax.set_ylabel("Answer kept (%), n=120")
    ax.set_xlim(-1, 16)
    ax.set_ylim(0, 105)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "tradeoff.pdf")


def breakdown(m: dict) -> None:
    keys = ["b0", "b2raw", "ours_a1_b0.8_g0.4_k-0.2_tnone"]
    fams = sorted(g[7:] for g in m["b0"] if g.startswith("family="))
    pos = ["start", "middle", "end"]
    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.8), gridspec_kw={"width_ratios": [5, 1.3]})
    w = 0.27
    for j, k in enumerate(keys):
        fy = [m[k][f"family={f}"]["asr"]["k"] for f in fams]
        axes[0].bar([i + (j - 1) * w for i in range(len(fams))], fy, w, label=NAMES[k])
        py = [m[k][f"position={p}"]["asr"]["k"] for p in pos]
        axes[1].bar([i + (j - 1) * w for i in range(3)], py, w)
    axes[0].set_xticks(range(len(fams)))
    axes[0].set_xticklabels(fams, rotation=60, ha="right", fontsize=6)
    axes[0].set_ylabel("Successful attacks (count)")
    axes[0].set_title("By attack family (n≈20 each)", fontsize=8)
    axes[0].legend(fontsize=7)
    axes[1].set_xticks(range(3))
    axes[1].set_xticklabels(pos, fontsize=7)
    axes[1].set_title("By position (n≈100)", fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "breakdown.pdf")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    data = load()
    tradeoff(data)
    breakdown(data)
    print("wrote", sorted(p.name for p in OUT.iterdir()))
