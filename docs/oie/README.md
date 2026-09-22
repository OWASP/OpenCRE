# OpenCRE Integrated Ecosystem (OIE) — documentation

This directory describes how the OWASP Integrated Ecosystem maps standards into
Common Requirements Enumeration (CRE) nodes, how Module C (the Librarian)
decides automatic links, and how the B2 evaluation harness measures accuracy.

| Document | Contents |
|----------|----------|
| [How it works](how-it-works.md) | Pipeline stages A→B→C, retrieval and decision theory |
| [Evaluation and metrics](evaluation-and-metrics.md) | Exact Links bar vs CRE neighborhood soft bar |
| [Feature flags](feature-flags.md) | Promoted `CRE_LIBRARIAN_*` settings and how to reproduce |
| [Experimental feature flags](experimental-feature-flags.md) | Flags tried and not promoted — shipped as dead code (default off) |

Package-level API notes remain in
[`application/utils/librarian/README.md`](../../application/utils/librarian/README.md).
Operator steps for live drains are in
[`docs/gsoc_2026_module_c/runbook.md`](../gsoc_2026_module_c/runbook.md).
