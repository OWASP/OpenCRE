# Scaling OpenCRE's Harvester: Weeks 7-12 — Semantic Chunking to Handoff (Corrected)

**Author:** Parth Aggarwal  
**Project:** OpenCRE Scraper & Indexer (OIE) — Module A  
**Timeline:** July 13 – Aug 31, 2026  
**Status:** Ready for Module B integration testing

**Prerequisite:** Read [Week 1-6: Building the Foundation](#blog1) first.

---

## From Documents to Chunks: The Architecture

Weeks 1-6 got us to **Documents**: complete file content with heading structure, persisted to `harvest_input` table.

Weeks 7-12 would transform Documents into **IngestChunkRecords**: semantically meaningful chunks ready for Module B's classifier.

But here's the thing: **Week 7 actually defers to Week 8**. The real work starts with semantic chunking.

---

## Week 7: Checkpoint Persistence & State Management

**Timeline:** July 13 – July 19  
**Goal:** Make nightly runs resumable at the repo level  
**Deliverables:** CheckpointStore (DB-backed)

### Checkpoint Architecture

Week 2 introduced checkpoints in-memory. Week 7 **persists them to the database**:

```python
# Week 7: CheckpointStore (database-backed)
@dataclass
class Checkpoint:
    repo: str  # "OWASP/ASVS"
    pipeline_run_id: str  # "20260201T020000Z"
    last_processed_commit: str  # Latest commit we processed
    status: str  # "in_progress" | "completed" | "failed"
    timestamp: datetime

class CheckpointStore:
    """Persist checkpoints to database for resumability."""
    
    def get_latest(self, repo: str) -> Optional[Checkpoint]:
        """Get latest checkpoint for repo."""
        row = db.query(CheckpointTable).filter(
            CheckpointTable.repo == repo
        ).order_by(CheckpointTable.timestamp.desc()).first()
        
        return Checkpoint(**row) if row else None
    
    def update(self, checkpoint: Checkpoint):
        """Insert or update checkpoint."""
        db.session.merge(CheckpointTable.from_checkpoint(checkpoint))
        db.session.commit()

# Usage in pipeline
checkpoint_store = CheckpointStore()
checkpoint = checkpoint_store.get_latest("OWASP/ASVS")

if checkpoint and checkpoint.status == "completed":
    # Resume from last successful commit
    base_commit = checkpoint.last_processed_commit
    logger.info(f"Resuming {repo} from {base_commit}")
else:
    # First run or interrupted
    base_commit = get_default_base_commit(repo)
    logger.warning(f"Starting {repo} from {base_commit}")

# Run pipeline
for doc in pipeline.process(repo, base_commit):
    harvest_input.write(doc)

# Mark completed
checkpoint_store.update(Checkpoint(
    repo=repo,
    pipeline_run_id=pipeline_run_id,
    last_processed_commit=latest_commit,
    status="completed"
))
```

### Artifact Registry: In-Memory Only

**Important clarification:** `ArtifactRegistry` (Week 5) remains **in-memory only**. It's not persisted to the database.

```python
# Week 5-7: ArtifactRegistry (in-memory cache)
class ArtifactRegistry:
    """In-process dedup cache."""
    
    def __init__(self):
        self._cache = {}  # artifact_id -> ArtifactRecord
    
    def has_seen(self, artifact_id: str, content_hash: str) -> bool:
        """Has this content already been processed?"""
        if artifact_id not in self._cache:
            return False
        
        stored = self._cache[artifact_id]
        return stored.content_hash == content_hash
    
    def record(self, artifact_id: str, content_hash: str):
        """Remember this artifact."""
        self._cache[artifact_id] = ArtifactRecord(
            artifact_id=artifact_id,
            content_hash=content_hash,
            last_seen=datetime.now()
        )

# Usage
artifact_registry = ArtifactRegistry()

for doc in harvest_input.read():
    content_hash = sha256(doc.full_text)
    
    if artifact_registry.has_seen(doc.artifact_id, content_hash):
        logger.info(f"SKIP: {doc.artifact_id} unchanged")
        continue
    
    artifact_registry.record(doc.artifact_id, content_hash)
    # Process to Week 8
```

**Why in-memory?**
- Fast (no DB overhead)
- Sufficient for single nightly run
- Resets each run (fresh dedup check)
- DB checkpoints handle multi-run resumability

**Key difference:**
- **CheckpointStore (DB):** "Which commit did last night's run finish at?"
- **ArtifactRegistry (in-memory):** "Did we already process this exact file content in THIS run?"

**Week 7 learnings:**
- ✅ Checkpoint persistence enables nightly resumability
- ✅ In-memory artifact cache is fast enough
- ✅ Two-layer tracking (commits vs content) handles both cases

---

## Week 8: LlamaIndex Semantic Chunking

**Timeline:** July 20 – July 26  
**Goal:** Transform Documents into IngestChunkRecords  
**Deliverables:** Chunk generation, chunk_id generation (index-based)

### Semantic Chunking Strategy

Documents come in with full file content and heading structure. Now we chunk them **semantically**:

```python
from llama_index.core.text_splitter import SemanticSplitter
from llama_index.embeddings.openai import OpenAIEmbedding

class SemanticChunkingConfig:
    chunk_size: int = 1024  # Target chars
    chunk_overlap: int = 20  # Context overlap
    embedding_model: str = "text-embedding-3-small"
    breakpoint_percentile_threshold: int = 95

# Week 8: Initialize splitter
embedding_model = OpenAIEmbedding(model="text-embedding-3-small")
splitter = SemanticSplitter(
    chunk_size=1024,
    chunk_overlap=20,
    breakpoint_percentile_threshold=95,
    embedding_model=embedding_model,
)

def chunk_document(doc: Document) -> List[IngestChunkRecord]:
    """
    Split Document into semantic chunks.
    
    Input: Document with full_text + heading_structure
    Output: IngestChunkRecord[] with chunk_id = index-based
    """
    
    # LlamaIndex splits text into semantically coherent chunks
    chunks = splitter.split_text(doc.full_text)
    
    records = []
    for index, chunk_text in enumerate(chunks):
        # chunk_id is INDEX-BASED, not content-addressed
        chunk_id = f"chk:{doc.artifact_id}:{index}"
        
        # Infer heading context for this chunk
        heading_path = infer_heading_path(chunk_text, doc.heading_structure)
        
        # Build complete record
        record = IngestChunkRecord(
            schema_version="0.2.0",
            chunk_id=chunk_id,  # chk:art:OWASP/ASVS:...:0
            artifact_id=doc.artifact_id,
            pipeline_run_id=doc.pipeline_run_id,
            text=chunk_text,
            span=SpanInfo(
                index=index,
                total=len(chunks),
                heading_path=heading_path,
                start_char_idx=calculate_start_char(doc.full_text, chunk_text),
                end_char_idx=calculate_end_char(doc.full_text, chunk_text),
                start_line=calculate_start_line(doc.full_text, chunk_text),
                end_line=calculate_end_line(doc.full_text, chunk_text),
            ),
            source=doc.source,
            locator=doc.locator,
        )
        
        records.append(record)
    
    return records
```

### chunk_id Format: Index-Based

**Critical clarification:** chunk_id is **NOT content-addressed**. It's **index-based**:

```
chunk_id = chk:{artifact_id}:{index}

Examples:
  chk:art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md:0
  chk:art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md:1
  chk:art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md:2
```

**What this means:**
- Chunks are identified by position, not content
- Same artifact always generates chunks 0, 1, 2, 3... (in order)
- Chunk text can change without changing chunk_id (unlike content-addressed)
- Module B applies its own content hashing for dedup

**Why not content-addressed?**
- Simpler to reason about
- Doesn't explode on small edits
- Module B handles dedup via its own content hash

### Heading Path Inference

Each chunk belongs to a heading context:

```python
def infer_heading_path(chunk_text: str, heading_structure: List[HeadingNode]) -> List[str]:
    """Map chunk to its heading context."""
    
    # Find which heading section this chunk belongs to
    # (simplified; real implementation finds best match)
    
    for heading in heading_structure:
        if chunk_text.startswith(heading.text) or contains_section(heading, chunk_text):
            path = [heading.text]
            for child in heading.children:
                if contains_section(child, chunk_text):
                    path.append(child.text)
            return path
    
    return ["Uncategorized"]

# Example output
heading_path = ["V3", "Authentication", "MFA"]
```

**Week 8 learnings:**
- ✅ LlamaIndex semantic splitting works well
- ✅ Index-based chunk_id is simpler than content-addressed
- ✅ Heading context is critical for downstream understanding
- ❌ Embedding API calls add latency (mitigation: cache embeddings)

---

## Week 9: Database Storage & Handoff

**Timeline:** July 27 – Aug 2  
**Goal:** Persist IngestChunkRecords to database  
**Deliverables:** Database schema, validation, Module B handoff

### Storage Layer: Database-Backed

IngestChunkRecords are written to a database table for Module B to consume:

```python
class IngestChunkRecordRow(BaseModel):
    """Database persistence of IngestChunkRecord."""
    __tablename__ = "ingest_chunk_records"
    
    id = Column(String, primary_key=True)
    
    # RFC fields (complete)
    schema_version = Column(String, nullable=False)
    chunk_id = Column(String, nullable=False, unique=True, index=True)
    artifact_id = Column(String, nullable=False, index=True)
    pipeline_run_id = Column(String, nullable=False, index=True)
    
    # Content + boundaries
    text = Column(Text, nullable=False)
    span = Column(Text, nullable=False)  # JSON: {index, total, heading_path, ...}
    
    # Provenance
    source = Column(Text, nullable=False)  # JSON: {type, repo, commit_sha, ...}
    locator = Column(Text, nullable=False)  # JSON: {kind, id, path}
    
    created_at = Column(DateTime, default=now(), index=True)
    
    __table_args__ = (
        UniqueConstraint("chunk_id", name="uq_chunk_id"),
        Index("ix_by_artifact", "artifact_id"),
        Index("ix_by_run", "pipeline_run_id"),
    )

# Writing records
def emit_chunks(records: List[IngestChunkRecord], db):
    """Persist validated IngestChunkRecords to database."""
    
    for record in records:
        # Validate RFC compliance
        if not validate_rfc_record(record):
            logger.error(f"RFC validation failed: {record.chunk_id}")
            continue
        
        row = IngestChunkRecordRow(
            schema_version=record.schema_version,
            chunk_id=record.chunk_id,
            artifact_id=record.artifact_id,
            pipeline_run_id=record.pipeline_run_id,
            text=record.text,
            span=json.dumps(record.span.model_dump()),
            source=json.dumps(record.source.model_dump()),
            locator=json.dumps(record.locator.model_dump()),
        )
        
        db.session.add(row)
    
    db.session.commit()
```

### Validation: RFC Compliance

Before writing, every record must pass validation:

```python
def validate_rfc_record(record: IngestChunkRecord) -> bool:
    """Ensure RFC compliance."""
    
    checks = [
        (record.schema_version == "0.2.0", "schema_version must be 0.2.0"),
        (record.chunk_id.startswith("chk:"), "chunk_id format"),
        (record.artifact_id.startswith("art:"), "artifact_id format"),
        (len(record.text.strip()) >= 10, "text too short"),
        (record.span.index < record.span.total, "span.index >= total"),
        (len(record.span.heading_path) > 0, "heading_path empty"),
        (record.source.type == "github", "source.type must be github"),
        (len(record.source.commit_sha) == 40, "commit_sha length"),
    ]
    
    for check, reason in checks:
        if not check:
            logger.error(f"Validation failed: {reason}")
            return False
    
    return True
```

### Module B Handoff

Module B reads from this table:

```sql
-- Module B's query (Week 5 pipeline)
SELECT id, chunk_id, artifact_id, pipeline_run_id, text, span, source, locator
FROM ingest_chunk_records
WHERE created_at >= ?  -- Recent records
ORDER BY created_at
LIMIT 100;  -- Batch processing
```

**Week 9 learnings:**
- ✅ Database tables enable queryability and resumability
- ✅ JSON columns store complex RFC fields cleanly
- ✅ Indexes on chunk_id, artifact_id, pipeline_run_id speed up Module B queries
- ✅ Validation gates prevent RFC violations from reaching Module B

---

## Weeks 10-12: Testing, Documentation, Observability

**Timeline:** Aug 3 – Aug 31  
**Goal:** Production-readiness  
**Focus:** Testing strategy, logging, docs

### Testing Architecture

Three tiers of testing:

**Tier 1: Unit Tests**
- Test individual functions in isolation
- Mock external dependencies (git, database)
- Focus: correctness of logic

**Tier 2: Integration Tests**
- Test component interactions
- Example: git sync → change detection → document building
- Use small test repositories

**Tier 3: End-to-End Tests**
- Full pipeline: Week 1 config → Week 9 database write
- Use real (small) OWASP repositories
- Validate RFC compliance

```python
# Example Tier 3 test
def test_e2e_pipeline():
    """Full pipeline: config → database."""
    
    config = load_config("test_repos.yaml")
    runner = HarvesterRunner(config)
    
    # Run pipeline
    results = runner.run()
    
    # Validate
    assert results.documents_processed > 0
    assert results.chunks_generated > 0
    
    # Check database
    records = db.query(IngestChunkRecordRow).all()
    for record in records:
        assert validate_rfc_record(record)
    
    assert len(records) == results.chunks_generated
```

**Current test status:** 126 passing tests (unit + integration)

### Structured Logging

Every significant event logs structured JSON:

```python
# Example logs
logger.info({
    "event": "pipeline_started",
    "pipeline_run_id": "20260201T020000Z",
    "repos": ["OWASP/ASVS", "OWASP/CheatSheetSeries"],
    "timestamp": "2026-02-01T02:00:00Z"
})

logger.info({
    "event": "repository_processed",
    "repo": "OWASP/ASVS",
    "files_changed": 3,
    "files_processed": 2,
    "files_skipped": 1,
    "timestamp": "2026-02-01T02:15:00Z"
})

logger.info({
    "event": "document_chunked",
    "artifact_id": "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md",
    "chunks_generated": 3,
    "avg_chunk_size": 1024,
    "timestamp": "2026-02-01T02:20:00Z"
})
```

Structured logs enable:
- Cost tracking (API calls, tokens)
- Performance monitoring
- Debugging specific runs
- Anomaly detection

---

## Current Architecture (Week 12)

```
GitHub Actions (nightly)
    ↓
Week 1-2: Config, Clone, Checkpoints
    ↓ git log + checkpoint resume
Change Detection & Filtering
    ↓ git show HEAD:path (read complete files)
Week 5: Content Hashing (in-memory ArtifactRegistry)
    ↓ dedup within run
Week 6: Document Building
    ↓ harvest_input table (Documents with full_text + headings)
Week 8: Semantic Chunking (LlamaIndex)
    ↓ chk:artifact_id:index format
Week 9: IngestChunkRecords to Database
    ↓ ingest_chunk_records table
Module B Ready to Consume
```

---

## Configuration & Scope (Current)

```yaml
# repos.yaml (Week 1-6)
sources:
  - type: github
    repo: OWASP/ASVS
    default_branch: master
  
  - type: github
    repo: OWASP/CheatSheetSeries
    default_branch: master
```

**Only 2 repositories configured.** Future expansion (WSTG, Top10) will use the same schema.

---

## What Worked

- ✅ Semantic chunking respects structure and content
- ✅ Index-based chunk_id is simpler than content-addressed
- ✅ Database-backed storage enables Module B integration
- ✅ Checkpoint persistence makes nightly runs resilient
- ✅ RFC validation gates catch issues early
- ✅ Testing tiers (unit → integration → E2E) build confidence

---

## What Was Hard

- ❌ LlamaIndex embedding latency (mitigation: caching)
- ❌ Heading extraction edge cases
- ❌ Coordinating database schema with Module B
- ❌ Deciding on index-based vs content-addressed chunk_id
- ❌ Balancing in-memory caching vs DB persistence

---

## Metrics (Actual)

```
Testing:
  Unit + Integration tests: 126 passing
  Test coverage: TBD (measure in final)
  
Repositories configured: 2 (ASVS, CheatSheetSeries)

Schema compliance: All records validated against RFC before persistence
```

---

## The Production Handoff

By Week 12, Module A is ready for **integration testing with Module B**.

The pipeline:
1. Detects changed files (git log)
2. Reads complete files (git show)
3. Deduplicates content (in-memory)
4. Builds documents (heading extraction)
5. Chunks semantically (LlamaIndex)
6. Generates index-based chunk_ids
7. Validates RFC compliance
8. Persists to database
9. Waits for Module B to consume

All nightly. All resumable from checkpoints. All logged.

---

## Looking Ahead

**Immediate (Next weeks):**
- Joint A→B integration tests with Manshu
- Validate Module B can consume all IngestChunkRecords
- Fine-tune semantic chunk boundaries
- Monitor embedding API costs

**Future (Post-GSoC):**
- Add more source repositories
- Optimize embedding caching
- Add parallel processing
- Build observability dashboard
- Implement semantic mapping (if Module C proposes it)

---

## Thank You

To Spyros and Paola (mentors), Manshu (Module B), and Prateek (Module C): this wouldn't have shipped without your feedback on schema, coordination on handoffs, and patience through the pivots.

To the OpenCRE community: your repos made this real.

---

*Code: [GitHub PR #725 → PR #735](https://github.com/OpenCRE/OpenCRE). Architecture docs: `docs/gsoc_2026_module_a/`. First production nightly run: Sept 1, 2026.*

*Next: Module B integration testing and classifier evaluation.*
