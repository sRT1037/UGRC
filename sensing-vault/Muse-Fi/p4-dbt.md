---
tags: [muse-fi, phase4, walkthrough, doubts]
---

# Phase 4 — Step-by-Step Walkthrough (worked examples)

> Companion to [[04-phase4-sparse-recovery]] — that file is the dense reference; this one is the example-driven, question-by-question walkthrough that built up the intuition, step by step, from segmentation through the TCN-AE. Read this first if the main file feels crowded.

## 1. Segmentation

Slide a window of length $\Delta t$ across the raw, irregular-timestamp CSI series. Count real samples inside each window:
- more than $N_{nsp}$ samples → **non-sparse**
- otherwise → **sparse**

Example, window `[0.0–0.1]` with raw arrivals at $t=0.00,0.02,0.04,0.06$ (4 samples) → non-sparse. A window `[0.5–0.9]` with zero arrivals in it → sparse. This is purely a labeling step — nothing gets modified yet, each window just gets tagged for how step 2 should treat it.

## 2. Resampling — different treatment for sparse vs. non-sparse

Both cases must land on the same evenly-spaced time grid at frequency $f_{rs}$, but *how* they get there differs in kind, not just degree.

**Non-sparse window — genuine interpolation.** Enough real neighboring samples exist to trust a reconstruction.
- Example: raw samples at $t=0.01,0.03,0.045,0.07,0.09$; grid targets `0.00,0.02,0.04,0.06,0.08`.
- First remove outliers (a raw value wildly inconsistent with its neighbors gets dropped).
- Then interpolate each grid point from its real neighbors — e.g. grid point `0.02` sits between real samples at 0.01 and 0.03, so it can be confidently estimated. Every output point here counts as **trustworthy real data**, just re-timed.

**Sparse window — snap, don't fabricate.** Not enough real samples nearby to interpolate safely.
- Example: only one real sample at $t=0.03$, value 5; grid `0.00,0.02,0.04,0.06,0.08`.
- **Snap** the one real sample to its **nearest** grid instant only — `0.02 → 5` (preserves the true measurement exactly, no blending with nonexistent neighbors).
- Every other grid instant with nothing nearby gets explicitly tagged **`no-data`** and linearly filled as a placeholder — not trusted, just structurally present. This tag is what becomes the $-1$ flag in normalization (step 4).

**Shared final sub-step**: both paths pass through a low-pass filter at cutoff $f_{cut}$ to denoise — real samples carry measurement noise too, regardless of sparsity.

**The core distinction in one line**: non-sparse resampling produces values you can trust as reconstructed signal; sparse resampling produces values that are *honest about being missing*, and that honesty is exactly what lets the TCN-AE later learn to fix them properly instead of the pipeline silently pretending it already had good data.

## 3. Transformation — adding a frequency axis, not replacing time with it

**Why not just feed the raw time-domain wiggle in:** the same underlying motion (e.g. breathing) produces a differently-shaped raw phase trace depending on subject position, room multipath, antenna geometry — lots of irrelevant variation baked directly into the raw waveform's shape, making it environment- and subject-specific and hard to recognize directly.

**The fix**: motion has a fairly characteristic *frequency* signature regardless of all that (breathing sits in a narrow low band, gestures/activity have broader/faster content) — so represent each moment by "how much energy at each frequency" instead of just "one wiggly number."

**Important correction — this is not "flip time for frequency."** If you actually discarded time and kept only frequency, you'd get one static FFT — no sense of *when* anything happened, useless for sensing motion unfolding over time. What actually happens: **both axes are kept**. For every time step $n$ (still there, still in order), attach a vector of $N_F$ frequency-bin values describing that instant's content.

```
Shape change:
  1D:  N_s time-steps, one number each
   ↓
  2D:  N_F frequency bins  ×  N_s time-steps   = the spectrogram
```

Time stays the horizontal axis; frequency is a *new* vertical axis added at each point along it, not a replacement. "At every point in time, also tell me its frequency makeup" — not "instead of time, use frequency."

Note: this generic pipeline step doesn't commit to one specific transform. Downstream, the paper uses **STFT** for respiration and **WSST** for gesture/activity (better suited to fast, non-stationary signals) — the pipeline description here is the general shape underneath both.

## 4. Normalization — what's actually being rescaled

Per the paper's own notation ("mapping each $\tilde x_n$ into $\hat x_n\in[0,1]^{N_F}$"), this is applied **per time step (per column), not globally across the whole spectrogram**: for each column $n$, find the min and max among just that column's $N_F$ values, and rescale so the smallest → 0, largest → 1.

