---
tags: [simwisense, phase1, data-pipeline]
---

# Phase 1 — Data Pipeline

**Files:** `Matlab_code/CSI_extractor_SimWiSense.m` → `Matlab_code/csi2batches_SimWiSense.m` → `Python_Code/create_csv.py` + `csv_main.py`

Turns raw `.pcap` captures into labeled, model-ready `.mat` chunks + CSV manifests. This is the phase we're replacing the sanitization part of with Wilight — see [[../wilight/00-overview]].

```mermaid
flowchart TD
    A[".pcap per activity letter"] --> B["CSI_extractor_SimWiSense.m\nchip-decode + static prune\n(256 -> 242 subcarriers, 80MHz)"]
    B --> C["one .mat per activity\nfull unwindowed stream"]
    C --> D["csi2batches_SimWiSense.m\nrescale Train/Test slice bounds\nchop into 50-packet windows\ndiscard first/last 5 windows"]
    D --> E["batch_N.mat per window\n(50 x 242, csi_mon field)"]
    E --> F["create_csv.py / csv_main.py\nwalk *_batch/ folders"]
    F --> G["train_set.csv / val_set.csv\n(80/20 split)"]
    F --> H["test_set.csv\n(all rows)"]
```

## The 3 steps, briefly

1. **Extraction** (`CSI_extractor_SimWiSense.m`): pcap → chip-specific decode (`typecast` or `unpack_float` MEX) → complex CSI → static `non_zero` subcarrier prune → one `.mat` per activity.
2. **Windowing** (`csi2batches_SimWiSense.m`): slices each activity stream into proportionally-rescaled Train/Test ranges, chops into 50-packet windows, discards 5 edge windows per side, saves one `.mat` per window.
3. **Manifest** (`create_csv.py`/`csv_main.py`): walks the windowed `.mat` files, writes `filename,label` CSV rows (label = activity letter from the folder name), 80/20 train/val split.

Full step-by-step logic (already verified against source) lives in [[../project-log/03-code-walkthrough]] §1–3 — this file is the short pointer version to keep the phase layout consistent with [[../wilight]].

## See also
- [[00-overview]]
- [[02-phase2-model-architecture]]
- [[../project-log/03-code-walkthrough]]
