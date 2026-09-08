---
tags: [paper, multi-person-sensing, wireless-sensing]
---
# SiMWiSense: Simultaneous Multi-Subject Activity Classification Through Wi-Fi Signals

> Haque, Zhang, Restuccia — IEEE WoWMoM 2023. First framework for simultaneous multi-subject Wi-Fi activity classification. Core idea: assign one CSI monitor per subject, positioned close to them, so physical proximity does the separation work; then solve the resulting combinatorial class-explosion and cross-environment generalization problems with a cascaded classifier and a new few-shot learning algorithm (FREL).

> **Reading map (7 levels):** L0 prerequisites from `basics/` → L1 sensing-proximity intuition → L2 the class-explosion problem → L3 system architecture → L4 cascaded detection → L5 FREL (few-shot learning) → L6 experimental results → L7 positioning/limitations.

## Level 0 — Prerequisites already covered in `basics/`

Nothing new to learn here — SiMWiSense's foundation is entirely material already in this vault, just relabeled.

**CSI tensor, from [[CSI-fundamentals]]:** the paper's CSI matrix (Eq. 1, $H^{m,n}_r$) is exactly the sampled-CFR object from that note, indexed per Tx/Rx antenna pair. Their $K$ (subcarriers) is [[CSI-fundamentals]]'s $J$; their $S$ samples over an interval $T$ is just a sequence of packets, same as index $i$ in [[CSI-sanitization]]'s notation. No new concept — just a different letter scheme for the same `[packets, subcarriers, antennas]` tensor, which they write as `[S, K, N]`.

**The physical mechanism, from [[scattering-model]]:** this is what the whole paper's premise rests on. Recall the scattering model's core equation — CSI is a sum of contributions from every scatterer in the room, static and dynamic:

$$H(f,t) = \sum_{o \in \Omega_s(t)} H_o(f,t) + \sum_{p \in \Omega_d(t)} H_p(f,t)$$

SiMWiSense's entire premise is one specific consequence of this: place a monitor *close* to one particular dynamic scatterer (a person), and that person's term in the sum overwhelmingly dominates the contributions from everyone/everything else in the room — not for any exotic reason, just because signal strength falls off with distance, so a near dynamic scatterer's contribution is much larger than a far one's. SiMWiSense turns this physical fact into a system design decision: *put one device per subject, close to them, and let physical proximity do the separation work, instead of asking an algorithm to untangle a mixed multi-subject signal.*

**Baseline CNN, from [[wireless-sensing-DL]]:** their "baseline CNN" (Section III-C, Fig. 8) is the same recipe as [[wireless-sensing-DL]] §2 — conv layers, batch norm, ReLU, max pooling, global average pooling into a latent embedding. No new architecture here; it's the same CNN pattern applied to CSI, used as a feature extractor whose output feeds a separate classifier head (this separation of embedding-network from classifier becomes important once FREL enters at Level 5).

**What's genuinely new starts at Level 1:** the systems-level problem — proving proximity actually works, and handling the multi-subject class explosion — followed later by few-shot/meta-learning (Level 5), a completely new ML topic not yet in this vault.

## Up next

→ [[SiMWiSense-sensing-proximity|Level 1 — Sensing Proximity]]

## See also
- [[CSI-fundamentals]]
- [[scattering-model]]
- [[wireless-sensing-DL]]
- [[MUSE-Fi]] — the same near-scatterer-domination physics, applied through the opposite deployment topology (personal device vs. dedicated monitor)
