"""
Wilight's ratio sanitization, adapted to SiMWiSense's already-pruned .mat files.

Chain:
    (N, 242)  ->  column map  ->  (N, 234)  ->  single ratio  ->  (N, 117)
              ->  double ratio  ->  (N, 58)  ->  temporal clean  ->  (N, 58)

Two things differ from running Wilight as-is, both because SiMWiSense's
extractor never applies an fftshift and already removed 14 subcarriers:

  1. The column map is DERIVED from subcarrier numbers, not copied from
     Wilight's hardcoded index list. Wilight's indices are in fftshifted
     coordinates, where index 0 means subcarrier -128; here index 0 means
     subcarrier 0. Copying the list literally would delete real data and keep
     the dead guard band.

  2. The same map also REORDERS columns into physical frequency order. The
     ratio divides adjacent columns and Savitzky-Golay smooths across the
     frequency axis; on the raw array, columns 116 and 117 are subcarriers
     +122 and -122, i.e. opposite ends of the band.

ratio_stage() and temporal_clean() are Wilight's own implementations, copied
verbatim from Single_antenna_single_file_processing.py so the numerics match.
"""

import gc

import numpy as np
import h5py
from scipy.signal import savgol_filter as _savgol

import config as C


# ══════════════════════  column map  ══════════════════════════════════════════

def subcarrier_of(orig_index: int) -> int:
    """Original 256-FFT index -> subcarrier number, for a NON-fftshifted array."""
    return orig_index if orig_index < C.FFT_SIZE // 2 else orig_index - C.FFT_SIZE


def build_column_map():
    """
    Work out, from first principles, which of the 242 columns to keep and in
    what order.

    Returns
    -------
    keep_cols   : ndarray[int]  column indices into the 242, ASCENDING.
                                Safe for h5py fancy indexing.
    reorder     : ndarray[int]  permutation applied AFTER selecting keep_cols,
                                putting columns into ascending subcarrier order.
    subcarriers : ndarray[int]  the final subcarrier number of each output
                                column, ascending. For sanity checks and plots.
    """
    # Column c of the .mat corresponds to this original 256-FFT index.
    orig_of_col = [i for i in range(C.FFT_SIZE) if i not in C.SIMWI_REMOVED]
    assert len(orig_of_col) == 242, f"expected 242 columns, got {len(orig_of_col)}"

    drop = set(C.GUARD_SUBCARRIERS)
    if C.DROP_PILOTS:
        drop |= C.PILOT_SUBCARRIERS

    keep_cols, keep_sc = [], []
    for col, orig in enumerate(orig_of_col):
        sc = subcarrier_of(orig)
        if sc not in drop:
            keep_cols.append(col)
            keep_sc.append(sc)

    keep_cols = np.asarray(keep_cols, dtype=int)     # already ascending
    keep_sc   = np.asarray(keep_sc, dtype=int)

    reorder = np.argsort(keep_sc)                    # -122..-6 then +6..+122
    return keep_cols, reorder, keep_sc[reorder]


# ══════════════════════  loading  ═════════════════════════════════════════════

def load_csi(mat_path, keep_cols, reorder, packet_limit=None,
             block=None, dtype=None):
    """
    Read a SiMWiSense v7.3 .mat into (N_packets, 234) complex, already pruned
    and already in ascending-subcarrier order.

    MATLAB stores column-major, so h5py reports the dataset as (242, N) with a
    compound {real, imag} dtype, gzip-compressed (~3.4x). The decompressed
    array for the largest activity is 4.5 GB, so the read is BLOCKED:

      * `src_cols` folds the keep-mask and the frequency reorder into a single
        index, so each block is written straight into its final position and
        no permuted second copy is ever materialised.
      * only one block (~390 MB) is transient; the output is allocated once.

    Peak is therefore output + one block, not 2x output.

    packet_limit  : read only the first N packets (testing / quick checks).
    """
    src_cols = np.asarray(keep_cols)[reorder]     # source column per output column
    block    = block or C.BLOCK_PACKETS
    dtype    = dtype or C.DTYPE

    with h5py.File(mat_path, "r") as f:
        ds = f["csi"]
        n_sub, n_pkt = ds.shape
        if n_sub != 242:
            raise ValueError(
                f"{mat_path}: expected 242 subcarriers (the output of "
                f"CSI_extractor_SimWiSense.m), got {n_sub}")
        if packet_limit is not None:
            n_pkt = min(n_pkt, packet_limit)

        out = np.empty((n_pkt, len(src_cols)), dtype=dtype)

        for i0 in range(0, n_pkt, block):
            i1  = min(i0 + block, n_pkt)
            blk = ds[:, i0:i1]                     # (242, b) contiguous
            out.real[i0:i1] = blk["real"][src_cols].T
            out.imag[i0:i1] = blk["imag"][src_cols].T
            del blk                                # freed before the next read

    return out


