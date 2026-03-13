import argparse
import os
import sys
import time
import tracemalloc

# Bootstrap project root onto sys.path
_project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(_project_root))

try:
    from application.database import db
    from application.config import Config
except ImportError as exc:
    print(f"[ERROR] Could not import project modules: {exc}")
    print("  Make sure you run from the project root with venv activated.")
    sys.exit(1)


def list_available_standards():
    collection = db.Node_collection()
    standards = collection.standards()
    if not standards:
        print("  [!] No standards found in database.")
        return
    print(f"Found {len(standards)} standards:")
    for s in standards:
        print(f"  • {s}")


def run_benchmark(name_1, name_2, db_type, runs=3):
    """Run benchmark for a specific database type."""
    os.environ["GRAPH_DB_TYPE"] = db_type
    # Force re-initialization of GraphDB if needed (Factory usually handles this)
    collection = db.Node_collection()
    graph_db = collection.graph_db
    
    print(f"▶  Benchmarking {db_type.upper()} gap analysis: '{name_1}' ↔ '{name_2}'")
    
    times, mems, paths = [], [], 0
    for i in range(runs):
        tracemalloc.start()
        t0 = time.perf_counter()
        # db.gap_analysis returns (node_names, grouped_paths, extra_paths_dict)
        _, res_paths, _ = db.gap_analysis(graph_db, [name_1, name_2])
        
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        times.append(elapsed)
        mems.append(peak / 1024 / 1024)
        # res_paths is a dict of paths, we count all paths in all groups
        total_p = sum(len(group["paths"]) + group["extra"] for group in res_paths.values())
        paths = total_p
        print(f"   Run {i+1}: {elapsed:.3f}s  |  peak mem {mems[-1]:.2f} MB")

    avg_t = sum(times) / runs
    avg_m = sum(mems) / runs
    return avg_t, avg_m, paths


def benchmark(name_1, name_2, runs=3):
    print(f"Comparative Benchmark: '{name_1}' ↔ '{name_2}'")
    print(f"Averaging over {runs} run(s) per backend\n")
    print("=" * 68)

    # Benchmark Neo4j
    neo_t, neo_m, neo_p = run_benchmark(name_1, name_2, "neo4j", runs)
    print()

    # Benchmark AGE
    age_t, age_m, age_p = run_benchmark(name_1, name_2, "age", runs)
    print()

    t_pct = ((neo_t - age_t) / neo_t * 100) if neo_t > 0 else 0
    direction = "faster" if t_pct >= 0 else "slower"

    print("=" * 68)
    print("RESULTS")
    print("=" * 68)
    print(f"  Metric                     Neo4j              Apache AGE")
    print(f"  {'-'*60}")
    print(f"  Avg time (s)            {neo_t:>10.3f}        {age_t:>10.3f}")
    print(f"  Avg peak memory (MB)    {neo_m:>10.2f}        {age_m:>10.2f}")
    print(f"  Total paths             {neo_p:>10}        {age_p:>10}")
    print()
    print(f"  ⚡ Apache AGE is {abs(t_pct):.1f}% {direction} than Neo4j")
    print("=" * 68)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Multi-backend Gap analysis benchmark")
    p.add_argument("--standard1", default="OWASP Top 10 2021")
    p.add_argument("--standard2", default="NIST 800-53")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--list-standards", action="store_true")
    p.add_argument("--db", choices=["neo4j", "age", "both"], default="both")
    args = p.parse_args()

    from application import create_app
    app = create_app(mode=os.getenv("FLASK_CONFIG", "development"))
    
    with app.app_context():
        if args.list_standards:
            list_available_standards()
        elif args.db == "both":
            benchmark(args.standard1, args.standard2, args.runs)
        else:
            run_benchmark(args.standard1, args.standard2, args.db, args.runs)
