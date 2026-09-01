# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

from neo4j import GraphDatabase
import json

uri = "bolt://localhost:7688"
user = "neo4j"
password = "contextgraph"

driver = GraphDatabase.driver(uri, auth=(user, password))

def dump_db():
    with driver.session() as s:
        # Dump nodes
        nodes_res = s.run("MATCH (n) RETURN labels(n) as labels, properties(n) as props")
        nodes = []
        for record in nodes_res:
            props = dict(record["props"])
            # Remove embedding vector to keep the JSON readable and small
            if "embedding" in props:
                del props["embedding"]
            nodes.append({"labels": record["labels"], "properties": props})
            
        # Dump relationships
        rels_res = s.run("MATCH (n)-[r]->(m) RETURN type(r) as type, properties(r) as props, labels(n) as source_labels, labels(m) as target_labels, properties(n) as source_props, properties(m) as target_props")
        edges = []
        for record in rels_res:
            source_props = dict(record["source_props"])
            target_props = dict(record["target_props"])
            
            # Use a friendly identifier
            source_id = source_props.get("canonical_label") or source_props.get("regime_id") or source_props.get("section_id") or source_props.get("change_id") or "Unknown"
            target_id = target_props.get("canonical_label") or target_props.get("regime_id") or target_props.get("section_id") or target_props.get("change_id") or "Unknown"
            
            edges.append({
                "source": {"labels": record["source_labels"], "id": source_id},
                "type": record["type"],
                "target": {"labels": record["target_labels"], "id": target_id},
                "properties": dict(record["props"])
            })
            
    with open("graph_dump.json", "w") as f:
        json.dump({"nodes": nodes, "edges": edges}, f, indent=2)
    print("Graph dumped successfully to graph_dump.json")

dump_db()
driver.close()
