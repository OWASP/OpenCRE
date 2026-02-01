# RFC: The OpenCRE Scraper & Indexer (Project OIE)

| Meta              | Details                                  |
| :---------------- | :--------------------------------------- |
| **Status**        | `Draft` / `Review Pending`               |
| **Target System** | OpenCRE.org / OWASP Chatbot              |
| **Focus**         | Automation, Knowledge Graph, Low-Ops ETL |
| **Authors**       | Spyros Gasteratos                        |
| **Date**          | 2026-02-01                               |
---

## 1. Context & Motivation

**Problem Statement**
OWASP produces an immense amount of high-value security knowledge, but it is fragmented.
A developer looking for "JWT Security" might find a *Cheat Sheet*, but miss the corresponding *ASVS* requirement, *Testing Guide* techniques, and relevant *AppSec Global* talks that explain a bypasses and defences.

**Current State**
OpenCRE currently maps standards (NIST, ISO, OWASP) well.
However, it fails to capture the "living" knowledge of the community—repo updates, new chapters, events, and blog posts.

**Proposed Solution**
We can build a reliable ETL (Extract, Transform, Load) pipeline that acts as a **Scraper & Indexer**.
It will autonomously ingest raw content, filter out noise, and link it to the OpenCRE or "community/owasp info" graphs, making it queryable via the existing chat interface.

---

## 2. Architecture Overview

The system consists of 4 autonomous modules.

**Info for contributors: DO NOT write production code for a module until the "Pre-Code Experiment" is passed.**

### Module A: Information Harvesting

**Goal:** Fetch changes from important information sources nightly.

```ascii
[ GitHub Actions ] (Trigger: 02:00 UTC)
       |
       v
[ A.1 Config Reader ] (Reads repos.yaml list)
       |
       v
[ A.2 Diff Fetcher ] ----> [ git log --since="24h" ]
       |
       v
[ Raw Change Bucket ] (Temporary Storage)
```

* Metric	Rating
* Difficulty	⭐⭐ (Medium)
* Vibe Coding Potential	Low. This requires hands-on engineering. Handling rate limits, git diff parsing, and incremental crawling is "hard coding" territory.
* Tech Stack:	Python (requests, PyGithub), GitHub Actions (Cron)
* MVP Logic: A nightly cron job checks a static list of high-value repos (ASVS, WSTG). Simple text diffs.
* Pre-Code Experiment (Do This First)
    Shifting through "Junk" : Manually inspect the file structure of 10 random OWASP repositories.
        Task: Identify common junk files (e.g., package-lock.json, CNAME, _config.yml).
        Goal: Create a Prompt and a Regex Exclusion List that eliminates 90% of noise without downloading the files.
    "Diff" Simulation: Pick a large Markdown file (e.g., in wstg). Modify one paragraph.
        Task: Write a 10-line script to fetch only the modified paragraph using git diff.
        Success Criteria: The script must return clean text, not raw diff syntax like <<<< HEAD.

* Bonus / Pro-Mode: LLM Diff Judge:
  Instead of writing complex regex to parse code changes, pass the raw git diff to a lightweight LLM.
  Prompt you can modify: "Review this diff. Did the logic or meaning change? Ignore formatting/typos. Reply YES/NO."

### Module B: Noise/Relevance Filter

**Goal:** Filter out bureaucracy (formatting, linting) cheaply.

```ascii
[ Raw Change Bucket ]
       |
       v
[ B.1 Regex Filter ] (Reject *.css, lockfiles, tests/)
       |
       v
[ B.2 LLM API ] (Gemini Flash / GPT-4o-mini)
    Prompt: "Is this security knowledge? JSON Bool."
       |
       +---(No)---> [ Discard ]
       |
       +---(Yes)--> [ Knowledge Queue ]
```

