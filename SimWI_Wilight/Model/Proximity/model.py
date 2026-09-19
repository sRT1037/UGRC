"""
The proximity baseline CNN, ported verbatim from SiMWiSense's
Python_Code/baseline_proximity.py:65-89.

Architecture is UNCHANGED on purpose — it is the thing we are holding fixed
while the preprocessing varies. Including its quirks:

  * a bare Activation('relu') sitting directly after a ReLU() (line 75
    upstream). Mathematically a no-op. Kept so the graph matches the published
    baseline exactly.
  * fc1 / fc2 are accepted upstream and never used. Dropped here rather than
    carried as dead arguments.

The head is Flatten -> Dense, so parameter count scales with n_sub:

    n_sub   flatten   dense params   total
      242    92,928      1,858,580   ~1.97 M
       58    22,272        445,460   ~558 k

That 3.5x gap is why the baseline should also be run at n_sub=58: otherwise a
242-vs-58 comparison confounds "did the ratio destroy information" with "did
the model get smaller".
"""

from tensorflow import keras
from tensorflow.keras import layers, models

WINDOW_SIZE = 50


def build_baseline_cnn(n_sub, n_classes, window=WINDOW_SIZE):
    m = models.Sequential(name=f"baseline_cnn_{n_sub}sc")

    m.add(layers.Input(shape=(window, n_sub, 2)))
    m.add(layers.Conv2D(64, (3, 3), padding="same", strides=2))
    m.add(layers.BatchNormalization())
    m.add(layers.ReLU())
    m.add(layers.Conv2D(64, (3, 3), padding="same"))
    m.add(layers.BatchNormalization())
    m.add(layers.ReLU())

    m.add(layers.Activation("relu"))          # upstream :75 — no-op, kept
    m.add(layers.Conv2D(64, (3, 3), padding="same"))
    m.add(layers.BatchNormalization())
    m.add(layers.ReLU())
    m.add(layers.Conv2D(64, (3, 3), padding="same"))
    m.add(layers.BatchNormalization())
    m.add(layers.ReLU())

    m.add(layers.MaxPooling2D(pool_size=(2, 1)))
    m.add(layers.Flatten())
    m.add(layers.Dense(n_classes, activation="softmax"))

    return m


def compile_baseline(m, lr=0.01):
    """Upstream: Adam(0.01), categorical crossentropy, accuracy."""
    m.compile(optimizer=keras.optimizers.Adam(lr),
              loss="categorical_crossentropy",
              metrics=["accuracy"])
    return m
