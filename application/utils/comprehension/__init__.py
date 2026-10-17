"""Ingestion-time comprehension: derive cited digests/claims from harvested sources.

See docs/oie/comprehension-design.md. Nothing here is hand-curated: every
statement is extracted by an LLM from harvested text and carries the source
artifact it came from; level-1 claims are additionally quote-verified.
"""
