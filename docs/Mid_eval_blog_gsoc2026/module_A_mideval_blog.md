# Building OpenCRE's Harvester: Weeks 1-6 — From Config to Semantics (Corrected)

**Author:** Parth Aggarwal  
**Project:** OpenCRE Scraper & Indexer (OIE) — Module A  
**Timeline:** May 25 – July 5, 2026  
**Status:** Foundation complete, moving to semantic chunking

---

## The Challenge

OWASP maintains critical security knowledge across multiple GitHub repositories. Our goal: **build an automated harvester that runs nightly, detects file changes, reads complete file content, validates it semantically, and emits queryable records for Module B's classifier**.

The system had to be:
- **Deterministic**: Same repo state → same output every time
- **Resumable**: Crash mid-run? Pick up where you left off
- **Incremental**: Only process changed files, not the entire repo
- **Production-ready**: Handle edge cases, retry failures, log everything

This is the story of the first 6 weeks—the foundation that makes this possible.

---

## Week 1-2: Configuration & Git Foundation

**Timeline:** May 25 – June 7  
**Goal:** Config loader + incremental git operations  
**Reality:** Three critical decisions locked in

### The repos.yaml Schema Decision

We started with: "How should we configure which repos to harvest?"

**Option A (Minimal):**
```yaml
repos:
  - OWASP/ASVS
  - OWASP/CheatSheetSeries
```

**Option B (Extensible):**
```yaml
schema_version: "0.2.0"
sources:
  - type: github
    repo: OWASP/ASVS
    default_branch: master
    paths_include: ["**/*.md"]
    paths_exclude: ["**/package-lock.json"]
```

We chose **Option B** because:
- Future sources (RSS, static sites) need a common interface
- Path inclusion/exclusion prevents noise at the config layer
- Version tracking allows schema evolution

**Current configuration (as of Week 6):**
```yaml
# repos.yaml (actual)
sources:
  - type: github
    repo: OWASP/ASVS
    default_branch: master
    
  - type: github
    repo: OWASP/CheatSheetSeries
    default_branch: master
```

Just two repos so far. Future additions (WSTG, Top10) will follow the same schema.

### Git Operations: Shallow Clone + Checkpoint Tracking

**Week 2's key decision:** How to handle incremental updates?

We implemented **shallow cloning** with **checkpoint tracking**:

```python
# Week 2: Shallow clone for speed
result = subprocess.run(
    ["git", "clone", "--depth=1", repo_url],
    cwd=clone_dir,
    timeout=60
)
# Result: ~50MB for ASVS (vs 1.2GB full clone)

# Week 2: Checkpoint tracking for resumability
@dataclass
class Checkpoint:
    repo: str  # "OWASP/ASVS"
    pipeline_run_id: str  # "20260201T020000Z"
    last_processed_commit: str  # Resume point
    status: str  # "in_progress" | "completed" | "failed"

# On next run: Resume from checkpoint
checkpoint = checkpoint_store.get_latest("OWASP/ASVS")
if checkpoint and checkpoint.status == "completed":
    # Scan since last completed checkpoint
    git_log = subprocess.run(
        ["git", "log", f"{checkpoint.last_processed_commit}..HEAD", "--name-only"]
    )
else:
    # Interrupted run; recover or restart
    git_log = recover_or_restart(checkpoint)
```

**Why this matters:** Checkpoints allow runs to resume from a stored commit. However, the current pipeline advances the checkpoint before chunk construction and output persistence, so failures afterward can cause changes to be skipped on retry.

**Week 1-2 learnings:**
- ✅ Extensible config schema prevents rework later
- ✅ Shallow clones cut repo size by 95%+
- ✅ Checkpoint tracking supports resumption, but advancing the checkpoint before output persistence can cause changes to be skipped after a failure
- ❌ Shallow clones break some git operations; need careful command selection

---

## Week 3-4: Change Detection & Filtering

**Timeline:** June 8 – June 21  
**Goal:** Detect changed files, apply noise filters  
**Reality:** Regex filtering works, but the pipeline isn't diff-based

### How Change Detection Actually Works

The current pipeline compares the stored checkpoint with `HEAD` using `git diff --name-only`. On the first run, it uses the empty tree as the comparison point.

It reads complete file contents rather than diffs because heading extraction and downstream processing require full-file context.

```python
# Illustrative flow; see ChangeDetector and pipeline.py for implementation.
changed_files = detect_changed_files(checkpoint_commit, head_commit)

for file_path in changed_files:
    complete_file_content = read_file_at_commit(head_commit, file_path)



```python
deny_extensions = [".css", ".scss", ".png", ".lock", ".map"]
deny_filenames = ["package-lock.json", "_config.yml", ".gitignore"]
deny_paths = ["node_modules/**", "dist/**", "tests/**"]

