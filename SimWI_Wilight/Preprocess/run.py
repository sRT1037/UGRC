"""
Driver: SiMWiSense .mat  ->  Wilight-sanitized  ->  windowed batch tree.

    python run.py --dry-run              # plan only, touch nothing
    python run.py --station m1 --activity A
    python run.py                        # all 60 streams

One pass per (station, activity). The sanitized stream is handed straight to
window.py in memory and never hits disk:

    A.mat (N, 242)  ->  sanitize  ->  (N, 58)  ->  window  ->  batch_*.mat

Set config.SAVE_INTERIM = True to also dump the full sanitized stream as .npz,
for inspection or plotting.

Resumable: an activity whose batch folders already exist is skipped, so the run
can be interrupted and restarted. Use --force to redo.

After this, generate manifests with SiMWiSense's own create_csv.py / csv_main.py
pointed at config.BATCHES, then train with NoOfSubcarrier = 58.
"""

import argparse
import time

import h5py
import numpy as np

import config as C
import sanitize
import window


def batches_exist(env, station, activity):
    """True if every slot for this activity already has batch files on disk."""
    for name, _, _ in window.slots_for(station):
        d = (C.BATCHES / env / C.BW / C.NUM_MON / station
             / "Slots" / name / f"{activity}_batch")
        if not d.is_dir() or not any(d.glob("batch_*.mat")):
            return False
    return True


def print_plan(src, station):
    """Dry-run: show the slot layout using the packet count from the header."""
    with h5py.File(src, "r") as f:
        n_packets = f["csi"].shape[1]
    print(f"      {n_packets:,} packets")
    for name, start, stop in window.slots_for(station):
        lo, hi = window.slot_bounds(n_packets, start, stop)
        n_win = max(0, (hi - lo) // C.WINDOW_SIZE - 2 * C.DISCARD + 1)
        print(f"      [dry-run] {name:<9} packets {lo:>9,}..{hi:<9,} -> {n_win:>6,} windows")


def process_one(env, station, activity, keep_cols, reorder, args):
    src = C.DATA_IN / env / C.BW / C.NUM_MON / station / activity / f"{activity}.mat"
    tag = f"{env}/{station}/{activity}"

    if not src.exists():
        print(f"   {tag}: !! missing {src}")
        return

    if batches_exist(env, station, activity) and not args.force:
        print(f"   {tag}: batches present, skipping")
        return

    if args.dry_run:
        print(f"   {tag}: would process {src.name}")
        print_plan(src, station)
        return

    t0 = time.time()

    # ── load + sanitize ───────────────────────────────────────────────────
    # load_and_sanitize, not load_csi + sanitize_stream: it keeps the sole
    # reference to the full-size input so it can be freed after the first
    # ratio instead of being pinned through the whole chain.
    print(f"   {tag}: loading {src.name}")
    stream = sanitize.load_and_sanitize(src, keep_cols, reorder)
    t_san = time.time() - t0

    # ── optional interim dump ─────────────────────────────────────────────
    if C.SAVE_INTERIM:
        npz = C.INTERIM / env / station / f"{activity}.npz"
        npz.parent.mkdir(parents=True, exist_ok=True)
        # savez, not savez_compressed: ratio outputs are float mantissas and
        # do not compress, so zlib would cost minutes for nothing.
        np.savez(npz, csi=stream)
        print(f"      interim -> {npz.name}")

    # ── window straight out of memory ─────────────────────────────────────
    t1 = time.time()
    counts = window.write_batches(stream, station, env, activity)
    del stream

    total = sum(counts.values())
    print(f"      sanitize {t_san:5.1f}s | window {time.time()-t1:5.1f}s | "
          f"{total:,} files across {len(counts)} slots")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--station",  action="append", choices=C.STATIONS,
                   help="limit to these stations (repeatable)")
    p.add_argument("--activity", action="append",
                   help="limit to these activity letters (repeatable)")
    p.add_argument("--env",      action="append", choices=C.ENVS)
    p.add_argument("--force",    action="store_true", help="redo work already on disk")
    p.add_argument("--dry-run",  action="store_true", help="print the plan, write nothing")
    args = p.parse_args()

    envs       = args.env      or C.ENVS
    stations   = args.station  or C.STATIONS
    activities = args.activity or C.ACTIVITIES

    keep_cols, reorder, subcarriers = sanitize.build_column_map()

    n_in  = len(keep_cols)
    n_mid = n_in // 2
    n_out = n_mid if C.SINGLE_RATIO_ONLY else n_mid // 2

    print("=" * 72)
    print("  SiMWiSense + Wilight preprocessing")
    print("=" * 72)
    print(f"  in      : {C.DATA_IN}")
    print(f"  batches : {C.BATCHES}")
    print(f"  interim : {C.INTERIM if C.SAVE_INTERIM else '(not saved)'}")
    print(f"  test    : {C.TEST}")
    print(f"  dtype   : {C.DTYPE}")
    print(f"  columns : 242 -> {n_in} -> {n_mid}"
          f"{'' if C.SINGLE_RATIO_ONLY else f' -> {n_out}'}"
          f"   (drop_pilots={C.DROP_PILOTS}, single_ratio_only={C.SINGLE_RATIO_ONLY})")
    print(f"  kept subcarriers: {subcarriers[0]}..{subcarriers[n_in//2-1]}, "
          f"{subcarriers[n_in//2]}..{subcarriers[-1]}")
    print(f"  >> NoOfSubcarrier for main.py / baseline_*.py  =  {n_out}")
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
