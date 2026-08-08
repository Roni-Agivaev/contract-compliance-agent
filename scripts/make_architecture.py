"""Generate static/architecture.png (run once; commit the PNG).

Reproduces the presentation's slide-6 flow. Box labels MUST match the module
names used in the steps trace: Supervisor, Company Law, Employee Law, Editor,
Reflection.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "architecture.png")

INK = "#1a1f36"
BLUE = "#6c8cff"
GREEN = "#2fbf7f"
GREY = "#8b93b0"
CARD = "#ffffff"


def box(ax, x, y, w, h, title, sub="", edge=BLUE, fill=CARD):
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                       linewidth=2, edgecolor=edge, facecolor=fill, mutation_aspect=1)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h * (0.63 if sub else 0.5), title, ha="center", va="center",
            fontsize=12, fontweight="bold", color=INK)
    if sub:
        ax.text(x + w / 2, y + h * 0.27, sub, ha="center", va="center",
                fontsize=8.5, color=GREY)


def arrow(ax, p1, p2, color=INK, style="-|>", ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=15,
                                 linewidth=1.8, color=color, linestyle=ls,
                                 connectionstyle=f"arc3,rad={rad}"))


def lbl(ax, x, y, text, color=INK):
    ax.text(x, y, text, ha="center", va="center", fontsize=8, color=color,
            style="italic", bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none"))


fig, ax = plt.subplots(figsize=(12, 7), dpi=150)
ax.set_xlim(0, 12); ax.set_ylim(0, 7); ax.axis("off")

ax.text(0.3, 6.7, "Contract Compliance Agent — Architecture",
        fontsize=15, fontweight="bold", color=INK)

# ── nodes ──
box(ax, 0.3, 3.15, 1.9, 1.0, "Draft Contract", "text input", edge=GREY)
box(ax, 2.6, 3.05, 2.0, 1.15, "Supervisor", "orchestrates the flow")
box(ax, 5.4, 5.05, 2.7, 1.0, "Company Law", "checks company jurisdiction")
box(ax, 5.4, 3.05, 2.7, 1.0, "Employee Law", "checks employee jurisdiction")
box(ax, 9.1, 5.05, 2.6, 1.0, "Editor", "rewrites flagged clauses")
box(ax, 9.1, 3.05, 2.6, 1.0, "Reflection", "reviews the fixes")
box(ax, 4.9, 0.7, 3.2, 1.05, "Compliant Contract", "+ list of what changed & why",
    edge=GREEN)

# ── RUN IN PARALLEL note (empty gap between the two law boxes) ──
ax.text(6.75, 4.55, "RUN IN PARALLEL", ha="center", fontsize=8.5,
        color=BLUE, fontweight="bold")

# ── flow arrows ──
arrow(ax, (2.2, 3.65), (2.6, 3.65)); lbl(ax, 2.4, 3.9, "draft")

# supervisor -> law agents (forward)
arrow(ax, (4.6, 3.95), (5.4, 5.4), rad=0.12)
arrow(ax, (4.6, 3.6), (5.4, 3.55), rad=0.0)
lbl(ax, 5.0, 4.35, "draft")

# law agents -> supervisor (issues, dashed green)
arrow(ax, (5.4, 5.15), (4.6, 4.1), color=GREEN, ls="--", rad=0.12)
arrow(ax, (5.4, 3.25), (4.6, 3.35), color=GREEN, ls="--", rad=-0.12)
lbl(ax, 5.05, 3.0, "issues", color=GREEN)

# supervisor -> editor (contract + issues), curve up and over the top
arrow(ax, (4.4, 4.25), (9.3, 6.05), rad=-0.42)
lbl(ax, 6.9, 6.6, "contract + issues")

# editor <-> reflection loop
arrow(ax, (10.1, 5.05), (10.1, 4.05))
arrow(ax, (10.6, 4.05), (10.6, 5.05), color=GREEN)
lbl(ax, 9.55, 4.55, "revise")
lbl(ax, 11.15, 4.55, "≤ N iters", color=GREEN)

# reflection -> supervisor: OUTER re-audit loop over the corrected contract
arrow(ax, (9.1, 3.4), (4.6, 3.15), color=GREEN, rad=0.32)
lbl(ax, 6.9, 2.42, "corrected contract — re-audit, ≤ 3 passes", color=GREEN)
# supervisor -> compliant contract (only once no breaches remain)
arrow(ax, (3.4, 3.05), (5.6, 1.75), color=GREEN, rad=0.05)
lbl(ax, 3.9, 2.2, "0 breaches", color=GREEN)

# ── data-store legend (empty bottom-left) ──
ax.text(0.3, 1.75, "Data stores", fontsize=9, fontweight="bold", color=INK)
ax.text(0.3, 1.42, "• Pinecone (RAG): US · UK · DE · IL · ILO", fontsize=8.5, color=GREY)
ax.text(0.3, 1.14, "• Supabase: 2026 minimum-wage table", fontsize=8.5, color=GREY)
ax.text(0.3, 0.86, "• LLM: MB5R2CF-azure/gpt-5.4-mini", fontsize=8.5, color=GREY)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"wrote {OUT}")
