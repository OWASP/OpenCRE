"""Module C.3 — confidence calibration (Week 5).

C.2 (the cross-encoder, W4) emits a raw ranking logit per candidate — great for
ordering, meaningless as confidence (a +1.5 is not "82% sure"). C.3 turns that
logit into an honest probability via **temperature scaling**: ``p = sigmoid(z/T)``
with a single scalar ``T`` fit by negative-log-likelihood on the golden set, and
proves the result honest with **ECE < 0.10**.

The W6 decision engine thresholds that probability (auto-link vs. human review),
so calibration is what makes the threshold trustworthy. Kept dependency-light
(numpy + scipy) and model-free so it stays hermetically testable — mirrors the
C.1/C.2 seams.
"""
