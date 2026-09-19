"""
Paths and constants for the SiMWiSense + Wilight merged preprocessing pipeline.

Everything that might need changing lives here. Nothing else in Preprocess/
hardcodes a path or a magic number.
"""

from pathlib import Path

# ── Repo layout ───────────────────────────────────────────────────────────────
# config.py lives at  UGRC/SimWI_Wilight/Preprocess/config.py
REPO_ROOT = Path(__file__).resolve().parents[2]

# Input: the downloaded SiMWiSense .mat tree (already 242 subcarriers, v7.3)
#   data/SimWi/<Env>/<BW>/<num_mon>/<station>/<letter>/<letter>.mat
DATA_IN = REPO_ROOT / "data" / "SimWi"

# Output root. Lives under data/ so it inherits the .gitignore rule.
DATA_OUT = REPO_ROOT / "data" / "SimWi_Wilight"

# Optional sanitized full-length streams, one .npz per (station, activity).
#
# OFF by default: the sanitized stream is handed straight to window.py in
# memory, so nothing intermediate touches disk. Writing it would cost ~38 GB
# (complex128) and ~14 min of zlib for near-zero compression, since ratio
# outputs are float mantissas rather than the int16-derived input.
#
# It is not needed as insurance against re-windowing either: fine_grained's
# Train/Test bounds are IDENTICAL to proximity's Train_m<i>/Test_m<i> for the
# same station, so the FREL tree is the diagonal of the proximity tree and can
# be symlinked rather than regenerated.
#
# Turn on only to inspect or plot a full sanitized stream.
SAVE_INTERIM = False
INTERIM = DATA_OUT / "interim"

# Windowed batch tree, laid out exactly like SiMWiSense's Data/ so that
# create_csv.py / main.py / baseline_proximity.py run against it unmodified:
#   <BATCHES>/<Env>/<BW>/<num_mon>/<station>/Slots/<slot>/<letter>_batch/batch_N.mat
BATCHES = DATA_OUT / "batches"

# ── Dataset shape ─────────────────────────────────────────────────────────────
ENVS        = ["Classroom"]              # only Classroom was downloaded
BW          = "80MHz"
NUM_MON     = "3mo"
STATIONS    = ["m1", "m2", "m3"]
ACTIVITIES  = list("ABCDEFGHIJKLMNOPQRST")

# Which experiment layout to emit. Decides the slot table in window.py.
#   "proximity"    -> 6 slots: Train_m1/Test_m1/.../Test_m3  (baseline_proximity.py)
#   "fine_grained" -> 2 slots: Train/Test, per-station bounds (main.py FREL)
TEST = "proximity"

# ── Subcarrier handling ───────────────────────────────────────────────────────
# What CSI_extractor_SimWiSense.m already removed (0-based, of the original 256).
# MATLAB: non_zero = [7:128,132:251]  ->  keeps 0-based 6..127 and 131..250
SIMWI_REMOVED = set(range(0, 6)) | {128, 129, 130} | set(range(251, 256))

# The SiMWiSense arrays are NOT fftshifted. Raw FFT order:
#   index i < 128  -> subcarrier  i
#   index i >= 128 -> subcarrier  i - 256
FFT_SIZE = 256

# 802.11ac VHT80 guard band. SiMWiSense removed only 3 of these 11; the other 8
# survive into the 242 columns as dead noise (mean |CSI| ~= 3.9 vs ~562 overall,
# neighbour correlation 0.015-0.44 vs 0.999). They must go before the ratio,
# because the ratio divides by them -> |r| up to 1.9e13.
GUARD_SUBCARRIERS = set(range(-128, -122)) | set(range(123, 128))

# Pilot tones (+-11, +-39, +-75, +-103). Wilight removes these; we do NOT.
# Measured on this dataset they are indistinguishable from data subcarriers
# (neighbour correlation 0.991-0.999, mean |CSI| 527 vs 562), so dropping them
# would cost 8 real subcarriers for no measurable gain. Flip to True to match
# Wilight literally (234 -> 226 -> 113 -> 56 instead of 234 -> 117 -> 58).
DROP_PILOTS = False
PILOT_SUBCARRIERS = {-103, -75, -39, -11, 11, 39, 75, 103}

# ── Wilight sanitization parameters (verbatim from
#    Single_antenna_single_file_processing.py:43-51) ────────────────────────────
THRESHOLD     = 2        # vote: flag if |phase| > THRESHOLD * row mean |phase|
VOTE_PACKETS  = 100      # vote: sample size
VOTE_FRACTION = 2 / 3    # vote: fraction of sampled packets needed to confirm
CLIP_MULT     = 5.0      # spatial clip: cap at CLIP_MULT * median(|row|)
SG_WINDOW     = 11       # Savitzky-Golay window, across subcarrier axis
SG_POLY       = 3        # Savitzky-Golay polynomial order
T_CLIP_MULT   = 5.0      # temporal clip: cap at T_CLIP_MULT * median(|column|)

# Run single ratio only (117 columns) instead of the double pass (58).
# Single ratio cancels AGC and the random per-packet phase but leaves one
# residual rotation e^-j2*pi*delta; the second pass removes that too.
SINGLE_RATIO_ONLY = False

# ── Windowing (mirrors csi2batches_SimWiSense.m) ──────────────────────────────
WINDOW_SIZE = 50
DISCARD     = 5
# csi2batches divides the packet count by this to rescale its fixed slot bounds
# onto whatever length each file actually has.
SLOT_SCALE  = 814

# Packets read per block in load_csi(). The full stream must be resident (Vote
# needs the first 100 packets, temporal_clean needs whole columns), but the
# READ is chunked so no second full-size array ever exists at once.
# 100k packets x 242 cols x 16 B ~= 390 MB per block.
BLOCK_PACKETS = 100_000

# complex128 matches Wilight exactly. complex64 halves peak memory (~4.2 GB ->
# ~2.1 GB for the largest activity) at the cost of float32 precision.
DTYPE = "complex128"
