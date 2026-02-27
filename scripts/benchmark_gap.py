"""
Benchmark script for Gap Analysis performance (Issue #587)
===========================================================

Measures wall-clock time and peak memory for:
  - MODE A: Original exhaustive traversal (always runs wildcard [*..20] twice)
  - MODE B: Optimized tiered pruning     (early exit on strong/medium links)

Usage:
    # List available standards in Neo4j:
    python scripts/benchmark_gap.py --list-standards

    # Run benchmark on two standards:
    python scripts/benchmark_gap.py --standard1 "OWASP Top 10 2021" --standard2 "NIST 800-53"

Requirements:
    Neo4j must be running (use: make docker-neo4j)
    NEO4J_URL env var or default: neo4j://neo4j:password@localhost:7687
"""

import argparse
import os
import sys
import time
import tracemalloc

# Bootstrap project root onto sys.path
_project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_project_root))

try:
    from neomodel import config as neo_config, db as neomodel_db

    # Must import the project's DB models so neomodel registers NeoStandard,
    # NeoCRE etc. — otherwise resolve_objects=True raises NodeClassNotDefined.
    import application.database.db  # noqa: F401
except ImportError as exc:
    print(f"[ERROR] Could not import project modules: {exc}")
    print("  Make sure you run from the project root with venv activated.")
    sys.exit(1)


def connect_neo4j():
    url = os.environ.get("NEO4J_URL", "neo4j://neo4j:password@localhost:7687")
    neo_config.DATABASE_URL = url
    print(f"  → Connected to Neo4j at: {url}\n")


def list_available_standards():
    connect_neo4j()
    results, _ = neomodel_db.cypher_query(
        "MATCH (n:NeoStandard) RETURN DISTINCT n.name ORDER BY n.name"
    )
    if not results:
        print("  [!] No NeoStandard nodes found. Import data first:")
        print("      make import-neo4j")
        return
    print(f"Found {len(results)} standards:")
    for row in results:
        print(f"  • {row[0]}")


def run_original(name_1, name_2):
    """Original pre-PR#716 approach: always runs BOTH queries unconditionally."""
    denylist = ["Cross-cutting concerns"]

    # Query 1 — wildcard (the expensive one)
    r1, _ = neomodel_db.cypher_query(
        """
        MATCH (BaseStandard:NeoStandard {name: $name1})
        MATCH (CompareStandard:NeoStandard {name: $name2})
        MATCH p = allShortestPaths((BaseStandard)-[*..20]-(CompareStandard))
        WITH p
        WHERE length(p) > 1 AND ALL(n in NODES(p) WHERE
            (n:NeoCRE OR n = BaseStandard OR n = CompareStandard)
            AND NOT n.name IN $denylist)
        RETURN p
        """,
        {"name1": name_1, "name2": name_2, "denylist": denylist},
        resolve_objects=True,
    )

    # Query 2 — filtered (also always ran)
    r2, _ = neomodel_db.cypher_query(
        """
        MATCH (BaseStandard:NeoStandard {name: $name1})
        MATCH (CompareStandard:NeoStandard {name: $name2})
        MATCH p = allShortestPaths((BaseStandard)-[:(LINKED_TO|AUTOMATICALLY_LINKED_TO|CONTAINS)*..20]-(CompareStandard))
        WITH p
        WHERE length(p) > 1 AND ALL(n in NODES(p) WHERE
            (n:NeoCRE OR n = BaseStandard OR n = CompareStandard)
            AND NOT n.name IN $denylist)
        RETURN p
        """,
        {"name1": name_1, "name2": name_2, "denylist": denylist},
        resolve_objects=True,
    )

    return len(r1) + len(r2), 2  # paths, num_queries_run


def run_optimized(name_1, name_2):
    """Tiered pruning from PR #716/#717: exits early when strong/medium links found."""
    denylist = ["Cross-cutting concerns"]

    # Tier 1 — strong links only
    r, _ = neomodel_db.cypher_query(
        """
        MATCH (BaseStandard:NeoStandard {name: $name1})
        MATCH (CompareStandard:NeoStandard {name: $name2})
        MATCH p = allShortestPaths((BaseStandard)-[:(LINKED_TO|AUTOMATICALLY_LINKED_TO|SAME)*..20]-(CompareStandard))
        WITH p
        WHERE length(p) > 1 AND ALL(n in NODES(p) WHERE
            (n:NeoCRE OR n = BaseStandard OR n = CompareStandard)
            AND NOT n.name IN $denylist)
        RETURN p
        """,
        {"name1": name_1, "name2": name_2, "denylist": denylist},
        resolve_objects=True,
    )
    if r:
        return len(r), 1, "Tier 1 — strong links (LINKED_TO/SAME/AUTO)"

    # Tier 2 — adds CONTAINS
    r, _ = neomodel_db.cypher_query(
        """
        MATCH (BaseStandard:NeoStandard {name: $name1})
        MATCH (CompareStandard:NeoStandard {name: $name2})
        MATCH p = allShortestPaths((BaseStandard)-[:(LINKED_TO|AUTOMATICALLY_LINKED_TO|SAME|CONTAINS)*..20]-(CompareStandard))
        WITH p
        WHERE length(p) > 1 AND ALL(n in NODES(p) WHERE
            (n:NeoCRE OR n = BaseStandard OR n = CompareStandard)
            AND NOT n.name IN $denylist)
        RETURN p
        """,
        {"name1": name_1, "name2": name_2, "denylist": denylist},
        resolve_objects=True,
    )
    if r:
        return len(r), 2, "Tier 2 — medium links (adds CONTAINS)"

    # Tier 3 — wildcard fallback
    r, _ = neomodel_db.cypher_query(
        """
        MATCH (BaseStandard:NeoStandard {name: $name1})
        MATCH (CompareStandard:NeoStandard {name: $name2})
        MATCH p = allShortestPaths((BaseStandard)-[*..20]-(CompareStandard))
        WITH p
        WHERE length(p) > 1 AND ALL(n in NODES(p) WHERE
            (n:NeoCRE OR n = BaseStandard OR n = CompareStandard)
            AND NOT n.name IN $denylist)
        RETURN p
        """,
        {"name1": name_1, "name2": name_2, "denylist": denylist},
        resolve_objects=True,
    )
    return len(r), 3, "Tier 3 — wildcard fallback (no strong/medium paths found)"


