# Neo4j Indexing Strategies for OpenCRE

To ensure high performance of graph queries, especially when dealing with large datasets (e.g., gap analysis or AI mapping), specific Neo4j properties must be indexed.

## Recommended Primary Indexes

The following properties are frequently used in `MATCH` and `WHERE` clauses and should always be indexed:

| Node Label | Property | Reason |
|------------|----------|--------|
| `NeoDocument` | `name` | Used extensively in Gap Analysis to locate start/end nodes. |
| `NeoCRE` | `external_id` | Used for mapping standards to CREs and AI pipeline lookups. |
| `NeoStandard` | `section` | Used for filtering standards by section. |
| `NeoStandard` | `section_id` | Used for precise standard section lookups. |
| `NeoStandard` | `subsection` | Used for granular standard filtering. |

> [!NOTE]
> `document_id` is automatically indexed by `neomodel` via `UniqueIdProperty`.

## Suggested Composite Indexes

For patterns that frequently filter by multiple properties simultaneously, consider creating composite indexes:

```cypher
CREATE INDEX standard_lookup_idx IF NOT EXISTS
FOR (n:NeoStandard)
ON (n.name, n.section, n.section_id);
```

## Performance Tips & Best Practices

### 1. Avoid Deep Unbounded Traversal
Query patterns like `[:REL*..20]` can be extremely expensive on dense graphs.
- **Tip**: Limit the max depth as much as possible.
- **Tip**: Use "Tiered Pruning" (as seen in `db.py`) to search for strong links first before falling back to complex traversals.

### 2. Use `PROFILE` for Query Analysis
When a query is slow, prefix it with `PROFILE` in the Neo4j Browser to see the execution plan.
- Look for **"NodeByLabelScan"** (indicates lack of index).
- Aim for **"NodeIndexSeek"** or **"NodeIndexLookup"**.

### 3. AI Mapping Performance
The AI embedding pipeline performs frequent `document_id` lookups. Ensure the database matches are using indexed fields to avoid full-label scans during high-concurrency embedding generation.

## How to Apply Indexes
Indexes are defined in `application/database/db.py` using `neomodel`'s `index=True` property. If you add new models or properties that are used for filtering, ensure they are marked as indexed.
