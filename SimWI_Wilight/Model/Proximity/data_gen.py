"""
Data loading for the proximity baseline, ported from SiMWiSense's
Python_Code/dataGenerator.py.

Faithful to the original except for three things, each marked CHANGED:

  1. Static removal is available as a flag (`center`). Wilight subtracts the
     per-window mean before its Doppler FFT (`win - win.mean(axis=0)`,
     Single_antenna_single_file_processing.py:266); we dropped the Doppler
     stage and with it that line, so it is reinstated here as a load-time
     option. Needed because after the double ratio every value sits at
     1.00 +- 0.03, and SiMWiSense's CNN does no input normalisation at all.

  2. keras.utils.PyDataset instead of keras.utils.Sequence, with worker
     threads. Keras 3 removed the `workers=` argument from model.fit(); it now
     lives on the dataset. This matters: one training run reads ~700k .mat
     files off disk, single-threaded in the original.

  3. The 20-branch if/elif ladder in read_mat is replaced by a dict lookup.
     Same mapping, A->0 .. T->19.
"""

import os

import numpy as np
import scipy.io as spio
import pandas as pd
from tensorflow import keras

WINDOW_SIZE = 50
LABELS = "ABCDEFGHIJKLMNOPQRST"
LABEL_OF = {c: i for i, c in enumerate(LABELS)}      # CHANGED (3): was if/elif


def read_mat(dirpath, filename, n_sub, norm="none"):
    """
    One batch_N.mat -> ((50, n_sub, 2) float, int label).

    The label comes from the FILENAME's first character, exactly as upstream —
    the `label` column in the CSV is never used for this.

    n_sub TRUNCATES: [:, 0:n_sub] takes the first n_sub columns, it does not
    subsample. Passing 58 against a 242-column tree gives the first 58
    subcarriers, which is how we hold model capacity fixed across arms.
    """
    data = spio.loadmat(os.path.join(dirpath, filename))
    csi = data["csi_mon"][:, 0:n_sub]

    # CHANGED (1): input normalisation. `norm` is one of
    #
    #   "none"         upstream behaviour: raw values straight into the CNN.
    #
    #   "center"       per-subcarrier static removal over the packet axis —
    #                  Wilight's pre-Doppler line (`win - win.mean(axis=0)`,
    #                  Single_antenna_single_file_processing.py:266). Removes
    #                  the constant multipath (walls, furniture, direct path),
    #                  static across a ~36 ms window, keeping the motion.
    #
    #   "standardize"  center, then divide by the window's own std.
    #                  REQUIRED for the sanitized arm: measured over 300 random
    #                  windows, per-window std after centering has a median of
    #                  0.0036 and a p99 of 0.348 — a ~100x spread, with 39% of
    #                  windows above 10x the median. That is inherent to the
    #                  ratio (a denominator in a deep fade inflates it, up to
    #                  Wilight's 5x-median clip). With that spread, every batch
    #                  of 64 has a different variance, BatchNorm's moving
    #                  averages match no real batch, and inference-mode
    #                  accuracy collapses to below chance while training-mode
    #                  accuracy looks fine. Verified: 0.08% vs 11.8% on the
    #                  SAME training data.
    if norm in ("center", "standardize"):
        csi = csi - csi.mean(axis=0, keepdims=True)

    real = np.real(csi).reshape(WINDOW_SIZE, -1, 1)
    imag = np.imag(csi).reshape(WINDOW_SIZE, -1, 1)
    x = np.concatenate([real, imag], axis=2)

    if norm == "standardize":
        x = x / (x.std() + 1e-12)          # scalar per window, both channels

    return x, LABEL_OF[filename[0]]


class CSIDataset(keras.utils.PyDataset):
    """
    Keras 3 PyDataset over a train/val/test CSV manifest.

    Upstream's __len__ is floor(N / batchsize), so the trailing partial batch is
    silently dropped. Preserved — it is why the confusion-matrix code slices
    Y_true[:len(Y_pred)].
    """

    def __init__(self, data_dir, csv_path, n_sub, n_classes, batch_size,
                 norm="none", shuffle=True, workers=8, max_queue_size=24):
        # CHANGED (2): workers/use_multiprocessing now belong to the dataset
        super().__init__(workers=workers, use_multiprocessing=False,
                         max_queue_size=max_queue_size)
        df = pd.read_csv(csv_path)
        self.data_dir = str(data_dir)
        self.files = df["filename"].tolist()
        self.n_sub = n_sub
        self.n_classes = n_classes
        self.batch_size = batch_size
        self.norm = norm
        self.shuffle = shuffle
        self.indexes = np.arange(len(self.files))
        self.on_epoch_end()

    def __len__(self):
        return len(self.files) // self.batch_size

    def __getitem__(self, idx):
        sel = self.indexes[idx * self.batch_size:(idx + 1) * self.batch_size]
        X = np.empty((len(sel), WINDOW_SIZE, self.n_sub, 2), dtype=np.float32)
        y = np.empty(len(sel), dtype=int)
        for i, k in enumerate(sel):
            X[i], y[i] = read_mat(self.data_dir, self.files[k],
                                  self.n_sub, self.norm)
        return X, keras.utils.to_categorical(y, num_classes=self.n_classes)

    def on_epoch_end(self):
        if self.shuffle:
            np.random.shuffle(self.indexes)

    def ordered_labels(self):
        """True labels in __getitem__ order — for the confusion matrix.
        Only meaningful when shuffle=False."""
        n = len(self) * self.batch_size
        return np.array([LABEL_OF[self.files[k][0]] for k in self.indexes[:n]])