def benchmark(name_1, name_2, runs=3):
    connect_neo4j()
    print(f"Benchmarking gap analysis: '{name_1}'  ↔  '{name_2}'")
    print(f"Averaging over {runs} run(s) per mode\n")
    print("=" * 68)

    # MODE A — Original
    a_times, a_mems, a_paths, a_queries = [], [], 0, 0
    print("▶  MODE A — Original exhaustive (pre-PR #716 behaviour)...")
    for i in range(runs):
        tracemalloc.start()
        t0 = time.perf_counter()
        a_paths, a_queries = run_original(name_1, name_2)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        a_times.append(elapsed)
        a_mems.append(peak / 1024 / 1024)
        print(f"   Run {i+1}: {elapsed:.3f}s  |  peak mem {a_mems[-1]:.2f} MB")

    avg_a_t = sum(a_times) / runs
    avg_a_m = sum(a_mems) / runs
    print()

    # MODE B — Optimized
    b_times, b_mems, b_paths, b_queries, b_tier = [], [], 0, 0, ""
    print("▶  MODE B — Optimized tiered pruning (GAP_ANALYSIS_OPTIMIZED=true)...")
    for i in range(runs):
        tracemalloc.start()
        t0 = time.perf_counter()
        b_paths, b_queries, b_tier = run_optimized(name_1, name_2)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        b_times.append(elapsed)
        b_mems.append(peak / 1024 / 1024)
        print(
            f"   Run {i+1}: {elapsed:.3f}s  |  peak mem {b_mems[-1]:.2f} MB  |  queries run: {b_queries}"
        )

    avg_b_t = sum(b_times) / runs
    avg_b_m = sum(b_mems) / runs

    t_pct = ((avg_a_t - avg_b_t) / avg_a_t * 100) if avg_a_t > 0 else 0
    m_pct = ((avg_a_m - avg_b_m) / avg_a_m * 100) if avg_a_m > 0 else 0

    direction = "faster" if t_pct >= 0 else "slower"
    print()
    print("=" * 68)
    print("RESULTS")
    print("=" * 68)
    print(f"  Pair: '{name_1}' ↔ '{name_2}'  |  {runs} run(s)\n")
    print(f"  {'Metric':<26} {'MODE A (original)':>18} {'MODE B (optimized)':>18}")
    print(f"  {'-'*26} {'-'*18} {'-'*18}")
    print(f"  {'Avg time (s)':<26} {avg_a_t:>18.3f} {avg_b_t:>18.3f}")
    print(f"  {'Avg peak memory (MB)':<26} {avg_a_m:>18.2f} {avg_b_m:>18.2f}")
    print(f"  {'Total paths returned':<26} {a_paths:>18} {b_paths:>18}")
    print(f"  {'DB queries executed':<26} {a_queries:>18} {b_queries:>18}")
    print()
    print(f"  ⚡ Mode B is {abs(t_pct):.1f}% {direction} than Mode A")
    print(
        f"  🧠 Mode B used {abs(m_pct):.1f}% {'less' if m_pct >= 0 else 'more'} peak memory"
    )
    print(f"  🔍 Mode B exited at: {b_tier}")
    print("=" * 68)

    # GitHub-ready table
    print()
    print("### GitHub-ready Benchmark Table\n")
    print(
        "| Metric | Original (`GAP_ANALYSIS_OPTIMIZED=false`) | Optimized (`GAP_ANALYSIS_OPTIMIZED=true`) | Δ |"
    )
    print(
        "|--------|------------------------------------------|------------------------------------------|---|"
    )
    print(
        f"| Avg query time | `{avg_a_t:.3f}s` | `{avg_b_t:.3f}s` | **{abs(t_pct):.1f}% {direction}** |"
    )
    print(
        f"| Peak memory | `{avg_a_m:.2f} MB` | `{avg_b_m:.2f} MB` | **{abs(m_pct):.1f}% {'less' if m_pct >= 0 else 'more'}** |"
    )
    print(f"| Paths returned | `{a_paths}` | `{b_paths}` | — |")
    print(
        f"| DB queries run | `{a_queries}` (always both) | `{b_queries}` (early exit at {b_tier.split('—')[0].strip()}) | — |"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Gap analysis benchmark — Issue #587")
    p.add_argument("--standard1", default="OWASP Top 10 2021")
    p.add_argument("--standard2", default="NIST 800-53")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--list-standards", action="store_true")
    args = p.parse_args()

    if args.list_standards:
        list_available_standards()
    else:
        benchmark(args.standard1, args.standard2, args.runs)
