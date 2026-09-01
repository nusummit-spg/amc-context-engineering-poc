# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import sys, os, json
from pathlib import Path

STREAMLIT_APP = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\streamlit_app")
sys.path.insert(0, str(STREAMLIT_APP))
os.chdir(str(STREAMLIT_APP))

from dotenv import load_dotenv
load_dotenv()
import config, taxonomy_retrieval
from neo4j import GraphDatabase

try:
    # 1. Get Neo4j Nodes
    neo4j_entities = set()
    driver = GraphDatabase.driver(config.NEO4J_URI, auth=(config.NEO4J_USER, config.NEO4J_PASSWORD))
    with driver.session() as s:
        # Looking for Entity, Scheme, Asset, etc.
        r = s.run("MATCH (n) RETURN labels(n) as labels, n.name as name, n.label as label LIMIT 100")
        for rec in r:
            name = rec['name'] or rec['label']
            if name: neo4j_entities.add(name.lower())
    driver.close()
    
    # 2. Get FAISS text
    index, chunks = taxonomy_retrieval.get_taxonomy_index()
    faiss_text = " ".join([c['text'].lower() if isinstance(c, dict) else c.lower() for c in chunks])
    
    # 3. Find Overlap
    print("Overlapping Entities (in both Neo4j and FAISS):")
    overlap_count = 0
    for entity in neo4j_entities:
        if len(entity) > 4 and entity in faiss_text:
            print(f"  - {entity}")
            overlap_count += 1
            
    print(f"\nTotal Overlaps: {overlap_count}")
    
except Exception as e:
    print('Error:', e)
