---
tags: [project-log, ugrc, plan]
---

# UGRC Project — Aim & Plan

> Read this file first in a new session. It's the "why" — for "what's been done" see [[01-progress]], for "current infra state / how to pick up work" see [[02-devVM-and-next-steps]].

## The aim

This is an undergraduate research project (UGRC) on Wi-Fi CSI-based human sensing, built around understanding and then extending **SiMWiSense** (`resources/SiMWiSense`) — a simultaneous multi-subject activity classification system that uses a cascaded classifier + a few-shot learning algorithm (FREL) to adapt to new environments/subjects with minimal new data. Background theory for all of this lives in `sensing-vault/basics/` and `sensing-vault/multipeople/`.

## The concrete technical goal right now

Replace/augment SiMWiSense's CSI preprocessing with the **ratio-based sanitization technique** implemented in a second reference repo, **Wilight-Code-CSI-Doppler** (`resources/Wilight-Code-CSI-Doppler`) — specifically its null/pilot subcarrier pruning + single-ratio + double-ratio + temporal-clean stages (adjacent-subcarrier division that cancels common per-packet noise, applied twice). We do **not** want Wilight's Doppler/STFT stage — SiMWiSense's FREL pipeline consumes raw CSI tensors directly (`Sp × K × 2`, real/imag), not Doppler spectrograms, so that stage is dropped entirely.

After swapping in that sanitization step, the plan is to run SiMWiSense's **existing, unmodified FREL pipeline** (`main.py`, `-tr` then `-ft`) on the newly-sanitized data and compare against the baseline (SiMWiSense's own lightweight amplitude-normalization-only preprocessing).

## Why this might matter

SiMWiSense's own sanitization is minimal (per-window amplitude normalization only — see `sensing-vault/multipeople/SiMWiSense-system-architecture.md` §2). Wilight's ratio technique is a more aggressive, physically-motivated noise-cancellation step (same family of idea as the vault's `[[CARM-CFR-power-model]]` and the survey's FarSense-style CSI-ratio model, but applied across adjacent subcarriers on one antenna instead of across two antennas). Whether it helps or hurts SiMWiSense's classifier is an open, testable question — that's the experiment.

## High-level roadmap

The SiMWiSense codebase itself was broken into 4 phases for a code walkthrough (see [[01-progress]] for what's covered so far):

1. **Data Pipeline** — pcap → CSI extraction → windowed samples → CSV manifests (Matlab + `create_csv.py`/`csv_main.py`)
2. **Model Architecture** — `models.py` (`EmbeddingNet`, `Decoder`, `Embed_Dec`)
3. **Supervised Training** — `dataGenerator.py` + `TrainTest.py`'s `model_training`/`model_training_coarse`, plus the standalone `baseline_*.py` scripts
4. **Few-Shot Adaptation (FREL)** — `metalearn.py`, `utils.py`, `TrainTest.py`'s `model_testing`/`model_testing_coarse`

The integration work (swapping in Wilight's sanitization) is new work layered on top of **Phase 1**, upstream of everything else — see [[02-devVM-and-next-steps]] for the concrete next steps and known hiccups.

## See also
- [[01-progress]]
- [[02-devVM-and-next-steps]]
- [[../multipeople/SiMWiSense]]
