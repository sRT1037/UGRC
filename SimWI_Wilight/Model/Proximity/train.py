"""
Train and evaluate ONE cell of the proximity grid.

    python train.py --arm sanitized --station m1 --subject m2 --subcarriers 58 --center

A cell is a (recorder, subject) pair:
    train on  <root>/<env>/80MHz/3mo/<station>/Slots/Train_<subject>
    test  on  <root>/<env>/80MHz/3mo/<station>/Slots/Test_<subject>
Same person, same device, different time block. No domain shift — that is why
proximity uses this plain CNN and not FREL.

The model predicts the 20 ACTIVITIES. station/subject select the data, they are
never predicted.

Writes into Results/runs/<tag>.json:  accuracy, loss, per-epoch history,
confusion matrix, and the full config, so the 9-cell grid can be assembled
afterwards without re-reading logs.
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from tensorflow import keras
from sklearn.metrics import confusion_matrix

from data_gen import CSIDataset, LABELS
from model import build_baseline_cnn, compile_baseline

HERE = Path(__file__).resolve().parent          # SimWI_Wilight/Model/Proximity
REPO = HERE.parents[2]                          # UGRC
RESULTS = HERE.parents[1] / "Results"           # SimWI_Wilight/Results

ARMS = {
    # arm name  -> batch tree root
    "sanitized": REPO / "data" / "SimWi_Wilight" / "batches",
    "baseline":  REPO / "data" / "SimWi_raw" / "batches",
}


def build_paths(root, env, station, subject):
    base = Path(root) / env / "80MHz" / "3mo" / station / "Slots"
    return base / f"Train_{subject}", base / f"Test_{subject}"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--arm", choices=list(ARMS), default="sanitized")
    p.add_argument("--root", default=None, help="override the arm's tree root")
    p.add_argument("--env", default="Classroom")
    p.add_argument("--station", required=True, help="which monitor RECORDED (folder)")
    p.add_argument("--subject", required=True, help="which subject PERFORMED (slot)")
    p.add_argument("--subcarriers", type=int, required=True)
    p.add_argument("--norm", choices=["none", "center", "standardize"],
                   default="none",
                   help="input normalisation; 'standardize' is required for the "
                        "sanitized arm (see data_gen.read_mat)")
    p.add_argument("--epochs", type=int, default=15)      # upstream default
    p.add_argument("--batch-size", type=int, default=64)  # upstream default
    p.add_argument("--lr", type=float, default=0.01)      # upstream default
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--tag", default=None)
    args = p.parse_args()

    root = Path(args.root) if args.root else ARMS[args.arm]
    train_dir, test_dir = build_paths(root, args.env, args.station, args.subject)
    for d in (train_dir, test_dir):
        if not d.is_dir():
            raise SystemExit(f"missing {d}")

    tag = args.tag or (f"{args.arm}_{args.subcarriers}sc_{args.norm}"
                       f"_{args.env}_{args.station}_{args.subject}")
    (RESULTS / "runs").mkdir(parents=True, exist_ok=True)
    (RESULTS / "models").mkdir(parents=True, exist_ok=True)
    ckpt = RESULTS / "models" / f"{tag}.keras"

    print("=" * 72)
    print(f"  {tag}")
    print("=" * 72)
    print(f"  recorded by : {args.station}      performed by : {args.subject}")
    print(f"  train : {train_dir}")
    print(f"  test  : {test_dir}")
    print(f"  subcarriers {args.subcarriers} | norm={args.norm} | "
          f"epochs={args.epochs} bs={args.batch_size} lr={args.lr}")

    common = dict(n_sub=args.subcarriers, n_classes=len(LABELS),
                  batch_size=args.batch_size, norm=args.norm,
                  workers=args.workers)
    train_gen = CSIDataset(train_dir, train_dir / "train_set.csv", **common)
    val_gen   = CSIDataset(train_dir, train_dir / "val_set.csv",   **common)
    test_gen  = CSIDataset(test_dir,  test_dir  / "test_set.csv",
                           shuffle=False, **common)
    print(f"  batches/epoch: train {len(train_gen)}  val {len(val_gen)}  "
          f"test {len(test_gen)}")

    m = compile_baseline(build_baseline_cnn(args.subcarriers, len(LABELS)), args.lr)
    print(f"  params: {m.count_params():,}")

    # Upstream callbacks (baseline_proximity.py:92-105). Note ReduceLROnPlateau's
    # patience(15) >= epochs(15), so it never fires — kept for fidelity.
    cbs = [
        keras.callbacks.ReduceLROnPlateau(monitor="val_loss", patience=15,
                                          factor=0.5, min_lr=1e-4, verbose=1),
        keras.callbacks.ModelCheckpoint(str(ckpt), save_best_only=True, verbose=1),
        keras.callbacks.EarlyStopping(monitor="val_loss", min_delta=0.05,
                                      patience=10, verbose=1),
    ]

    t0 = time.time()
    hist = m.fit(train_gen, validation_data=val_gen,
                 epochs=args.epochs, callbacks=cbs, verbose=2)
    t_train = time.time() - t0

    # Reload the BEST checkpoint, not the last epoch — upstream :164
    best = keras.models.load_model(ckpt)
    loss, acc = best.evaluate(test_gen, verbose=0)

    y_pred = np.argmax(best.predict(test_gen, verbose=0), axis=1)
    y_true = test_gen.ordered_labels()[:len(y_pred)]
    cm = confusion_matrix(y_true, y_pred, labels=range(len(LABELS)),
                          normalize="true")

    out = {
        "tag": tag, "arm": args.arm, "env": args.env,
        "station": args.station, "subject": args.subject,
        "diagonal": args.station == args.subject,
        "subcarriers": args.subcarriers, "norm": args.norm,
        "epochs_requested": args.epochs, "epochs_run": len(hist.history["loss"]),
        "batch_size": args.batch_size, "lr": args.lr,
        "params": int(m.count_params()),
        "n_train": len(train_gen) * args.batch_size,
        "n_test": len(y_pred),
        "test_accuracy": float(acc), "test_loss": float(loss),
        "train_seconds": round(t_train, 1),
        "history": {k: [float(v) for v in vs] for k, vs in hist.history.items()},
        "confusion_matrix": np.round(cm, 4).tolist(),
    }
    (RESULTS / "runs" / f"{tag}.json").write_text(json.dumps(out, indent=2))

    print(f"\n  TEST ACCURACY : {acc:.4f}   loss {loss:.4f}")
    print(f"  trained {len(hist.history['loss'])} epochs in {t_train/60:.1f} min")
    print(f"  -> Results/runs/{tag}.json")


if __name__ == "__main__":
    main()
