---
tags: [wilight, plan, overview]
---

# Wilight Pipeline — 4-Phase Plan

> Source: `resources/Wilight-Code-CSI-Doppler`. This vault mirrors the 4-phase breakdown already used for [[SiMWiSense]] so both codebases read the same way. See [[../project-log/00-aim-and-plan]] for why we want this pipeline (ratio sanitization swapped into SiMWiSense).

## Pipeline diagram

```mermaid
flowchart TD
    A[".pcap file\nNexmon capture"] --> B["Phase 1: Extraction\ncsi_extractor.py"]
    B --> C["complex CSI .npz\n(N_packets x N_subcarriers)"]
    C --> D["Phase 2: Null/Pilot Pruning\nremove guard, DC, pilot tones"]
    D --> E["pruned complex CSI\n256 to 234 subcarriers (80MHz)"]
    E --> F["Phase 3: Ratio Sanitization\nSingle Ratio then Double Ratio\n(Vote to Interpolate to Clip to Savitzky-Golay)"]
    F --> G["double_ratio CSI\n234 to ~58 subcarrier-groups"]
    G --> H["Phase 4a: Temporal Clean\nclip + interpolate along packet axis"]
    H --> I["sanitized complex CSI\nready to hand off"]
    I -.dropped, not used.-> J["Phase 4b: Doppler/STFT\n(kept in Wilight, not ported)"]

    style J fill:#00000000,stroke-dasharray: 5 5
```

## The 4 phases

1. **[[01-phase1-extraction]]** — `csi_extractor.py`: raw `.pcap` → complex CSI `.npz`.
2. **[[02-phase2-null-pilot-pruning]]** — remove guard/null/DC/pilot subcarriers (256 → 234 at 80MHz).
3. **[[03-phase3-ratio-sanitization]]** — Single Ratio + Double Ratio, each with Vote → Interpolate → Clip → Savitzky-Golay.
4. **[[04-phase4-temporal-clean-and-doppler]]** — Temporal Clean (kept) + Doppler/STFT (dropped for our integration).

## The theory behind it

**[[05-why-the-ratio-works]]** — the hardware model the ratio cancels, the algebra of *what* cancels and why the pass runs twice, and the two costs (dimension halving, and the ratio sitting near 1 because adjacent subcarriers are highly correlated). Also records the two blockers found when checking this against our actual SiMWiSense `.mat` files.

## What we actually need

Only **Phases 1–3 + Temporal Clean (start of Phase 4)**. The Doppler/STFT half of Phase 4 stays in Wilight's own repo — SiMWiSense's FREL pipeline consumes raw `Sp × K × 2` CSI tensors, not spectrograms (see [[../project-log/00-aim-and-plan]]).

## See also
- [[05-why-the-ratio-works]]
- [[../project-log/00-aim-and-plan]]
- [[../project-log/01-progress]]
- [[../project-log/03-code-walkthrough]]
