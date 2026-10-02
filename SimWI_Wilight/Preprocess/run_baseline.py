"""
Baseline arm: the SAME data, windowed WITHOUT the ratio.

    python run_baseline.py --dry-run
    python run_baseline.py --station m1 --activity A
    python run_baseline.py                        # all 60 streams

This is the control for the experiment. The sanitized arm is

    242 -> drop 8 guard -> frequency order -> 234 -> ratio -> ratio -> 58 -> window

and this is

    242 -> drop 8 guard -> frequency order -> 234 ------------------------> window

Everything else is shared, deliberately: the same column map, the same slot
table, the same /814 rescale, the same asymmetric 4-head/5-tail discard, the
same batch_N naming, the same `csi_mon` v7 files, and (via make_csv --seed) the
same 80/20 split. The ONLY difference between the two trees is whether
ratio_stage and temporal_clean ran.

Why the guard drop and the reorder stay in the baseline: those 8 columns are
dead (mean |CSI| 3.9 against 562 overall, neighbour correlation 0.015-0.44), so
feeding them to the baseline would handicap it with 8 channels of noise. Both
arms must see the same subcarriers. The reorder is free — it is a permutation,
and a CNN over a permuted frequency axis is not the same model, so both arms
get the physical ordering.

NO information is discarded relative to the input: all 234 usable subcarriers
are kept at full precision (see config.BASELINE_DTYPE for why complex64 is
exact here).

Afterwards:
    python make_csv.py --root ../../data/SimWi_raw/batches --seed 0
    python ../Model/Proximity/run_grid.py --arm baseline --subcarriers 234 \
           --norm standardize
"""

import argparse
import time

import h5py

import config as C
import sanitize
import window


def expected_counts(src, station):
    """Windows each slot SHOULD contain, from the packet count in the header."""
    with h5py.File(src, "r") as f:
        n_packets = f["csi"].shape[1]
    out = {}
    for name, start, stop in window.slots_for(station):
        lo, hi = window.slot_bounds(n_packets, start, stop)
        out[name] = max(0, (hi - lo) // C.WINDOW_SIZE - 2 * C.DISCARD + 1)
    return n_packets, out


def batches_complete(env, station, activity, src, out_root):
    """
    True only if EVERY slot has EXACTLY the expected number of files.

    Not "the directory exists and has something in it": slots are written in
    order (Train_m1 ... Test_m3), so a job killed while writing the last slot
    would leave all six directories non-empty and that activity would be
    skipped forever on resume — silently producing a short, class-skewed
    test set for one cell and desynchronising the split RNG for every slot
    after it. Counting also catches stale files left by a --force re-run.
    """
    _, expected = expected_counts(src, station)
    for name, want in expected.items():
        d = (out_root / env / C.BW / C.NUM_MON / station
             / "Slots" / name / f"{activity}_batch")
        if not d.is_dir():
            return False
        if sum(1 for _ in d.glob("batch_*.mat")) != want:
            return False
    return True


def print_plan(src, station):
    """Dry-run: the slot layout, from the packet count in the header."""
    n_packets, expected = expected_counts(src, station)
    print(f"      {n_packets:,} packets")
    for name, n_win in expected.items():
        print(f"      [dry-run] {name:<9} -> {n_win:>6,} windows")


def process_one(env, station, activity, keep_cols, reorder, args):
    src = C.DATA_IN / env / C.BW / C.NUM_MON / station / activity / f"{activity}.mat"
    tag = f"{env}/{station}/{activity}"

    if not src.exists():
        print(f"   {tag}: !! missing {src}")
        return
    if args.dry_run:
        print(f"   {tag}: would process {src.name}")
        print_plan(src, station)
        return

    if batches_complete(env, station, activity, src, C.BASELINE_BATCHES) \
            and not args.force:
        print(f"   {tag}: complete, skipping")
        return

    t0 = time.time()
    print(f"   {tag}: loading {src.name}")

    # Same reader, same column map as the sanitized arm — then STOP.
    # No ratio_stage, no temporal_clean.
    stream = sanitize.load_csi(src, keep_cols, reorder, dtype=C.BASELINE_DTYPE)
    t_load = time.time() - t0
    print(f"      loaded {stream.shape}  ({stream.nbytes / 1e9:.2f} GB, {stream.dtype})")

    t1 = time.time()
    counts = window.write_batches(stream, station, env, activity,
                                  out_root=C.BASELINE_BATCHES, compress=False)
    del stream

    total = sum(counts.values())
    print(f"      load {t_load:5.1f}s | window {time.time()-t1:5.1f}s | "
          f"{total:,} files across {len(counts)} slots")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--station",  action="append", choices=C.STATIONS)
    p.add_argument("--activity", action="append", choices=C.ACTIVITIES)
    p.add_argument("--env",      action="append", choices=C.ENVS)
    p.add_argument("--force",    action="store_true")
    p.add_argument("--dry-run",  action="store_true")
    args = p.parse_args()

    envs       = args.env      or C.ENVS
    stations   = args.station  or C.STATIONS
    activities = args.activity or C.ACTIVITIES

    keep_cols, reorder, subcarriers = sanitize.build_column_map()
    n = len(keep_cols)

    print("=" * 72)
    print("  BASELINE arm — no ratio, full 234 subcarriers")
    print("=" * 72)
    print(f"  in      : {C.DATA_IN}")
    print(f"  batches : {C.BASELINE_BATCHES}")
    print(f"  test    : {C.TEST}")
    print(f"  dtype   : {C.BASELINE_DTYPE}  (lossless: raw CSI is integer-valued, |v| <= 2047)")
    print(f"  columns : 242 -> {n}   (8 dead guard columns dropped, frequency-ordered)")
    print(f"  kept subcarriers: {subcarriers[0]}..{subcarriers[n//2-1]}, "
          f"{subcarriers[n//2]}..{subcarriers[-1]}")
    print(f"  >> NoOfSubcarrier for the grid  =  {n}")
    print(f"  scope   : {len(envs)} env x {len(stations)} sta x {len(activities)} act "
          f"= {len(envs)*len(stations)*len(activities)} streams")
    print("=" * 72)

    t_start = time.time()
    for env in envs:
        for station in stations:
            print(f"\n-- {env} / {station}")
            for activity in activities:
                process_one(env, station, activity, keep_cols, reorder, args)

    print(f"\ndone in {(time.time() - t_start) / 60:.1f} min")


if __name__ == "__main__":
    main()