* Metric	Rating
* Difficulty	⭐ (Low / Entry Level)
* Vibe Coding Potential	High. You can "vibe code" the prompts. Tweak the system prompt until it "feels right."
* Tech Stack	Python (langchain or raw API calls), Managed LLM APIs.
* MVP Logic: Regex list first (free), then Managed LLM API (cheap).
* Pre-Code Experiment (Do This First)
    Human Benchmark:
        Extract 100 real commit messages/diffs from owasp ai exchange and owasp/wstg.
        Manually tag them in a spreadsheet: Relevant (Security Info) vs Noise (Typos, Admin, Formatting).
        Run these 100 items through your proposed LLM Prompt.
        Success Criteria: The LLM must match your tags >97% of the time. If it flags "Updated Code of Conduct" as "Security Knowledge," your prompt failed.

### Module C: The Librarian (The "Smart" Part)

**Goal:** Accurately map text to CRE nodes (handling the "Negation Problem") and detect updates to existing content.

```ascii
[ Knowledge Queue ]
       |
       v
[ C.1 Initial Retrieval ] (Vector Search / Pgvector)
    -> "Get top 20 candidates"
       |
       v
[ C.2 The Cross-Encoder ] (Local Re-Ranking)
    -> Model: ms-marco-MiniLM-L-6-v2
    -> "Compare Input vs Candidate. Output Score."
       |
       v
[ C.3 Update Detection ] (New Logic)
    -> Check if content is an update to existing content.
    -> Implement security gates to detect adversarial updates or contradictions to previous content.
       |
       v
[ C.4 Threshold Check ]
    -> Score > 0.8? Link to CRE.
    -> Score < 0.8? Flag for Human Review.
```

* Difficulty	⭐⭐⭐ (Hard)
* Vibe Coding Potential	Medium. Prompts are vibe-based, but Vector Search requires strict math/logic.
* Tech Stack	sentence-transformers (HuggingFace), pgvector, Python.
* Prerequisites	Understanding of Embeddings, Bi-Encoders vs Cross-Encoders.
* MVP Logic: Retrieve top 20 with Cosine Similarity, Re-rank top 5 with Cross-Encoder, and implement update detection.
* Pre-Code Experiment (Do This First)
    ASVS Re-Classify Challenge:
        Select 50 random ASVS requirements (e.g., "Verify password complexity...").
        Strip their metadata so you only have text.
        Feed them into a basic Vector Search (Cosine Similarity).
        Check: Does it map to the correct CRE node?
        Compare: Now run them through a Cross-Encoder.
        Success Criteria: The Cross-Encoder must show a 20% accuracy improvement over basic Cosine Similarity, specifically for "Negative" requirements (e.g., "Do NOT use MD5").
        You can use the existing CRE database as ground truth. You can repeat this with WSTG and NIST items too.

* Bonus / Pro-Mode: Hybrid Search
    Don't rely just on vectors. Use Hybrid Search (Vector + Keyword/BM25).
    Why: Vectors are bad at exact keyword matches (e.g., specific CVE IDs).

**Goal:** Accurately map text to CRE nodes (handling the "Negation Problem").

```ascii
[ Knowledge Queue ]
       |
       v
[ C.1 Initial Retrieval ] (Vector Search / Pgvector)
    -> "Get top 20 candidates"
       |
       v
[ C.2 The Cross-Encoder ] (Local Re-Ranking)
    -> Model: ms-marco-MiniLM-L-6-v2
    -> "Compare Input vs Candidate. Output Score."
       |
       v
[ C.3 Threshold Check ]
    -> Score > 0.8? Link to CRE.
    -> Score < 0.8? Flag for Human Review.
```

