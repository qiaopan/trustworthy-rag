"""Deck-styled figures for the talk (presentation/figs/deck_*.png).

Numbers are copied from the locked main-Test results (paper Table "main" and
Fig. "breakdown"); they are not recomputed here.
Run: python presentation/make_deck_figs.py
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

HERE = Path(__file__).resolve().parent
INK, SLATE, MUTED = "#1B2A41", "#4A5A70", "#8A96A8"
ATTACK, SAFE, AMBER, GRID = "#C8443F", "#21867A", "#D9922E", "#E3E8EE"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 13, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": SLATE, "ytick.color": SLATE,
    "axes.spines.top": False, "axes.spines.right": False,
})

# --- Trade-off: ASR (Wilson 95% CI) vs answers kept (/120) -------------------
pts = [  # name, ASR %, lo, hi, answers kept /120, colour, label offset
    ("B0 no defence", 10.0, 7.1, 13.9, 119, MUTED, (0.3, -7)),
    ("B2 per-chunk PIGuard", 5.0, 3.1, 8.1, 119, AMBER, (0.3, -7)),
    ("B2-win / B3 (risk only)", 0.3, 0.1, 1.9, 93, SLATE, (1.9, -1.5)),
    ("B2-doc whole email", 0.0, 0.0, 1.3, 8, ATTACK, (1.6, -1.5)),
    ("Ours", 0.7, 0.2, 2.4, 108, SAFE, (2.0, -1.5)),
]
fig, ax = plt.subplots(figsize=(7.6, 5.6), dpi=220)
ax.axhspan(100, 125, xmin=0, xmax=0.2, color=SAFE, alpha=0.07, lw=0)
ax.text(-0.3, 124, "ideal corner", color=SAFE, fontsize=11, va="top")
ax.axhline(99, color=SLATE, lw=1, ls=":")
ax.text(14.4, 96.5, "best risk-only threshold (sweep): 99", color=SLATE, fontsize=10.5, ha="right", va="top")
for name, asr, lo, hi, kept, col, (dx, dy) in pts:
    ax.plot([lo, hi], [kept, kept], color=col, lw=2.5, alpha=0.55, solid_capstyle="round")
    ax.scatter([asr], [kept], s=150 if name == "Ours" else 95, color=col, zorder=3,
               edgecolor="white", linewidth=1.5)
    ax.annotate(name, (asr, kept), xytext=(asr + dx, kept + dy), color=col if col != MUTED else SLATE,
                fontsize=12.5, fontweight="bold" if name == "Ours" else "normal")
ax.set_xlim(-0.5, 15)
ax.set_ylim(0, 125)
ax.set_xlabel("Attack success rate (%)  ← better")
ax.set_ylabel("Answers kept (of 120)  better →")
ax.grid(color=GRID, lw=0.8)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(HERE / "figs/deck_tradeoff.png", transparent=False, facecolor="white")
plt.close(fig)

# --- Where attacks succeed ----------------------------------------------------
fam = ["Emoji substitution", "Language translation", "Substitution ciphers", "Information dissemination",
       "Base encoding", "Marketing & advertising", "Entertainment", "Scams & fraud"]
b0 = [10, 8, 5, 3, 1, 1, 1, 1]
b2 = [2, 6, 4, 0, 2, 1, 0, 0]
ours = [0, 1, 1, 0, 0, 0, 0, 0]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.4, 4.4), dpi=220, gridspec_kw={"width_ratios": [2.6, 1]})
h = 0.26
ys = list(range(len(fam)))[::-1]
for off, vals, col, lab in [(h, b0, MUTED, "B0 no defence"), (0, b2, AMBER, "B2 per-chunk PIGuard"),
                            (-h, ours, SAFE, "Ours")]:
    a1.barh([y + off for y in ys], vals, height=h, color=col, label=lab)
a1.set_yticks(ys)
a1.set_yticklabels(fam)
a1.set_xlabel("Successful attacks (of ~20 per family)")
a1.set_title("By attack family (7 other families: 0 for every method)", fontsize=12.5, color=INK, loc="left")
a1.legend(frameon=False, loc="lower right")
a1.grid(axis="x", color=GRID)
a1.set_axisbelow(True)
pos = ["start", "middle", "end"]
x = range(3)
w = 0.26
for off, vals, col in [(-w, [20, 4, 6], MUTED), (0, [10, 3, 2], AMBER), (w, [2, 0, 0], SAFE)]:
    a2.bar([i + off for i in x], vals, width=w, color=col)
a2.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
a2.set_xticks(list(x))
a2.set_xticklabels(pos)
a2.set_ylabel("Successful attacks (of ~100)")
a2.set_title("By insertion position", fontsize=12.5, color=INK, loc="left")
a2.grid(axis="y", color=GRID)
a2.set_axisbelow(True)
fig.tight_layout()
fig.savefig(HERE / "figs/deck_breakdown.png", facecolor="white")
plt.close(fig)
print("wrote deck_tradeoff.png, deck_breakdown.png")