# ══════════════════════  spatial stage  ═══════════════════════════════════════
# Verbatim from Wilight: Single_antenna_single_file_processing.py:110-192

def ratio_stage(data_2d, threshold, vote_packets, vote_fraction,
                clip_mult, sg_window, sg_poly):
    """
    One ratio stage: (n_packets, N) complex -> (n_packets, N//2) complex.
    Spatial cleaning only: A. Vote  B. Interpolate  C. Clip  D. Savitzky-Golay
    """
    n_packets, N = data_2d.shape
    n_pair       = N // 2
    check_upto   = min(vote_packets, n_packets)
    x            = np.arange(n_pair, dtype=float)

    # ── Compute all ratios in one shot ────────────────────────────────────
    num = data_2d[:, 0::2][:, :n_pair]
    den = data_2d[:, 1::2][:, :n_pair]
    nz  = den != 0
    raw_all = np.where(nz, num / np.where(nz, den, 1 + 0j), np.nan + 0j)

    # A. Vote — vectorised over all check_upto packets at once ────────────
    subset  = raw_all[:check_upto]
    valid_m = np.isfinite(subset.real)
    phase   = np.unwrap(np.angle(np.where(valid_m, subset, 1 + 0j)), axis=1)
    phase[~valid_m] = np.nan

    row_valid = valid_m.sum(axis=1)
    row_avg   = np.where(valid_m, np.abs(phase), 0.0).sum(axis=1) / row_valid.clip(1)

    bad_m = valid_m & (np.abs(phase) > threshold * row_avg[:, None])
    bad_m[row_valid == 0] = False
    bad_count = bad_m.sum(axis=0)
    del subset, valid_m, phase, bad_m

    min_votes     = int(np.ceil(vote_fraction * check_upto))
    confirmed_bad = np.where(bad_count >= min_votes)[0]

    # B. Set confirmed_bad to NaN (all packets at once) ───────────────────
    result = raw_all.copy()
    result[:, confirmed_bad] = np.nan

    # Interpolate confirmed_bad positions — weights are the same for every
    # row, so compute once and fill all rows with a vectorised column op.
    if len(confirmed_bad) > 0:
        valid_idx = np.where(~np.isin(np.arange(n_pair), confirmed_bad))[0]
        if len(valid_idx) > 0:
            for bad_j in confirmed_bad:
                left  = valid_idx[valid_idx < bad_j]
                right = valid_idx[valid_idx > bad_j]
                if len(left) == 0:
                    result[:, bad_j] = result[:, right[0]]
                elif len(right) == 0:
                    result[:, bad_j] = result[:, left[-1]]
                else:
                    lx, rx = int(left[-1]), int(right[0])
                    alpha  = float(bad_j - lx) / (rx - lx)
                    result[:, bad_j] = (1.0 - alpha) * result[:, lx] + alpha * result[:, rx]

    # Handle any residual per-row NaNs (e.g. from den==0 subcarriers)
    still_nan = ~np.isfinite(result.real).all(axis=1)
    for p in np.where(still_nan)[0]:
        z     = result[p]; valid = np.isfinite(z.real)
        if valid.sum() == 0:
            result[p] = 0
        elif not valid.all():
            result[p] = (np.interp(x, x[valid], z.real[valid]) +
                         1j * np.interp(x, x[valid], z.imag[valid]))

    # C. Clip — vectorised: compute per-row median and cap in one pass ────
    mags = np.abs(result)
    med  = np.median(mags, axis=1, keepdims=True)
    cap  = np.where(med != 0, clip_mult * med, np.inf)   # inf -> no clip when med==0
    bad_clip = mags > cap
    if bad_clip.any():
        scale  = np.where(bad_clip, cap / np.maximum(mags, 1e-300), 1.0)
        result = result * scale
    del mags, med, cap, bad_clip

    # D. Savitzky-Golay — one call on the full 2-D array along axis=1 ─────
    w = sg_window if sg_window % 2 == 1 else sg_window - 1
    w = min(w, n_pair if n_pair % 2 == 1 else n_pair - 1)
    if w > sg_poly and w >= 3:
        result = (_savgol(result.real, w, sg_poly, axis=1).astype(float) +
                  1j * _savgol(result.imag, w, sg_poly, axis=1).astype(float))

    return result, confirmed_bad, bad_count, min_votes