* Difficulty	⭐⭐⭐ (Hard)
* Vibe Coding Potential	Medium. Prompts are vibe-based, but Vector Search requires strict math/logic.
* Tech Stack	sentence-transformers (HuggingFace), pgvector, Python.
* Prerequisites	Understanding of Embeddings, Bi-Encoders vs Cross-Encoders.
* MVP Logic: Retrieve top 20 with Cosine Similarity, Re-rank top 5 with Cross-Encoder.
* Pre-Code Experiment (Do This First)
    ASVS Re-Classify Challenge:
        Select 50 random ASVS requirements (e.g., "Verify password complexity...").
        Strip their metadata so you only have text.
        Feed them into a basic Vector Search (Cosine Similarity).
        Check: Does it map to the correct CRE node?
        Compare: Now run them through a Cross-Encoder.
        Success Criteria: The Cross-Encoder must show a 20% accuracy improvement over basic Cosine Similarity, specifically for "Negative" requirements (e.g., "Do NOT use MD5").
        You can use the existing CRE database as ground truth. You can repeat this with WSTG and NIST items too.

* Bonus / Pro-Mode: Hybrid Search
    Don't rely just on vectors. Use Hybrid Search (Vector + Keyword/BM25).
    Why: Vectors are bad at exact keyword matches (e.g., specific CVE IDs).

### Module D: HITL & Logging

**Goal:** Simple human oversight without db bloat.

```ascii
[ Flagged for Review ] ---> [ D.1 Admin UI ] ---> [ Maintainer ]
                                   |
                                   v
                            [ S3 / Blob ]
                     (Appends to corrections.jsonl)
```

* Difficulty	⭐ (Low)
* Vibe Coding Potential	High. Standard CRUD web app. Ideal for junior devs or frontend contributors.
* Tech Stack	Flask/React, S3/MinIO.
* MVP Logic: Simple Admin UI. Logs corrections to a JSONL file.
* Pre-Code Experiment (Do This First)
    The "Click-Speed" Prototype:
        Draw a wireframe on paper or build a 10-line HTML prototype.
        Test: Can a user review, approve/reject, and save a correction in under 3 seconds per item?
        Goal: If the UI requires 5 clicks to approve one item, the volunteers will quit. Optimize for "Tinder-swipe" speed (Keybind 'y' for yes, 'n' for no).

* Bonus / Pro-Mode: Loss Warehousing
     Capture the "Loss Event" (Input + Wrong Prediction + Correct Label) in a structured format.
    Why: Allows future researchers to "Retrain on Loss."

## 3. Agent-Ready CI Pipeline (New way of code review)

Since we expect AI-generated PRs, we cannot rely solely on human code review. We will build the following:

* Strict Linting is enforced. No style arguments.
* Regression Eval: PRs come with tests. Test coverage under 70% is rejected.
  * We introduce dataset tests for Module B & C.
    We maintain a golden_dataset.json (100 samples of known-good inputs/outputs).
    Any PR touching Module B or C runs this dataset.
    Failure Condition: If accuracy drops by >2% compared to main, the PR is blocked automatically.
    Mandatory Tests: If code coverage drops, the PR is rejected.


## 4. Implementation Roadmap

Phase 1: Foundation (Week 1-2)

    [ ] Run Experiments

    [ ] Set up Ingest -> Process -> Store interfaces.

    [ ] Build The new CI Pipeline & Golden Dataset. Note: We build the test before the code.

Phase 2: Ingestion & Filtering (Week 3-4)

    [ ] Implement Module A (GitHub Action Cron).

    [ ] Implement Module B (LLM Client).

Phase 3: Intelligence (Week 5-6)

    [ ] Implement Module C (sentence-transformers integration).

    [ ] Tune the Cross-Encoder threshold against the Golden Dataset.

Phase 4: Dashboard (Week 7)

    [ ] Build simple Admin UI for Module D.

1. Call for Contributors

We are looking for distributed teams to own these modules.

    Backend Engineers: Owner for Module A. Needs Python & GitHub API experience.

    Prompt/AI Engineers: Owner for Module B. Needs experience with prompting.

    Data Scientists: Owner for Module C. Needs understanding of Bi-Encoders vs Cross-Encoders.

    Fullstack Devs: Owner for Module D. Simple Flask/React UI work.

To Contribute: Please reply to this RFC with the Module you wish to claim and provide a link to your working experiments.
If you are using AI tools (Cursor/Windsurf), please confirm you have read Section 3.
