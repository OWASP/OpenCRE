"""Module B: Noise / Relevance Filter for the OpenCRE Scraper & Indexer (Project OIE).

This package consumes records emitted by Module A (Information Harvesting), filters
out noise via a two-stage pipeline (regex on paths -> LLM classifier on text), and
writes accepted security-knowledge chunks to a queue that Module C (The Librarian)
maps to CRE nodes.

Pipeline stages:
    1.   regex_filter.py   -- path/extension exclusions
    1.5  sanitize.py       -- defensive text normalization (vendored from TRACT)
    2.   llm_classifier.py -- LiteLLM-backed classification via PromptHandler

Data contracts:
    Input:  Module A's JSONL records (schema in `schemas.ChangeRecord`)
            Specification: docs/gsoc_2026_module_b/module_a_contract.md
    Output: knowledge_queue table rows (model `KnowledgeQueueItem` in
            application/database/db.py; Module C contract in
            docs/gsoc_2026_module_b/module_c_contract.md)
"""