# ══════════════════════  temporal cleaning  ═══════════════════════════════════
# Verbatim from Wilight: Single_antenna_single_file_processing.py:197-232

def temporal_clean(dr, t_clip_mult):
    """
    Temporal outlier removal along the packet (time) axis.

    E. For each ratio-group column j:
       - flag packets where |dr[:,j]| > t_clip_mult * median(|dr[:,j]|)
       - set to NaN, interpolate on Re+Im along axis=0

    No temporal smoothing — Wilight defers that to a post-Doppler 2-D Gaussian,
    and we drop the Doppler stage, so this is the last step.
    """
    n_packets, n_groups = dr.shape
    t = np.arange(n_packets, dtype=float)
    out = dr.copy()

    mags     = np.abs(out)
    col_med  = np.median(mags, axis=0, keepdims=True)
    col_med  = np.where(col_med == 0, 1.0, col_med)
    bad_mask = mags > t_clip_mult * col_med
    del mags

    out[bad_mask] = np.nan

    for j in np.where(bad_mask.any(axis=0))[0]:
        col   = out[:, j]
        valid = np.isfinite(col.real)
        if valid.sum() == 0:
            out[:, j] = 0
        elif not valid.all():
            out[:, j] = (np.interp(t, t[valid], col.real[valid]) +
                         1j * np.interp(t, t[valid], col.imag[valid]))

    return out, int(bad_mask.sum())


# ══════════════════════  the full chain  ══════════════════════════════════════

def _chain(box, verbose=True):
    """
    Run the full sanitization on the single array held in `box`.

    The array is passed inside a one-element list, and popped out, so that this
    function holds the ONLY reference to it. That is what makes the `del` below
    actually free the memory — Wilight does the same thing (`del data;
    gc.collect()` at :342), but it only works if no caller is still holding on.
    A plain `f(csi)` would keep the caller's reference alive for the whole
    chain, pinning ~4.3 GB through stages that no longer need it.

    (N, 234) -> single ratio -> (N, 117) -> double ratio -> (N, 58)
             -> temporal clean -> (N, 58)
    """
    def log(msg):
        if verbose:
            print(f"      {msg}")

    csi = box.pop()                      # box is now empty; we hold the only ref

    single, bad_s, _, _ = ratio_stage(
        csi, C.THRESHOLD, C.VOTE_PACKETS, C.VOTE_FRACTION,
        C.CLIP_MULT, C.SG_WINDOW, C.SG_POLY)
    del csi                              # actually frees now
    gc.collect()
    log(f"single ratio -> {single.shape}   voted bad: {len(bad_s)}")

    if C.SINGLE_RATIO_ONLY:
        out, n_flagged = temporal_clean(single, C.T_CLIP_MULT)
        log(f"temporal clean -> {out.shape}   flagged: {n_flagged:,}")
        return out

    double, bad_d, _, _ = ratio_stage(
        single, C.THRESHOLD, C.VOTE_PACKETS, C.VOTE_FRACTION,
        C.CLIP_MULT, C.SG_WINDOW, C.SG_POLY)
    del single
    gc.collect()
    log(f"double ratio -> {double.shape}   voted bad: {len(bad_d)}")

    out, n_flagged = temporal_clean(double, C.T_CLIP_MULT)
    del double
    log(f"temporal clean -> {out.shape}   flagged: {n_flagged:,}")
    return out


def load_and_sanitize(mat_path, keep_cols, reorder, verbose=True):
    """
    Preferred entry point: read a .mat and sanitize it, without the caller ever
    holding a reference to the full-size input array.

    Equivalent to  sanitize_stream(load_csi(...))  but with a lower peak.
    """
    csi = load_csi(mat_path, keep_cols, reorder)
    if verbose:
        print(f"      loaded {csi.shape}  ({csi.nbytes / 1e9:.2f} GB, {csi.dtype})")
    box = [csi]
    del csi                              # hand ownership to the box
    return _chain(box, verbose)


def sanitize_stream(csi, verbose=True):
    """
    Sanitize an in-memory array. Convenience for tests and notebooks.

    NOTE: the caller's own reference keeps the input alive for the whole chain,
    so peak memory is higher than load_and_sanitize(). Prefer that in run.py.
    """
    return _chain([csi], verbose)
