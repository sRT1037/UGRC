"""
Run the 9-cell proximity grid and assemble the result table.

    python run_grid.py --arm sanitized --subcarriers 58 --center
    python run_grid.py --arm sanitized --subcarriers 58 --cells diagonal

The grid is (recorder x subject). The result is the diagonal-vs-off-diagonal
gap: a monitor should classify its OWN nearby subject well and the other two
badly. That gap is the proximity finding.

    --cells diagonal   3 runs  (m1/m1, m2/m2, m3/m3) — the cheap first look
    --cells all        9 runs

Each cell shells out to train.py so one crash cannot take down the grid, and
so cells can be resumed: a cell whose Results/runs/<tag>.json already exists is
skipped unless --force.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # SimWI_Wilight/Model/Proximity
RESULTS = HERE.parents[1] / "Results"           # SimWI_Wilight/Results
STATIONS = ["m1", "m2", "m3"]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", default="sanitized")
    p.add_argument("--root", default=None)
    p.add_argument("--env", default="Classroom")
    p.add_argument("--subcarriers", type=int, required=True)
    p.add_argument("--norm", choices=["none","center","standardize"], default="none")
    p.add_argument("--cells", choices=["all", "diagonal"], default="all")
    p.add_argument("--epochs", type=int, default=15)
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    cells = ([(s, s) for s in STATIONS] if args.cells == "diagonal"
             else [(s, j) for s in STATIONS for j in STATIONS])

    suffix = f"{args.arm}_{args.subcarriers}sc_{args.norm}"
    print(f"grid: {suffix} | {len(cells)} cells | env {args.env}")

    t0 = time.time()
    for station, subject in cells:
        tag = f"{suffix}_{args.env}_{station}_{subject}"
        if (RESULTS / "runs" / f"{tag}.json").exists() and not args.force:
            print(f"  {tag}: done, skipping")
            continue

        cmd = [sys.executable, str(HERE / "train.py"),
               "--arm", args.arm, "--env", args.env,
               "--station", station, "--subject", subject,
               "--subcarriers", str(args.subcarriers),
               "--epochs", str(args.epochs)]
        cmd += ["--norm", args.norm]
        if args.root:
            cmd += ["--root", args.root]

        print(f"\n>>> {station} recording subject {subject}")
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"  !! {tag} FAILED (exit {r.returncode}) — continuing")

    print(f"\ngrid finished in {(time.time()-t0)/60:.1f} min")

    # plots + the 3x3 table live in report.py so they can be rebuilt from the
    # JSONs at any time without retraining
    rep = [sys.executable, str(HERE / "report.py"),
           "--arm", args.arm, "--subcarriers", str(args.subcarriers),
           "--env", args.env]
    rep += ["--norm", args.norm]
    subprocess.run(rep)


if __name__ == "__main__":
    main()