def is_noise(file_path: str) -> bool:
    """Reject files matching configured noise patterns."""
    filename = file_path.rsplit("/", 1)[-1]

    if filename in deny_filenames:
        return True

    if any(file_path.endswith(ext) for ext in deny_extensions):
        return True

    path_parts = file_path.split("/")

    if any(
        fnmatch.fnmatch(file_path, pattern)
        or any(fnmatch.fnmatch(part, pattern.rstrip("/**")) for part in path_parts)
        for pattern in deny_paths
    ):
        return True

    return False
```

### Regex Filtering: The 90% Win

Before processing files, we apply regex filters:

```python
# Week 3: Noise patterns (data-driven)
deny_extensions = [".css", ".scss", ".png", ".lock", ".map"]
deny_filenames = ["package-lock.json", "_config.yml", ".gitignore"]
deny_paths = ["node_modules/**", "dist/**", "tests/**"]

def is_noise(file_path: str) -> bool:
    """Quick rejection filter."""
    for pattern in deny_extensions:
        if file_path.endswith(pattern):
            return True
    
    for pattern in deny_paths:
        if fnmatch.fnmatch(file_path, pattern):
            return True
    
    return False

# Result: ~90% of files rejected before reading from disk
# Only Markdown docs proceed to parsing
```

**Testing showed:** Regex filters catch most noise early, reducing computational load downstream.

**Week 3-4 learnings:**
- ✅ Checkpoint-to-HEAD change detection identifies changed files
- ✅ Regex filtering at config time (not runtime) is efficient
- ✅ Reading complete files (not diffs) enables full-file understanding
- ❌ Had to reconsider RFC diff parsing section; actual pipeline reads files at HEAD

---

## Week 5: Content Hashing & Artifact Registry

**Timeline:** June 22 – June 28  
**Goal:** Dedup at artifact level  
**Reality:** Both artifact-level and chunk-level hashing remain

### Content Hashing: Still Necessary

Early RFC planning considered dropping `content_hash`. **We didn't.**

Here's why:

```python
# Week 5: Artifact registry (in-memory during run)
@dataclass
class ArtifactRecord:
    artifact_id: str  # "art:OWASP/ASVS:4.0/en/0x12-V3-Authentication.md"
    content_hash: str  # sha256(normalized_file_content)
    last_seen_commit: str
    status: str  # "new" | "unchanged" | "updated"

artifact_registry = {}

def should_process_file(artifact_id: str, file_content: str) -> bool:
    """Has this file's content already been processed?"""
    current_hash = sha256(file_content)
    
    stored = artifact_registry.get(artifact_id)
    if not stored:
        return True  # New file
    
    if current_hash == stored["content_hash"]:
        return False  # Identical content, skip
    
    return True  # Content changed, reprocess

```


**Important:** `should_process_file()` only decides whether to process a file; it does not update the registry. The caller records the artifact's new content hash after processing succeeds.


**Why keep artifact-level hashing?**
- Detects when file content is identical despite cosmetic changes
- Avoids re-chunking if file hasn't actually changed
- In-process optimization (single nightly run)

**Module B also computes hashes:**
- B has its own content hash for dedup at the chunk queue level
- Different layer, different purpose

**Week 5 learnings:**
- ✅ Content hashing is simple but effective
- ✅ Works best as in-memory cache (not persisted)
- ✅ Different systems can use different hashing strategies (A: artifact-level, B: chunk-level)

---

## Week 6: Document Building & Structured Output

**Timeline:** June 29 – July 5  
**Goal:** Assemble RFC-ready documents  
**Reality:** First complete end-to-end test of the pipeline

### Building Documents from Files

After reading a complete file, we extract structure:

```python
# Week 6: Document builder
@dataclass
class Document:
    artifact_id: str
    pipeline_run_id: str
    schema_version: str
    source: SourceInfo
    locator: LocatorInfo
    full_text: str
    heading_structure: List[HeadingNode]

def build_document(
    file_path: str,
    file_content: str,
    repo: str,
    commit_sha: str,
    pipeline_run_id: str
) -> Document:
    """Assemble a Document with RFC fields."""
    
    artifact_id = f"art:{repo}:{file_path}"
    
    # Normalize text
    normalized = normalize_text(file_content)
    
    # Extract heading structure
    headings = extract_headings(normalized)
    
    return Document(
        artifact_id=artifact_id,
        pipeline_run_id=pipeline_run_id,
        schema_version="0.2.0",
        source=SourceInfo(
            type="github",
            repo=repo,
            commit_sha=commit_sha,
            committed_at=datetime.now().isoformat()
        ),
        locator=LocatorInfo(
            kind="repo_path",
            id=file_path,
            path=file_path
        ),
        full_text=normalized,
        heading_structure=headings
    )
