---
tags: [project-log, ugrc, progress]
---

# UGRC Project — Progress Log

> What's actually been done so far, roughly in order. See [[00-aim-and-plan]] for the why, [[02-devVM-and-next-steps]] for infra state + what's next.

## 1. Vault built from background reading

Read through the tutorial/survey papers and the SiMWiSense + MUSE-Fi papers (all in `papers/`, excluded from git — see [[02-devVM-and-next-steps]]) and wrote up `sensing-vault/basics/` (EM fundamentals → CSI fundamentals → ray-tracing/scattering/Fresnel-zone models → feature extraction → sanitization → deep learning on CSI) and `sensing-vault/multipeople/` (SiMWiSense's 7-level breakdown, FREL/embedding/meta-learning companions, MUSE-Fi).

Notes added specifically from this project's background-reading pass (not in the original vault): `fresnel-zone-model.md`, `CSI-data-collection.md`, `CARM-CFR-power-model.md`, `multipeople/MUSE-Fi.md`, plus a benchmark-informed update to `wireless-sensing-DL.md` §7 (SenseFi/WiLDAR evidence that shallow models beat deep ones on CSI specifically).

## 2. Repo infrastructure

- `UGRC` initialized as its own git repo, pushed to GitHub as **public** repo `sRT1037/UGRC`.
- `papers/` (copyrighted reference PDFs) excluded from git entirely — its local path lives in `.env` (gitignored), with `.env.example` committed as the template (`PAPERS_DIR=./papers`).
- `resources/SiMWiSense` and `resources/Wilight-Code-CSI-Doppler` added as **git submodules** (not plain clones) — keeps them linked to their original repos without duplicating history.

## 3. SiMWiSense code walkthrough

**Phase 4 (FREL) walked first**, via `main.py`:
- `main.py` is a CLI switch between `coarse` (4-class, subject ID) and `fine_grained` (20-class, activity) tests, and between `-tr` (train embedding) / `-ft` (finetune + test).
- `Embed_Dec` (`models.py`) = the embedding network ($E_\theta$: 4×Conv2D-BN-ReLU @ 64 filters, GlobalAveragePooling2D) + a one-layer softmax decoder ($C_\phi$) — matches the vault's FREL note exactly.
- `customCallback` only ever saves `model.embedding` to disk (not the full `Embed_Dec`), which is what structurally sets up Phase 2's "frozen embedding" assumption.
- `FReE_Learning` (`metalearn.py`) implements the freeze-embedding / fine-tune-classifier-only pattern via $N$-way $K$-shot episodes (`FewshotDataGen`), with three classifier options — `crossentropy`, `knn`, and `proto` (Prototypical Networks) — though the current `TrainTest.py` driver only loops over `crossentropy`/`knn`; `proto` is implemented in `utils.py` but not currently wired into the main entry point.
- **Open bug flagged, not yet verified**: `FewshotDataGen`'s `labellist` is built from folder names (letters), but filtered against a CSV `label` column that (per `read_mat`) stores integers — looks like a type mismatch that would make the filter always empty unless the CSV actually stores letters. Needs checking against `create_csv.py`/`csv_main.py` before trusting this path runs correctly.

**Phase 1 (Data Pipeline) walked next**, start of the pipeline:
- `CSI_extractor_SimWiSense.m` — reads raw `.pcap` per activity letter, decodes CSI (chip-specific: 4339/43455c0 via `typecast`, 4358/4366c0 via compiled `unpack_float` MEX), prunes to 242 usable subcarriers via a fixed `non_zero` index list (80MHz case: `7:128, 132:251`), saves one `.mat` per activity containing the *entire* un-windowed stream. No ratio/vote/clip sanitization at this stage — just pruning.
- `csi2batches_SimWiSense.m` — slices each activity's full stream into named Train/Test time ranges (hardcoded start/stop packet-fraction indices), then chunks each slice into non-overlapping 50-packet windows, one `.mat` file per window (`batch_N.mat`, `csi_mon` field).
- **Not yet walked**: `create_csv.py`/`csv_main.py` (the manifest-generation step that produces `train_set.csv`/`val_set.csv`/`test_set.csv`), `csi2batches_SimWiSense_fine_grained.m`, and the `baseline_*.py` scripts (Phase 3, plain-CNN comparison path).

## 4. Wilight-Code-CSI-Doppler walkthrough (preprocessing technique)

Full pipeline read: `csi_extractor.py` (Nexmon pcap → complex CSI `.npz`), then the real technique in `Single_antenna_single_file_processing.py` / `doppler_visualizer.py` / `preprocessing_finalize.ipynb` (the canonical source both `.py` scripts claim to mirror):

1. Null/pilot/DC subcarrier pruning (256→~237, hardcoded indices specific to this repo's 802.11ac/80MHz Nexmon capture layout).
2. **Single ratio**: `r[k] = CSI[2k] / CSI[2k+1]` — adjacent-subcarrier division within one packet.
3. **Double ratio**: same operation applied again to the single-ratio output.
   - Each ratio pass includes 4 sub-steps: **Vote** (flag subcarrier columns whose phase deviates from the packet's own average, confirmed via majority vote across a sample of packets) → **Interpolate** (linearly fill confirmed-bad columns from neighbors) → **Clip** (cap per-packet magnitude outliers at a multiple of that packet's median) → **Savitzky-Golay smoothing** (across the subcarrier axis).
4. **Temporal Clean** — same clip+interpolate idea, but along the packet/time axis instead of the subcarrier axis.
5. **Doppler/STFT** (sliding-window FFT → velocity spectrogram) — **this is the stage we're dropping**, per [[00-aim-and-plan]].

**Three real discrepancies flagged** between the notebook (canonical) and the two `.py` scripts — relevant if we ever need the Doppler stage for anything else later, though irrelevant to the current plan since we're skipping it: normalization strategy differs (global/shared-max vs. per-window vs. per-file), DC-bin zeroing is in the notebook but missing from both `.py` scripts, and packet-rate assumption differs (`Tc=1/150` in the notebook vs. `Tc=1/500` in both `.py` scripts).

## 5. Dataset status

Confirmed: **no actual dataset exists anywhere in `UGRC` locally** — both reference repos are code-only. SiMWiSense's real dataset (~190GB) is external, via a Google Drive link or IEEE DataPort (both in `resources/SiMWiSense/README.md`). This is what triggered the dev-machine decision in [[02-devVM-and-next-steps]].

## See also
- [[00-aim-and-plan]]
- [[02-devVM-and-next-steps]]
