---
tags: [project-log, ugrc, infra, next-steps]
---

# UGRC Project — Dev Machine State & Next Steps

> Pick up work here. See [[00-aim-and-plan]] for the why, [[01-progress]] for the full history.

## Why a second machine at all

The primary working laptop (Linux/WSL) can't hold the SiMWiSense dataset (~190GB). Decision: use a separate, recently-bought Mac as the actual data-storage + compute machine, and work on it remotely from the Linux/WSL laptop (via Cursor) instead of copying data back and forth.

## Infra set up so far (done)

1. **Tailscale** — installed and connected on **three** places that turned out to matter separately: inside WSL, natively on Windows (WSL's Tailscale instance does *not* cover Windows' own network stack — this cost real debugging time, see hiccup below), and on the Mac. All three now on the same tailnet, same account.
2. **SSH key auth, Windows → Mac** — generated an ed25519 keypair at `C:\Users\<user>\.ssh\id_ed25519` (the Windows-side path, since Cursor is a native Windows app and uses Windows' OpenSSH, not WSL's `~/.ssh`), and installed the public half into the Mac's `~/.ssh/authorized_keys`. `sshpass`/`expect` weren't available without a sudo password prompt blocking non-interactive install, so this was done via a quick Python (`paramiko`) script instead.
3. **Fixed a malformed SSH config** — Cursor's "Connect to Host" quick-add had written a bare `user@ip` line into `C:\Users\<user>\.ssh\config` with no `Host`/`HostName`/`User` keywords, which silently broke *every* SSH connection attempt (including plain `ssh.exe`) until rewritten with proper syntax.
4. **Cursor Remote-SSH → Mac**: confirmed working, passwordless.
5. **Python + TensorFlow-Metal on the Mac**: `tensorflow-macos` + `tensorflow-metal` installed in a venv, GPU confirmed detected (`tf.config.list_physical_devices('GPU')` → 1 device, as expected — Apple Silicon exposes the whole GPU as one logical device to TensorFlow regardless of core count).

## Hiccups hit along the way (worth knowing if debugging similar setup again)

- **WSL's network identity ≠ Windows' network identity.** Running `tailscale up` inside WSL only connects WSL's own virtual presence to the tailnet — it does *not* give the Windows host (or apps running natively on Windows, like Cursor) any route to other tailnet devices. Tailscale had to be installed a second time, natively on Windows, before Cursor could reach the Mac at all (symptom: `ssh.exe` gave `Connection timed out` even though WSL's `ssh`/`paramiko` could reach the same IP fine).
- **`/mnt/c/...` permission checks are unreliable from WSL.** `chmod 600` on a file under the Windows-mounted drive doesn't actually change anything OpenSSH cares about — WSL always reports it back as `777` regardless, because DrvFs doesn't map NTFS ACLs to POSIX bits. This makes WSL's own `ssh` unable to use a key stored there ("UNPROTECTED PRIVATE KEY FILE") even when Windows' native `ssh.exe` reading the exact same file is completely fine (it checks the real NTFS ACL, not the fake POSIX bits WSL shows). Lesson: test Windows-targeted SSH keys with Windows' own `ssh.exe` (`/mnt/c/Windows/System32/OpenSSH/ssh.exe`), not WSL's.
- **`sudo apt-get install sshpass` needs an interactive password** in this environment — worked around with `pip install --user paramiko` instead (no sudo needed) and a short Python script to push the public key over an already-password-authenticated SSH connection.

## Remaining steps, in order

1. **Pull the repo + submodules on the Mac** (this is what today's vault-logging is for):
   ```
   git pull
   git submodule update --init --recursive
   ```
2. **Download the actual SiMWiSense dataset onto the Mac** — from the Drive or IEEE DataPort link in `resources/SiMWiSense/README.md` — unzip as `Data/` at the `SiMWiSense/` repo root (`sudo unzip Data.zip`), matching the paths `main.py` and the Matlab scripts expect (`../Data/<test>/...`). This has **not been done yet** — nothing has actually been downloaded anywhere so far, this whole session was infra setup.
3. **Finish the SiMWiSense Phase-1 walkthrough**: read `create_csv.py`/`csv_main.py` specifically to resolve the open label-type-mismatch question flagged in [[01-progress]] §3 before trusting the FREL fine-tuning path.
4. **Design + implement the sanitization swap** (the actual experiment, per [[00-aim-and-plan]]):
   - Insert Wilight's null/pilot-prune → single-ratio → temporal-clean stages **before** SiMWiSense's `csi2batches` windowing step, on the full per-activity capture (not after windowing to 50 packets — the vote/temporal-clean steps need a longer stream to work statistically; see [[01-progress]] for why).
   - Decide whether to keep the **double** ratio pass or stop after single ratio — double ratio shrinks subcarrier count aggressively (256→~118→~59) and it's an open question whether that's still enough resolution for SiMWiSense's 20-class fine-grained CNN.
   - **Do not** port Wilight's Doppler/STFT stage — SiMWiSense's CNN wants a raw `Sp × K × 2` tensor, not a spectrogram.
   - Check Wilight's hardcoded null/pilot subcarrier indices against SiMWiSense's own pruning (`non_zero` in `CSI_extractor_SimWiSense.m`) before reusing them blindly — they come from different capture setups and likely don't line up subcarrier-for-subcarrier.
   - Write a glue step to repackage the ratio-cleaned complex output back into whatever format `dataGenerator.py`'s `read_mat`/`DataGenerator` expects (either save as `.mat` with a `csi_mon` field to match the existing convention, or adapt the data generator to read `.npz` directly), and update `NoOfSubcarrier`/`inputshape` to match the new, smaller subcarrier count.
5. **Run FREL** (`main.py <test> ... -tr -ft`) on the newly-sanitized data and compare against SiMWiSense's own baseline preprocessing.

## See also
- [[00-aim-and-plan]]
- [[01-progress]]
