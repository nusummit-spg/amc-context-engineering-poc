# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import sys, os, time, json
from pathlib import Path

STREAMLIT_APP = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\streamlit_app")
sys.path.insert(0, str(STREAMLIT_APP))
os.chdir(str(STREAMLIT_APP))

from dotenv import load_dotenv
load_dotenv()
import config, taxonomy_retrieval

queries = [
    "Who are the key executives or directors of Adani Enterprises?",
    "List the subsidiaries owned by Adani Enterprises such as Mundra Copper.",
    "What are the general guidelines for mutual fund categorization?",
    "What is the definition of a Debt Scheme?",
    "What are the regulations regarding ESG disclosures for mutual funds?",
    "What is the net worth requirement for SEBI registered Investment Advisers?",
    "How is the net asset value (NAV) calculated for mutual funds?",
    "What are the restrictions on mutual fund borrowing?",
    "What are the reporting requirements for AMC branches?",
    "What are the rules for investing in unlisted equities?",
    "Who signed the SEBI circular regarding mutual fund categorization?",
    "What is Bailadila Iron Ore Mining Private Limited and who owns it?"
]

valid_queries = []

print("Testing queries to find ones answered by BOTH pipelines...\n")

for q in queries:
    print(f"Testing: {q}")
    
    # Test Traditional
    trad = taxonomy_retrieval.traditional_rag_v2(q)
    trad_ans = trad.get('answer', '').lower()
    trad_failed = any(phrase in trad_ans for phrase in ["i don't have", "i do not have", "i cannot", "i am not able", "i'm not able", "does not contain", "unable to"])
    
    # Test Graph
    graph = taxonomy_retrieval.hybrid_graphrag_v2(q)
    gans = graph.get('answer', '')
    if isinstance(gans, dict): gans = gans.get('answer', '')
    graph_ans = gans.lower()
    graph_failed = any(phrase in graph_ans for phrase in ["i don't have", "i do not have", "i cannot", "i am not able", "i'm not able", "does not contain", "unable to", "nothing answers"])
    
    if not trad_failed and not graph_failed:
        print("  => SUCCESS in both!")
        valid_queries.append({
            "query": q,
            "trad_ans": trad.get('answer', ''),
            "graph_ans": gans
        })
    else:
        print(f"  => FAILED: Trad={'Fail' if trad_failed else 'Pass'}, Graph={'Fail' if graph_failed else 'Pass'}")

print(f"\nFound {len(valid_queries)} valid queries.")
out = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\evaluation\results\valid_queries.json")
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(valid_queries, indent=2, ensure_ascii=False), encoding='utf-8')
