import sys
import time
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import ner_pipeline

TEST_QUERIES = [
    "What is the TER of Axis Bluechip Fund?",
    "How is HDFC Balanced Advantage Fund performing compared to its benchmark?",
    "What are SEBI regulations for debt mutual funds?",
    "Show me ESG scores for Adani Enterprises and Adani Ports",
]

def benchmark_ner(num_runs=5):
    # Warmup
    print("Warming up NER pipeline...")
    ner_pipeline.warmup()
    ner_pipeline.clear_ner_cache()

    results = []
    for query in TEST_QUERIES:
        times = []
        entities = []
        for _ in range(num_runs):
            ner_pipeline.clear_ner_cache()
            start = time.perf_counter()
            entities = ner_pipeline.run_layers_ab(query)
            elapsed = time.perf_counter() - start
            times.append(elapsed * 1000)  # ms

        avg_time = sum(times) / len(times)
        min_time = min(times)
        results.append({
            "query": query[:50] + "..." if len(query) > 50 else query,
            "avg_ms": avg_time,
            "min_ms": min_time,
            "entities_found": len(entities),
            "sample_entities": [e.get("text") for e in entities[:3]]
        })

    return results

if __name__ == "__main__":
    print("=" * 80)
    print("Benchmarking NER Pipeline (GLiNER)")
    print("=" * 80)

    results = benchmark_ner()

    for r in results:
        print(f"\nQuery: {r['query']}")
        print(f"  Avg Time: {r['avg_ms']:.1f}ms (Best: {r['min_ms']:.1f}ms)")
        print(f"  Entities: {r['entities_found']} -> {r['sample_entities']}")

    overall_avg = sum(r['avg_ms'] for r in results) / len(results)
    print(f"\n{'=' * 80}")
    print(f"Overall Average: {overall_avg:.1f}ms per query")

    if overall_avg < 150:
        print("[SUCCESS] EXCELLENT - Sub-150ms performance achieved!")
    elif overall_avg < 500:
        print("[SUCCESS] GOOD - Sub-500ms performance achieved!")
    else:
        print("[INFO] Performance benchmark completed.")
