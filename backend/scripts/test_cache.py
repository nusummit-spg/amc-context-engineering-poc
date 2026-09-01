# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

ENV_PATH = Path(r"C:\Users\AmiyaRanjanSarangi\Downloads\AMC_Context_Engineering_Graph\amc_code\amc-context-engineering-poc\streamlit_app\.env")
load_dotenv(dotenv_path=ENV_PATH)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.faiss_store import BrochureFAISSStore
from app.engine.retrieval import hybrid_graphrag

def test_cache():
    store = BrochureFAISSStore("amc_showcase")
    query = "What are SEBI guidelines for algos?"
    
    print("\n--- FIRST QUERY (Should MISS cache) ---")
    res1 = hybrid_graphrag(query, store)
    print(f"Latency: {res1['telemetry_breakdown']['latency_total_pipeline_ms']} ms")
    print(f"Mode: {res1['telemetry_breakdown']['pipeline_mode']}")
    
    # Send a semantically identical query
    query2 = "What are the SEBI rules and guidelines for algorithmic trading?"
    print(f"\n--- SECOND QUERY (Should HIT cache) ---")
    print(f"Query: {query2}")
    res2 = hybrid_graphrag(query2, store)
    print(f"Latency: {res2['telemetry_breakdown']['latency_total_pipeline_ms']} ms")
    print(f"Mode: {res2['telemetry_breakdown']['pipeline_mode']}")

if __name__ == "__main__":
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    test_cache()
