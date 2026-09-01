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
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.faiss_store import BrochureFAISSStore
from app.engine.retrieval import traditional_rag, hybrid_graphrag
from app.engine.llm_text_client import call_llm_with_usage

def generate_next_query(turn_index, current_transcript, previous_answer):
    sys_prompt = """You are an Adversarial AMC Portfolio Manager. You are stress-testing an AI retrieval system.
You must ask a highly specific, logical follow-up question based on the system's previous answer.
Your goal is to push the system across documents (e.g., from SEBI regulations to Adani ESG to AMFI Gold ETF market data).
Output ONLY the text of your next query. No greetings, no formatting.
"""
    if turn_index == 1:
        return "What are the core algorithmic trading guidelines or restrictions for Investment Advisers according to SEBI?"
    
    context_str = json.dumps(current_transcript, indent=2)
    user_prompt = f"Here is the conversation so far:\n{context_str}\n\nBased on the system's last answer, what is your next adversarial follow-up query?"
    
    # We use a basic call to the model
    from app.engine import config
    answer, _ = call_llm_with_usage(sys_prompt + "\n\n" + user_prompt, model_id=config.GROQ_MODEL_LIGHT)
    return answer.strip()

def run_aare_loop():
    print("Initializing AARE Automated Loop...")
    store = BrochureFAISSStore("amc_showcase")
    
    transcript = []
    chat_history_trad = []
    chat_history_hyb = []
    
    previous_answer = ""
    
    for turn in range(1, 6):
        print(f"\n--- [TURN {turn}] ---")
        query = generate_next_query(turn, transcript, previous_answer)
        print(f"TESTER AGENT QUERY: {query}")
        
        # 1. Traditional RAG
        print("  Evaluating Traditional RAG...")
        try:
            trad_res = traditional_rag(query, store, chat_history_trad)
            chat_history_trad.append({"role": "user", "content": query})
            chat_history_trad.append({"role": "assistant", "content": trad_res.get("answer", "")})
        except Exception as e:
            trad_res = {"error": str(e)}

        # 2. Hybrid RAG
        print("  Evaluating Hybrid Graph RAG...")
        try:
            hyb_res = hybrid_graphrag(query, store, chat_history_hyb)
            chat_history_hyb.append({"role": "user", "content": query})
            chat_history_hyb.append({"role": "assistant", "content": hyb_res.get("answer", "")})
        except Exception as e:
            hyb_res = {"error": str(e)}
            
        previous_answer = hyb_res.get("answer", "")
            
        turn_data = {
            "turn": turn,
            "query": query,
            "traditional_answer": trad_res.get("answer"),
            "traditional_sources": [d.get("name") for d in trad_res.get("docs", [])] if "docs" in trad_res else [],
            "hybrid_answer": hyb_res.get("answer"),
            "hybrid_sources": [d.get("name") for d in hyb_res.get("docs", [])] if "docs" in hyb_res else [],
            "hybrid_graph_edges_used": len(hyb_res.get("edges", [])) if "edges" in hyb_res else 0
        }
        transcript.append(turn_data)
        
        # Sleep briefly to avoid rate limits
        time.sleep(2)

    out_file = Path("aare_transcript.json")
    with open(out_file, "w") as f:
        json.dump(transcript, f, indent=2)
    print(f"\nCompleted! Saved final transcript to {out_file.resolve()}")

if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    run_aare_loop()
