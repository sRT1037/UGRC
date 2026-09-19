---
tags: [simwisense, plan, overview]
---

# SiMWiSense Pipeline — 4-Phase Plan

> Source: `resources/SiMWiSense`. Same 4-phase breakdown used in [[../project-log/00-aim-and-plan]] and walked file-by-file in [[../project-log/03-code-walkthrough]]. This vault mirrors [[../wilight/00-overview]]'s layout so both codebases read the same way.

## Pipeline diagram

```mermaid
flowchart TD
    A[".pcap per activity"] --> B["Phase 1: Data Pipeline\nCSI_extractor -> csi2batches -> create_csv"]
    B --> C["batch_N.mat chunks\n+ train/val/test CSVs"]
    C --> D["Phase 2: Model Architecture\nmodels.py: EmbeddingNet + Decoder"]
    D --> E["Embed_Dec model\n(untrained)"]
    E --> F["Phase 3: Supervised Training\ndataGenerator.py + TrainTest.py\nmodel_training / model_training_coarse"]
    F --> G["frozen embedding\n(saved to disk by customCallback)"]
    G --> H["Phase 4: Few-Shot Adaptation (FREL)\nmetalearn.py: FReE_Learning.retrain/test"]
    H --> I["fine-tuned classifier\n+ accuracy / confusion matrix"]
```

## The 4 phases

1. **[[01-phase1-data-pipeline]]** — pcap → CSI extraction → 50-packet windows → CSV manifests. Full depth already in [[../project-log/03-code-walkthrough]] §1–4.
2. **[[02-phase2-model-architecture]]** — `models.py`: the embedding CNN + softmax decoder, and the custom training/checkpoint logic.
3. **[[03-phase3-supervised-training]]** — `dataGenerator.py` (batch loading) + `TrainTest.py`'s `model_training`: pretrains the embedding on the full labeled set.
4. **[[04-phase4-few-shot-adaptation]]** — `metalearn.py` + `utils.py`: freezes the embedding, fine-tunes only a classifier head via N-way K-shot episodes (FREL).

## Outside the 4 phases

- **[[05-baseline-proximity]]** — `baseline_proximity.py`, the plain-CNN script for the `proximity` test. Not part of the FREL pipeline: proximity trains and tests inside one *(recorder, subject)* cell, so there is no domain shift for FREL to absorb. It establishes the *premise* the cascade rests on.

## See also
- [[05-baseline-proximity]]
- [[../project-log/00-aim-and-plan]]
- [[../project-log/01-progress]]
- [[../project-log/03-code-walkthrough]]
- [[../wilight/00-overview]]