**What this buys you**: keeps the *shape* of the frequency profile at each instant (which bins are relatively strong — the actual motion signal) while stripping out *absolute* strength, which is heavily driven by subject-to-device distance rather than motion itself. Two subjects doing the same gesture at different distances become comparable.

**Honest tradeoff** (not discussed by the paper, a natural consequence of per-column scaling): you lose the ability to compare magnitude *across time* from the normalized values alone — a quiet moment and a loud moment both get stretched to fill $[0,1]$, so "was there more motion 2s ago" isn't recoverable from $\hat x_n$ alone.

**Override on top**: any column from a `no-data` timestamp skips this rescaling entirely and is forced to $-1$ across all $N_F$ bins — a value real min-max output can never produce, so the network always knows "measured" from "fabricated placeholder."

## 5. The TCN-AE — input, internals, output, drawn out

```
INPUT: normalized spectrogram X̂  — shape (N_F=32, N_s)
        one column per time-step, no-data columns forced to -1

  freq bin 32 ┤ ▓░▓▓░░▓▓▓░░░▓▓░░▓▓▓░░▓▓░░▓▓▓░░
  freq bin 16 ┤ ░▓▓░▓▓░░▓▓░▓░▓▓░░▓▓▓░▓▓░░▓▓░▓░     ← -1 columns = the sparse gaps
  freq bin  1 ┤ ▓▓░░░▓▓▓░░▓▓▓░░░▓▓▓░░▓▓▓░░░▓▓▓
               └──────────── N_s time-steps ────────────┘
```

**Step A — the first dilated conv layer changes channel count, not shape.** Each of $N_{ch}=64$ kernels spans the *entire* frequency axis (all 32 bins) plus $L=5$ time-taps spaced $\chi$ apart — sliding along time, each kernel collapses a 5-tap × 32-bin patch into one number. 64 kernels → every time-step's 32-dim vector becomes a 64-dim feature vector:

```
INPUT to block 1:  (N_F=32)  x  N_s
                        │  dilated conv, 64 kernels, each spans all 32 freq bins
                        ▼
OUTPUT of block 1: (N_ch=64) x  N_s      ← same time length (zero-padded), new channel count
```

From block 2 onward it's $64\to64$ — only the dilation $\chi$ changes.

**Step B — 4 blocks, exponentially widening how far back one output value can "see":**

| after block | dilation χ | this block's own reach ($=(L-1)\chi$) | cumulative receptive field |
|---|---|---|---|
| 1 | 1 | 4 steps | ~5 time-steps |
| 2 | 2 | 8 steps | ~13 time-steps |
| 3 | 4 | 16 steps | ~29 time-steps |
| 4 | 8 | 32 steps | ~61 time-steps |

So one output element after block 4 depends on roughly the last 61 time-steps of input — not because any single kernel got huge, but because stacking exponentially-growing gaps between taps makes the effective window balloon cheaply. This is the concrete version of "sees almost the entire spectrogram."

**Inside each block** (Fig. 7):
```
block input ──▶ DilatedConv ──▶ WeightNorm ──▶ ReLU ──▶ Dropout ──▶ (+) ──▶ block output
     │                                                                ▲
     └────────────────────── residual / skip connection ─────────────┘
```
[my own read, not stated by the paper]: the skip connection adding block-input back onto block-output is the standard ResNet-style trick — helps gradients flow through 4 stacked layers, lets each block learn a small correction rather than relearning how to pass information through unchanged.

**Step C — the tail, projecting back down to $N_F$:**

```
(N_ch=64) x N_s  ──▶  1D Conv  ──▶  Fully Connected  ──▶  1D DeConv  ──▶  (N_F=32) x N_s
   rich, wide-context                bottleneck                          recovered
   features from the                 (compress the                       spectrogram —
   TCN blocks                        sequence, then                      gaps filled in
                                      expand back)
```

This is the actual "autoencoder" part: encode (1D Conv) → squeeze through a bottleneck (Fully Connected) → decode (1D DeConv) back to $N_F\times N_s$. The paper's Fig. 7 names these three sub-layers but doesn't give exact bottleneck size or layer count.

**Overall input/output**: $(32\times N_s,\text{ with }{-1}\text{ gaps}) \to (32\times N_s,\text{ gaps filled})$ — same shape end-to-end — but internally the channel dimension balloons from 32 to 64 for all TCN-block processing, only projected back down to 32 at the very last step.

## See also
- [[00-overview]]
- [[04-phase4-sparse-recovery]]
- [[03-phase3-sensing-strategies-and-traffic]]
