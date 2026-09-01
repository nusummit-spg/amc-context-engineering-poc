# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import os
import sys
import json
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Force load the correct .env before importing app modules
ENV_PATH = Path(r"C:\Users\AmiyaRanjanSarangi\Downloads\AMC_Context_Engineering_Graph\amc_code\amc-context-engineering-poc\streamlit_app\.env")
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    print(json.dumps({"error": f"Could not find .env at {ENV_PATH}"}))
    sys.exit(1)

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.faiss_store import BrochureFAISSStore
from app.engine.retrieval import traditional_rag, hybrid_graphrag

def main():
    parser = argparse.ArgumentParser(description="AARE Subagent Harness")
    parser.add_argument("query", type=str, help="The query from the AMC Tester Subagent")
    args = parser.parse_args()

    try:
        # We use the amc_showcase index which has 29,119 vectors!
        store = BrochureFAISSStore("amc_showcase")
    except Exception as e:
        print(json.dumps({"error": f"Failed to load FAISS store: {e}"}))
        sys.exit(1)

    query = args.query
    chat_history = [] # For this stateless harness turn, we rely on the Subagent to feed context via the query string if needed

    result_payload = {
        "query": query,
        "traditional_rag": {},
        "hybrid_rag": {}
    }

    # 1. Traditional RAG
    try:
        trad_res = traditional_rag(query, store, chat_history)
        # Strip long text for token efficiency in the JSON output, keep just the answer and metrics
        result_payload["traditional_rag"]["answer"] = trad_res.get("answer")
        result_payload["traditional_rag"]["telemetry"] = trad_res.get("telemetry_breakdown")
        result_payload["traditional_rag"]["context_sources"] = [d.get("name") for d in trad_res.get("docs", [])]
    except Exception as e:
        result_payload["traditional_rag"]["error"] = str(e)

    # 2. Hybrid Graph RAG
    try:
        hyb_res = hybrid_graphrag(query, store, chat_history)
        result_payload["hybrid_rag"]["answer"] = hyb_res.get("answer")
        result_payload["hybrid_rag"]["telemetry"] = hyb_res.get("telemetry_breakdown")
        result_payload["hybrid_rag"]["graph_edges_used"] = len(hyb_res.get("edges", []))
        result_payload["hybrid_rag"]["context_sources"] = [d.get("name") for d in hyb_res.get("docs", [])]
    except Exception as e:
        result_payload["hybrid_rag"]["error"] = str(e)

    # Print strictly as JSON so the Subagent can parse it easily
    print(json.dumps(result_payload, indent=2))

if __name__ == "__main__":
    # Suppress verbose logging from transformers/sentence-transformers
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    import warnings
    warnings.filterwarnings("ignore")
    main()
