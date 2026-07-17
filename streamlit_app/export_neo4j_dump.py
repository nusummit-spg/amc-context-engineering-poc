"""
export_neo4j_dump.py
====================
Connects to the active Neo4j database (`bolt://localhost:7687`) and exports
the entire graph (every node with all labels/properties and every relationship
with all properties) into:
1. `amc_master_full_dump.cypher` (Self-contained Cypher queries for Cypher-Shell / Neo4j Browser)
2. `amc_master_full_dump.json` (Structured JSON dump for high-speed batch importing)
"""
import json
import time
from pathlib import Path
from neo4j import GraphDatabase
import config

CYPHER_OUT_PATH = Path("amc_master_full_dump.cypher")
JSON_OUT_PATH = Path("amc_master_full_dump.json")

def format_value(v):
    if v is None:
        return "null"
    elif isinstance(v, bool):
        return "true" if v else "false"
    elif isinstance(v, (int, float)):
        return str(v)
    elif isinstance(v, list):
        return "[" + ", ".join(format_value(x) for x in v) + "]"
    elif isinstance(v, dict):
        return "{" + ", ".join(f"`{k}`: {format_value(val)}" for k, val in v.items()) + "}"
    else:
        # string escape
        escaped = str(v).replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'

def export_graph():
    print("================================================================================")
    print(f"  [NEO4J EXPORTER] EXPORTING FULL DATABASE FROM {config.NEO4J_URI}")
    print("================================================================================")
    
    driver = GraphDatabase.driver(
        config.NEO4J_URI,
        auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
    )
    
    nodes_data = []
    edges_data = []
    cypher_statements = [
        "// ============================================================================",
        "//  ContextGraph AMC Master Database Export (Self-Contained Cypher Dump)",
        "// ============================================================================",
        "//  To import via cypher-shell:",
        "//  cypher-shell -u neo4j -p contextgraph -f amc_master_full_dump.cypher",
        "// ============================================================================\n",
        "// 1. Constraints & Indexes",
        "CREATE CONSTRAINT entity_dedup_key IF NOT EXISTS FOR (e:Entity) REQUIRE e.dedup_key IS UNIQUE;",
        "CREATE INDEX entity_text IF NOT EXISTS FOR (e:Entity) ON (e.text);\n",
        "// 2. Nodes Export"
    ]
    
    with driver.session(database=config.NEO4J_DATABASE) as session:
        # 1. Fetch all nodes
        t0 = time.perf_counter()
        result_nodes = session.run("MATCH (n) RETURN elementId(n) AS eid, labels(n) AS labels, properties(n) AS props")
        for record in result_nodes:
            eid = record["eid"]
            labels = record["labels"] or ["Entity"]
            props = record["props"] or {}
            
            # Save for JSON dump
            nodes_data.append({"id": eid, "labels": labels, "properties": props})
            
            # Format Cypher MERGE / CREATE
            label_str = ":" + ":".join(f"`{l}`" for l in labels)
            if "dedup_key" in props:
                dedup_val = format_value(props["dedup_key"])
                other_props = {k: v for k, v in props.items() if k != "dedup_key"}
                set_clause = " ".join(f"SET n.{k} = {format_value(v)}" for k, v in other_props.items())
                if set_clause:
                    stmt = f"MERGE (n{label_str} {{dedup_key: {dedup_val}}}) {set_clause};"
                else:
                    stmt = f"MERGE (n{label_str} {{dedup_key: {dedup_val}}});"
            else:
                props_str = ", ".join(f"`{k}`: {format_value(v)}" for k, v in props.items())
                stmt = f"CREATE (n{label_str} {{{props_str}}});"
            cypher_statements.append(stmt)
            
        print(f"  [+] Exported {len(nodes_data)} total nodes in {(time.perf_counter()-t0)*1000:.1f} ms.")
        
        # 2. Fetch all relationships
        cypher_statements.append("\n// 3. Relationships Export")
        t1 = time.perf_counter()
        result_edges = session.run("""
            MATCH (s)-[r]->(o)
            RETURN properties(s).dedup_key AS s_key, labels(s) AS s_labels, properties(s).text AS s_text,
                   type(r) AS rel_type, properties(r) AS r_props,
                   properties(o).dedup_key AS o_key, labels(o) AS o_labels, properties(o).text AS o_text
        """)
        for record in result_edges:
            s_key = record["s_key"]
            o_key = record["o_key"]
            rel_type = record["rel_type"]
            r_props = record["r_props"] or {}
            
            edges_data.append({
                "source_dedup_key": s_key,
                "source_text": record["s_text"],
                "target_dedup_key": o_key,
                "target_text": record["o_text"],
                "relationship_type": rel_type,
                "properties": r_props
            })
            
            # If both have dedup_key, create reliable Cypher edge statement
            if s_key and o_key:
                props_str = ", ".join(f"`{k}`: {format_value(v)}" for k, v in r_props.items())
                rel_props = f" {{{props_str}}}" if props_str else ""
                stmt = (f"MATCH (s:Entity {{dedup_key: {format_value(s_key)}}}), "
                        f"(o:Entity {{dedup_key: {format_value(o_key)}}}) "
                        f"MERGE (s)-[:`{rel_type}`{rel_props}]->(o);")
                cypher_statements.append(stmt)
        print(f"  [+] Exported {len(edges_data)} total relationships in {(time.perf_counter()-t1)*1000:.1f} ms.")

    # Write out files
    cypher_content = "\n".join(cypher_statements) + "\n"
    CYPHER_OUT_PATH.write_text(cypher_content, encoding="utf-8")
    
    json_dump = {
        "metadata": {
            "database_uri": config.NEO4J_URI,
            "export_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "node_count": len(nodes_data),
            "edge_count": len(edges_data)
        },
        "nodes": nodes_data,
        "relationships": edges_data
    }
    JSON_OUT_PATH.write_text(json.dumps(json_dump, indent=2, ensure_ascii=False), encoding="utf-8")
    
    print(f"\n  [SUCCESS] Full graph dump saved to:")
    print(f"    --> {CYPHER_OUT_PATH.resolve()} ({CYPHER_OUT_PATH.stat().st_size / 1024:.1f} KB)")
    print(f"    --> {JSON_OUT_PATH.resolve()} ({JSON_OUT_PATH.stat().st_size / 1024:.1f} KB)")
    driver.close()

if __name__ == "__main__":
    export_graph()
