"""
csi2batches_SimWiSense.m reimplemented in Python.

Slices a sanitized per-activity stream into named Train/Test slots, chops each
slot into non-overlapping 50-packet windows, and writes one .mat per window.

Faithful to the MATLAB original, including its quirks, so that a sanitized run
is comparable against the unsanitized baseline window-for-window:

  * the same start/stop slot tables
  * the same  a = len(csi) / 814  proportional rescale
  * the same asymmetric discard (4 windows dropped at the head, 5 at the tail —
    the loop runs i = 5 .. num_image-5 but slices (i-1)*50)
  * the same batch_N.mat naming, starting at 0
  * the same 'csi_mon' variable name

One deliberate fix: MATLAB's  csi(a*start : a*stop, :)  throws on a fractional
subscript, and a = N/814 is essentially never an integer. We floor it.
"""

import numpy as np
import scipy.io as spio

import config as C


# ══════════════════════  slot tables  ═════════════════════════════════════════
# csi2batches_SimWiSense.m:29-45  and  csi2batches_SimWiSense_fine_grained.m:29-40
#
# Positions are on a nominal 814-unit timeline shared by all three stations,
# which record the same session simultaneously. For proximity the timeline is
# three blocks — subject near m1, then m2, then m3 — each split Train/Test.

PROXIMITY_SLOTS = [
    ("Train_m1",   5, 180),
    ("Test_m1",  180, 240),
    ("Train_m2", 245, 425),
    ("Test_m2",  427, 485),
    ("Train_m3", 490, 670),
    ("Test_m3",  672, 730),
]

# fine_grained uses only the block belonging to the station being processed.
FINE_GRAINED_SLOTS = {
    "m1": [("Train",   5, 180), ("Test", 180, 240)],
    "m2": [("Train", 245, 425), ("Test", 427, 485)],
    "m3": [("Train", 490, 670), ("Test", 672, 730)],
}


def slots_for(station):
    """The (name, start, stop) list this station should emit."""
    if C.TEST == "proximity":
        # Every station produces all six slots: its own recording of each of
        # the three subjects. That cross-product is the proximity experiment.
        return PROXIMITY_SLOTS
    elif C.TEST == "fine_grained":
        return FINE_GRAINED_SLOTS[station]
    raise ValueError(f"unknown TEST: {C.TEST!r}")


# ══════════════════════  windowing  ═══════════════════════════════════════════

def slot_bounds(n_packets, start, stop):
    """
    MATLAB:
        a            = abs(length(csi)/814)
        packet_start = a*start
        packet_stop  = a*stop
        csi_slot     = csi(packet_start:packet_stop, :)

    MATLAB's range is 1-based and inclusive, so index p there is p-1 here.
    """
    a = n_packets / C.SLOT_SCALE
    lo = int(np.floor(a * start))
    hi = int(np.floor(a * stop))
    lo = max(lo - 1, 0)                       # 1-based -> 0-based
    hi = min(hi, n_packets)                   # inclusive end -> exclusive
    return lo, hi


def iter_windows(slot):
    """
    Yield (batch_index, window) for one slot.

    MATLAB:
        num_image = floor(num_p/window)
        for i = discard : num_image-discard        % inclusive both ends
            csi_mon = csi_slot((i-1)*window+1 : i*window, :)
            save batch_(i-discard).mat

    Note the asymmetry: i starts at 5 but the slice starts at (i-1)*50, so the
    first window emitted is packets 200..249 — 4 windows skipped at the head,
    5 at the tail. Preserved deliberately.
    """
    W, D = C.WINDOW_SIZE, C.DISCARD
    num_image = len(slot) // W

    for i in range(D, num_image - D + 1):
        yield i - D, slot[(i - 1) * W: i * W]


def write_batches(stream, station, env, activity, dry_run=False):
    """
    Slice one sanitized activity stream into every slot, window it, and write
    the .mat files. Returns {slot_name: n_windows_written}.

    Output layout mirrors SiMWiSense's Data/ exactly, so create_csv.py and
    main.py / baseline_proximity.py can run against it unmodified:
        <BATCHES>/<Env>/<BW>/<num_mon>/<station>/Slots/<slot>/<letter>_batch/
    """
    counts = {}
    n_packets = len(stream)

    for name, start, stop in slots_for(station):
        lo, hi = slot_bounds(n_packets, start, stop)
        slot = stream[lo:hi]

        out_dir = (C.BATCHES / env / C.BW / C.NUM_MON / station
                   / "Slots" / name / f"{activity}_batch")
        if not dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)

        n = 0
        for idx, win in iter_windows(slot):
            if not dry_run:
                # v7 (not v7.3) — dataGenerator.read_mat uses scipy.io.loadmat,
                # which cannot read v7.3. Variable must be named 'csi_mon'.
                spio.savemat(out_dir / f"batch_{idx}.mat",
                             {"csi_mon": win}, do_compression=True)
            n += 1

        counts[name] = n

    return counts