```

### Heading Extraction

Markdown structure matters. We parse it:

```python
# Week 6: Extract heading hierarchy
def extract_headings(text: str) -> List[HeadingNode]:
    """Parse Markdown headings and nesting."""
    lines = text.split('\n')
    headings = []
    stack = []
    
    for line_num, line in enumerate(lines):
        match = re.match(r'^(#+)\s+(.+)$', line)
        if not match:
            continue
        
        level = len(match.group(1))  # Number of # symbols
        heading_text = match.group(2)
        
        node = HeadingNode(
            text=heading_text,
            level=level,
            start_line=line_num,
            end_line=line_num,
            children=[]
        )
        
        # Pop stack to correct nesting level
        while stack and stack[-1].level >= level:
            stack.pop()
        
        # Add to parent or root
        if stack:
            stack[-1].children.append(node)
        else:
            headings.append(node)
        
        stack.append(node)
    
    return headings
```

**Example structure:**
```
V3 Authentication (level 2)
  ├─ MFA (level 3)
  ├─ Password Storage (level 3)
  │   ├─ Hashing Algorithms (level 4)
  │   └─ Salt Length (level 4)
  └─ Session Management (level 3)
```

This hierarchy becomes critical in Week 8 for semantic understanding.

### Database Write: harvest_input Table

By Week 6, the pipeline writes validated Documents to a database table:

```python
# Week 6: Store document for Week 8 to process
class HarvestInputRow(BaseModel):
    __tablename__ = "harvest_input"
    
    id = Column(String, primary_key=True)
    artifact_id = Column(String, nullable=False, unique=True)
    pipeline_run_id = Column(String, nullable=False)
    
    # RFC fields
    schema_version = Column(String, nullable=False)
    source_type = Column(String, nullable=False)  # "github"
    source_repo = Column(String, nullable=False)
    source_commit_sha = Column(String, nullable=False)
    source_committed_at = Column(String, nullable=False)
    
    locator_kind = Column(String, nullable=False)
    locator_id = Column(String, nullable=False)
    locator_path = Column(String, nullable=False)
    
    # Content
    full_text = Column(Text, nullable=False)
    heading_structure = Column(Text, nullable=False)  # JSON
    
    created_at = Column(DateTime, default=now())

# Writing Documents
for doc in documents:
    row = HarvestInputRow.from_document(doc)
    db.session.add(row)

db.session.commit()
```

This describes the intended staged handoff. In the current implementation, `_harvest_repository` chunks documents before calling `write_harvest_input()`.

**Week 6 learnings:**
- ✅ Database-backed handoff (not JSONL) enables traceability
- ✅ Heading extraction enables semantic context
- ✅ First complete pipeline validation (A reads → B can consume)

---

## Summary: Week 1-6 Foundation

By end of Week 6:

```
┌─────────────────────────────────────────────┐
│ GitHub Actions (nightly, 02:00 UTC)        │
└─────────────────┬───────────────────────────┘
                  │
    Week 1-2: Config, Clone, Checkpoints
         ↓ shallow clone + checkpoint resume
    
    Week 3-4: Change Detection, Filtering
         ↓ checkpoint-to-HEAD comparison + pattern filters
    
    Week 5: Content Hashing, Artifact Registry
         ↓ dedup at artifact level (in-memory)
    
    Week 6: Document Building, DB Write
         ↓ harvest_input table with full_text + heading_structure
    
              Ready for Week 8
```

**Current scope:**
- 2 repositories configured: ASVS, CheatSheetSeries
- Incremental detection: changed files between the stored checkpoint and HEAD
- Noise filtering: ~90% rejection via regex
- Content hashing: artifact-level dedup within run
- Database: harvest_input table persists documents

**Not yet implemented:**
- Semantic chunking (Week 8)
- chunk_id generation (Week 8)
- JSONL/storage emission (Week 9)

---

## What Worked

- ✅ Extensible config schema
- ✅ Shallow clones + checkpoints for efficiency
- ✅ Reading complete files (not diffs) for context
- ✅ Regex filtering at config layer
- ✅ In-memory artifact registry for dedup
- ✅ Heading extraction for semantic understanding
- ✅ Database-backed handoff to downstream

---

## What Was Hard

- ❌ Git operations are finicky (shallow clones, commit tracking)
- ❌ Heading extraction edge cases (weird Markdown nesting)
- ❌ Locking on 2 repos instead of planning for scalability
- ❌ Underestimated complexity of incremental detection

---

## Blockers Cleared by Week 6

| Blocker | Status | Solution |
|---------|--------|----------|
| Config schema | ✅ Locked | Extensible YAML with sources |
| Git operations | ✅ Working | Shallow clone + checkpoints |
| Change detection | ✅ Working | Checkpoint-to-HEAD comparison |
| Noise filtering | ✅ Working | Regex patterns at config |
| File reading | ✅ Working | git show HEAD:path |
| Document structure | ✅ Working | Heading extraction |
| DB persistence | ✅ Working | harvest_input table |

---

Looking ahead: [Week 7–12: From Documents to Chunks →](../Final_eval_blog_gsoc2026/module_A_final_blog.md)

*Next: Config-driven chunking, index-based `chunk_id` generation, and database-backed storage.*
