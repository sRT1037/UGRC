"""
Build all plots from the per-cell JSONs in Results/runs/.

    python report.py --arm sanitized --subcarriers 58

Reads only JSON, never retrains, so plots can be regenerated freely.

Outputs, under Results/Proximity/<suffix>/<env>/:

    m1/cm_m1_m1.png          20x20 confusion matrix, one per cell
    m1/cm_m1_m2.png
    m1/cm_m1_m3.png
    m1/summary_m1.png        all three side by side, shared colour scale
    ... same for m2, m3
    accuracy_grid.png        the 3x3 recorder-vs-subject accuracy matrix
    accuracy_grid.csv

Confusion matrices are row-normalised ("of everything that WAS activity X,
what fraction was predicted as Y"), so the diagonal is per-class recall and
every row sums to 1. Colour only, no printed numbers: at 20x20 the numbers are
unreadable and the pattern is the point. White = 0, deep blue = 1.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")                      # headless: no display on the Mac over SSH
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "Results"
RUNS = RESULTS / "runs"
STATIONS = ["m1", "m2", "m3"]
LABELS = list("ABCDEFGHIJKLMNOPQRST")


def load(suffix, env, station, subject):
    f = RUNS / f"{suffix}_{env}_{station}_{subject}.json"
    return json.loads(f.read_text()) if f.exists() else None


def draw_cm(ax, cm, title):
    """One 20x20 heatmap. vmin/vmax fixed at 0..1 so every panel is comparable."""
    im = ax.imshow(cm, cmap="Blues", vmin=0.0, vmax=1.0, interpolation="nearest")
    ax.set_xticks(range(20)); ax.set_xticklabels(LABELS, fontsize=6)
    ax.set_yticks(range(20)); ax.set_yticklabels(LABELS, fontsize=6)
    ax.set_xlabel("predicted", fontsize=8)
    ax.set_ylabel("actual", fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.tick_params(length=2)
    return im


def per_cell_and_per_monitor(suffix, env, outdir):
    for station in STATIONS:
        mdir = outdir / station
        mdir.mkdir(parents=True, exist_ok=True)
        panels = []

        for subject in STATIONS:
            d = load(suffix, env, station, subject)
            if d is None:
                continue
            cm = np.array(d["confusion_matrix"])
            near = " (NEAR)" if station == subject else ""
            title = (f"{station} recording subject {subject}{near}\n"
                     f"accuracy {d['test_accuracy']*100:.1f}%")

            # one figure per cell
            fig, ax = plt.subplots(figsize=(6.2, 5.4))
            im = draw_cm(ax, cm, title)
            fig.colorbar(im, ax=ax, fraction=0.046, label="fraction of actual class")
            fig.tight_layout()
            fig.savefig(mdir / f"cm_{station}_{subject}.png", dpi=200,
                        bbox_inches="tight")
            plt.close(fig)

            panels.append((subject, cm, d["test_accuracy"]))

        # one figure per MONITOR: its three cells side by side
        if panels:
            fig, axes = plt.subplots(1, len(panels), figsize=(5.0 * len(panels), 5.0))
            axes = np.atleast_1d(axes)
            for ax, (subject, cm, acc) in zip(axes, panels):
                near = " (NEAR)" if station == subject else ""
                im = draw_cm(ax, cm, f"subject {subject}{near}\n{acc*100:.1f}%")
            fig.suptitle(f"Monitor {station} — {suffix} — {env}", fontsize=12)
            fig.colorbar(im, ax=axes.tolist(), fraction=0.02,
                         label="fraction of actual class")
            fig.savefig(outdir / station / f"summary_{station}.png",
                        dpi=200, bbox_inches="tight")
            plt.close(fig)
            print(f"  {station}: {len(panels)} cells -> {station}/")


def accuracy_grid(suffix, env, outdir):
    """The 3x3 recorder-vs-subject accuracy matrix. Small, so numbers ARE shown."""
    grid = np.full((3, 3), np.nan)
    for i, station in enumerate(STATIONS):
        for j, subject in enumerate(STATIONS):
            d = load(suffix, env, station, subject)
            if d:
                grid[i, j] = d["test_accuracy"] * 100

    fig, ax = plt.subplots(figsize=(6.2, 5.2))
    im = ax.imshow(grid, cmap="Blues", vmin=0, vmax=100)
    for i in range(3):
        for j in range(3):
            if np.isnan(grid[i, j]):
                ax.text(j, i, "—", ha="center", va="center", color="grey")
                continue
            ax.text(j, i, f"{grid[i,j]:.1f}%", ha="center", va="center",
                    fontsize=13, weight="bold" if i == j else "normal",
                    color="white" if grid[i, j] > 55 else "black")
    ax.set_xticks(range(3)); ax.set_xticklabels([f"subject {s}" for s in STATIONS])
    ax.set_yticks(range(3)); ax.set_yticklabels([f"recorded by {s}" for s in STATIONS])
    ax.set_title(f"Proximity accuracy — {suffix} — {env}\n"
                 f"diagonal = monitor nearest its own subject", fontsize=10)
    fig.colorbar(im, ax=ax, fraction=0.046, label="test accuracy %")
    # bbox_inches="tight", not tight_layout: the long y tick labels
    # ("recorded by m1") sit outside the axes and get clipped otherwise
    fig.savefig(outdir / "accuracy_grid.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    lines = ["recorded_by," + ",".join(f"subject_{s}" for s in STATIONS)]
    for i, station in enumerate(STATIONS):
        lines.append(station + "," + ",".join(
            "" if np.isnan(v) else f"{v:.2f}" for v in grid[i]))
    (outdir / "accuracy_grid.csv").write_text("\n".join(lines) + "\n")

    diag = np.array([grid[i, i] for i in range(3)])
    off = np.array([grid[i, j] for i in range(3) for j in range(3) if i != j])
    diag, off = diag[~np.isnan(diag)], off[~np.isnan(off)]

    print(f"\n{'='*54}\n  {suffix} — {env}\n{'='*54}")
    print(f"  {'recorded by':<16}" + "".join(f"{'subj '+s:>12}" for s in STATIONS))
    for i, station in enumerate(STATIONS):
        print(f"  {station:<16}" + "".join(
            f"{'-':>12}" if np.isnan(grid[i, j]) else f"{grid[i,j]:>11.1f}%"
            for j in range(3)))
    if diag.size:
        print(f"\n  diagonal (near)    : {diag.mean():.1f}%  (n={diag.size})")
    if off.size:
        print(f"  off-diagonal (far) : {off.mean():.1f}%  (n={off.size})")
    if diag.size and off.size:
        print(f"  GAP                : {diag.mean()-off.mean():.1f} points")
    return grid


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", default="sanitized")
    p.add_argument("--subcarriers", type=int, required=True)
    p.add_argument("--norm", choices=["none","center","standardize"], default="none")
    p.add_argument("--env", default="Classroom")
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    suffix = (f"{args.arm}_{args.subcarriers}sc_{args.norm}"
              + (f"_s{args.seed}" if args.seed else ""))
    outdir = RESULTS / "Proximity" / suffix / args.env
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"report: {suffix} -> {outdir}")
    per_cell_and_per_monitor(suffix, args.env, outdir)
    accuracy_grid(suffix, args.env, outdir)
    print(f"\nplots written to {outdir}")


if __name__ == "__main__":
    main()
