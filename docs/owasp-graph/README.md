# OWASP Graph (Project OIE)

Living-knowledge ETL for OWASP content: harvest → filter → link → human review.

| Doc | Purpose |
| --- | --- |
| [RFC: Pane of Glass](../designs/owasp-pane-of-glass.md) | Motivation, four modules, experiments |
| [APIs & handovers](./apis/README.md) | Contracts between modules |

## Pipeline (logical)

```
Module A              Module B           Module C              Module D
(Harvest+chunk)  →    (Filter)      →    (Librarian)      →    (HITL)
Ingest Bucket         Knowledge            Link proposals         Human
(chunks)              Queue                + review flags         corrections
```

Module A **backfills** new artifacts (full read + chunk) and **incrementally** updates known ones. Each **chunk** is the unit Module B classifies and Module C links to CREs.

Handovers are versioned JSON (MVP: object storage / JSONL).
