"""
Generate train/val/test CSV manifests for the sanitized batch tree.

Reuses SiMWiSense's OWN generate_train_val_csv / generate_test_csv unmodified —
only the tree walk is ours, because create_csv.process_data hardcodes
`data_pa = f"../Data/{Test}"` and both environments.

    python make_csv.py                 # all stations, all slots
    python make_csv.py --root <path>   # e.g. the raw 242 baseline tree

Writes, into each slot directory:
    Train_m*/  ->  train_set.csv  +  val_set.csv   (80/20 coin flip per file)
    Test_m*/   ->  test_set.csv                    (every file)

Rows are `filename,label`, e.g. `A_batch/batch_0.mat,A`, relative to the slot
directory — which is what main.py / baseline_proximity.py pass as their data dir.

DEVIATION FROM UPSTREAM: the original never seeds numpy, so the 80/20 split is
different on every run. We seed it, so that the sanitized and baseline arms can
be given the same split and the comparison isn't confounded by it. Pass
--seed -1 to restore the unseeded behaviour.
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np

import config as C

SIMWI_PY = C.REPO_ROOT / "resources" / "SiMWiSense" / "Python_Code"
sys.path.insert(0, str(SIMWI_PY))
from create_csv import generate_train_val_csv, generate_test_csv   # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=None,
                   help="batch tree root (default: config.BATCHES)")
    p.add_argument("--seed", type=int, default=0,
                   help="numpy seed for the 80/20 split; -1 = unseeded (upstream behaviour)")
    args = p.parse_args()

    root = Path(args.root) if args.root else C.BATCHES
    if args.seed >= 0:
        np.random.seed(args.seed)

    print("=" * 72)
    print("  CSV manifests")
    print("=" * 72)
    print(f"  root : {root}")
    print(f"  seed : {args.seed if args.seed >= 0 else 'unseeded'}")
    print(f"  using: {SIMWI_PY / 'create_csv.py'}")
    print("=" * 72)

    t0 = time.time()
    for env in C.ENVS:
        for station in C.STATIONS:
            slots_dir = root / env / C.BW / C.NUM_MON / station / "Slots"
            if not slots_dir.is_dir():
                print(f"  !! missing {slots_dir}")
                continue

            print(f"\n-- {env} / {station}")
            for slot in sorted(d.name for d in slots_dir.iterdir() if d.is_dir()):
                sd = slots_dir / slot
                t1 = time.time()

                if slot.startswith("Train"):
                    generate_train_val_csv(str(sd), slot)
                    tr = sum(1 for _ in open(sd / "train_set.csv")) - 1
                    va = sum(1 for _ in open(sd / "val_set.csv")) - 1
                    print(f"   {slot:<9} train {tr:>7,}  val {va:>6,}   "
                          f"({tr/(tr+va)*100:.1f}% / {va/(tr+va)*100:.1f}%)  {time.time()-t1:.1f}s")
                else:
                    generate_test_csv(str(sd))
                    te = sum(1 for _ in open(sd / "test_set.csv")) - 1
                    print(f"   {slot:<9} test  {te:>7,}                      "
                          f"{time.time()-t1:.1f}s")

    print(f"\ndone in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
