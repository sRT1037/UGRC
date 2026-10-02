---
tags: [project-log, ugrc, code-walkthrough]
---

# UGRC Project — SiMWiSense Code Walkthrough (file-by-file)

> Running log of the Phase 1 (Data Pipeline) walkthrough, one file/point at a time. See [[00-aim-and-plan]] for the why, [[01-progress]] for the higher-level phase summary.

## Phase 1: Data Pipeline

### 1. CSI extraction — `Matlab_code/CSI_extractor_SimWiSense.m`

pcap → raw bytes → complex CSI (chip-dependent unpacking) → static subcarrier pruning → one `.mat` per activity. No normalization, no ratio-sanitization, no windowing here — purely extraction.

- Loops env × monitor × activity letter, one `.pcap` per (env, monitor, activity).
- Per packet: strips fixed 16-byte header, rejects malformed-length frames, decodes I/Q via `typecast` (chips 4339/43455c0) or the compiled `unpack_float` MEX (chips 4358/4366c0 — Broadcom's compressed float CSI format).
- Prunes to a static `non_zero` subcarrier index mask (242/256 kept at 80MHz: `7:128, 132:251`).
- Saves the whole unwindowed per-activity stream as one `.mat` (`csi` field).

### 2. Windowing — `Matlab_code/csi2batches_SimWiSense.m`

Full-stream `.mat` → proportionally-rescaled Train/Test slicing per monitor → chop into 50-packet windows → discard 5 windows off each end → one `.mat` per surviving window.

- Reads back the per-activity `.mat` the extractor saved.
- `start`/`stop` are hardcoded as fractions out of a reference 814-packet total; actual slice bounds are rescaled by `a = length(csi)/814` to handle varying real capture lengths.
- `proximity` test: 6 slots (Train/Test × 3 monitors — each monitor is a different physical vantage point). `coarse`: 1 Train/Test pair.
- Each slot sliced into non-overlapping `window_size = 50`-packet chunks (`num_image = floor(num_p/50)`).
- First/last 5 windows of every slot discarded (`discard = 5`) — likely to avoid activity-transition artifacts at slot boundaries.
- Each surviving window saved individually as `batch_<i-discard>.mat` (`csi_mon` field, 50×242) under `Slots/<Train|Test>_m<k>/<activity>_batch/`.
- Not yet compared: `csi2batches_SimWiSense_fine_grained.m` variant.

### 3. Manifest generation — `Python_Code/create_csv.py` + `csv_main.py`

Walks the `Slots/<Train|Test>_m<k>/<activity>_batch/` folders the windowing step wrote → writes `train_set.csv`/`val_set.csv`/`test_set.csv` with `filename,label` rows.

- `csv_main.py`: CLI entry, hardcodes env/BW/monitor/station lists, dispatches per (env, station, Train|Test) to `create_csv.py`.
- `os.walk`, filters to dirs ending in `batch`; `label = root[-7]` — a single char sliced from the folder path, i.e. the activity letter (folder named e.g. `A_batch`).
- Train: random 80/20 split into train/val CSVs. Test: all rows go to `test_set.csv` (`rand < 1` always true — no actual filtering).
- **Partially resolves the [[01-progress]] §3 label-type-mismatch flag**: the CSV `label` column is written as the raw activity **letter**, not an integer. If `FewshotDataGen` truly filters against integers, the mismatch is real — next thing to check is whether `read_mat` converts letter→int on load, or whether that's the actual bug.

### 4. Loading chunks for training — `Python_Code/dataGenerator.py`

Turns `batch_N.mat` chunks into model-ready `(50, K, 2)` tensors + labels, in two consumption patterns.

- `read_mat(dir, file, NoOfSubcarrier)`: loads one chunk, slices to `NoOfSubcarrier` columns, **derives the label from the filename's first letter** via a hardcoded `'A'→0 ... 'T'→19` ladder (`read_mat_coarse`: `'A'→0..'D'→3`) — ignores the CSV `label` column entirely. Splits complex → real/imag, reshapes each to `(window, K, 1)`, concatenates → `(50, K, 2)`.
- `DataGenerator` (Keras `Sequence`): standard supervised batching (Phase 2/3) — reads the CSV once, `__getitem__` batches indices through `read_mat`.
- `FewshotDataGen`: FREL episodic sampler (Phase 4) — `labellist` built from on-disk folder-name letters; per label, samples k support + q query rows from the CSV via `df.loc[df['label']==label]`, then loads each through `read_mat`.

**Resolves the [[01-progress]] §3 flagged bug — non-issue.** The CSV `label` column is letters (confirmed in step 3), and `FewshotDataGen.labellist` is also letters, so the filter is letter-vs-letter and works. `read_mat`'s integer label is a separate representation produced only at load time for the actual training signal — never compared against the CSV.

### 5. Execution trace — `main.py` → `TrainTest.py` (how the `.mat` chunks actually get consumed at runtime)

Entry point: `python main.py <test> <Train_Env> <train_sta> <Test_Env> <test_sta> <model_save> <NoOfSubcarrier> -tr -ft`.

1. `main.py:main()` — parses CLI args, assembles all paths (incl. the 4 CSV paths from step 3), branches on `-tr`/`-ft` and `coarse`/`fine_grained`. No data touched yet.
2. **`-tr` → `TrainTest.py: model_training`** (or `_coarse`): builds `Embed_Dec` (embedding CNN + softmax decoder, `models.py`), compiles (Adam + categorical cross-entropy). Builds `train_gen`/`val_gen` = `DataGenerator(tr_csv)`/`DataGenerator(val_csv)` — CSV read into memory at init, but `.mat` files are read **lazily per-batch** via `__getitem__` → `read_mat` (step 4). `model.fit(...)` runs the standard Keras loop over `train_epochs=15`. `customCallback` saves only `model.embedding` (not the full model) — this is the frozen-embedding checkpoint the next phase needs.
3. **`-ft` → `TrainTest.py: model_testing`** (or `_coarse`): loads `FReE_Learning` (`metalearn.py`), which reloads step 2's saved embedding. Builds `meta_train_set`/`meta_test_set` = `FewshotDataGen` over the **Test_Env/test_sta's own Train split** (support/target-domain few-shot examples) and the Test split (query/eval). Loops `["crossentropy","knn"]` classifiers: `model.retrain(...)` (freeze embedding, fine-tune classifier head over N-way-K-shot episodes — `.mat` chunks read here via `FewshotDataGen.load_batch`→`read_mat`), then `model.test(...)`.

**Chain, end to end:** `.mat` chunk → CSV row → `DataGenerator`/`FewshotDataGen` → `read_mat` (actual disk read + tensor build) → `model.fit` (embedding pretraining) or `model.retrain`/`model.test` (few-shot finetune+eval).

### 6. Next — `metalearn.py` (`FReE_Learning`: `retrain`/`test` internals) or `models.py` (`Embed_Dec` architecture)

## See also
- [[00-aim-and-plan]]
- [[01-progress]]
- [[02-devVM-and-next-steps]]
