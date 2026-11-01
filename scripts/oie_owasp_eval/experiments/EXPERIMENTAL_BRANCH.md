# Experimental feature flags

Non-promoted B2 experiment configs. Defaults stay **off**; do not enable in
production. Research write-up: `docs/oie/experimental-feature-flags.md`.

Promoted stack: `stack_winners.yaml` (`CRE_SUMMARY=1`, `MARGIN_GAMMA=0.85`).

Removed experiments (`rrf`, `context_enrich`) are preserved on the
`staging-experiments` branch; the RRF implementation is on
`exp/dual-index-and-name-packer`. Historical research branch:
`experimental-feature-flags`.
