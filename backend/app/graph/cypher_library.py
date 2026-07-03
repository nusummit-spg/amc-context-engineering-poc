"""
Cypher library — every write pattern the graph layer uses, in one place so
schema changes only need updating here. Two families of writes:

1. write_entity / write_relationship — idempotent MERGE for NER-derived
   entities/triples (from extraction/entities.py + resolver.py + relationships.py).
2. write_nav_row / write_aum_row / write_structured_batch — direct ETL for
   rows coming straight from Excel/CSV via ingestion/parsers/excel.py,
   bypassing NER entirely (Fund Performance.xlsx, History NAV/, etc).
"""
from typing import List, Dict, Optional
from graph.client import run_write, run_write_batch

_TYPE_TO_LABEL = {
    "fund house": ("FundHouse", "amfi_code"),
    "mutual fund scheme": ("Scheme", "isin_growth"),
    "scheme": ("Scheme", "isin_growth"),
    "holding": ("Holding", "isin"),
    "issuer": ("Issuer", "isin"),
    "issuer group": ("IssuerGroup", "name"),
    "benchmark index": ("Benchmark", "name"),
    "regulatory circular": ("RegulatoryCircular", "circular_no"),
    "risk theme": ("RiskTheme", "name"),
    "analyst": ("Analyst", "name"),
    "fund manager": ("FundManager", "name"),
    "credit rating": ("CreditRating", "name"),
}

_PREDICATE_TO_REL = {
    "manages": "MANAGES", "benchmarks_against": "BENCHMARKS_AGAINST", "holds": "HOLDS",
    "rated_by": "RATED_BY", "classified_under": "CLASSIFIED_UNDER", "issued_by": "ISSUED_BY",
    "governed_by": "GOVERNED_BY", "managed_by": "MANAGED_BY", "tracks": "TRACKS",
    "amends": "AMENDS", "flagged_in": "FLAGGED_IN", "monitored_for": "MONITORED_FOR",
}


def _label_and_key(entity_type: str, canonical_key: Optional[str], canonical_name: str):
    label, key_prop = _TYPE_TO_LABEL.get(entity_type.lower().strip(), ("Entity", "name"))
    if key_prop != "name" and not canonical_key:
        key_prop, key_value = "name", canonical_name
    else:
        key_value = canonical_key if key_prop != "name" else canonical_name
    return label, key_prop, key_value


# ---------------------------------------------------------------------------
# 1. NER-derived entity/relationship writes
# ---------------------------------------------------------------------------

def write_entity(entity_type: str, canonical_key: Optional[str], canonical_name: str) -> None:
    label, key_prop, key_value = _label_and_key(entity_type, canonical_key, canonical_name)
    cypher = f"""
    MERGE (n:{label} {{{key_prop}: $key_value}})
    ON CREATE SET n.name = $canonical_name, n.created_from = 'ner_pipeline'
    ON MATCH SET n.name = coalesce(n.name, $canonical_name)
    """
    run_write(cypher, {"key_value": key_value, "canonical_name": canonical_name})


def write_relationship(
    subj_type: str, subj_key: Optional[str], subj_name: str,
    predicate: str, obj_type: str, obj_key: Optional[str], obj_name: str,
    properties: Dict = None, source_chunk_id: str = None, confidence: float = None,
) -> bool:
    rel_type = _PREDICATE_TO_REL.get(predicate)
    if rel_type is None:
        print(f"[cypher_library] skipping unknown predicate: {predicate}")
        return False

    subj_label, subj_key_prop, subj_key_value = _label_and_key(subj_type, subj_key, subj_name)
    obj_label, obj_key_prop, obj_key_value = _label_and_key(obj_type, obj_key, obj_name)

    props = dict(properties or {})
    if source_chunk_id:
        props["source_chunk_id"] = source_chunk_id
    if confidence is not None:
        props["confidence"] = confidence

    cypher = f"""
    MERGE (a:{subj_label} {{{subj_key_prop}: $subj_key}})
    ON CREATE SET a.name = $subj_name
    MERGE (b:{obj_label} {{{obj_key_prop}: $obj_key}})
    ON CREATE SET b.name = $obj_name
    MERGE (a)-[r:{rel_type}]->(b)
    SET r += $props
    """
    run_write(cypher, {
        "subj_key": subj_key_value, "subj_name": subj_name,
        "obj_key": obj_key_value, "obj_name": obj_name, "props": props,
    })
    return True


def write_triples(resolved_lookup: Dict[str, "ResolvedEntity"], triples: List["Triple"]) -> int:
    written = 0
    for t in triples:
        subj, obj = resolved_lookup.get(t.subject), resolved_lookup.get(t.object)
        if not subj or not obj:
            continue
        ok = write_relationship(
            subj_type=subj.entity_type, subj_key=subj.canonical_key, subj_name=subj.canonical_name,
            predicate=t.predicate,
            obj_type=obj.entity_type, obj_key=obj.canonical_key, obj_name=obj.canonical_name,
            properties=t.properties, source_chunk_id=t.source_chunk_id, confidence=t.confidence,
        )
        written += int(ok)
    return written


# ---------------------------------------------------------------------------
# 2. Direct ETL writes for structured Excel/CSV rows (no NER involved)
# ---------------------------------------------------------------------------

def write_nav_row(scheme_isin: str, scheme_name: str, date: str, nav_value: float, source_file: str) -> tuple:
    cypher = """
    MERGE (s:Scheme {isin_growth: $isin})
    ON CREATE SET s.name = $name
    MERGE (n:NAVRecord {isin: $isin, date: $date})
    SET n.nav_value = $nav_value, n.source_file = $source_file
    MERGE (s)-[:HAS_NAV]->(n)
    """
    return cypher, {"isin": scheme_isin, "name": scheme_name, "date": date,
                     "nav_value": nav_value, "source_file": source_file}


def write_aum_row(scheme_isin: str, scheme_name: str, date: str, aum_cr: float, fund_house: str, source_file: str) -> tuple:
    cypher = """
    MERGE (fh:FundHouse {name: $fund_house})
    MERGE (s:Scheme {isin_growth: $isin})
    ON CREATE SET s.name = $name
    MERGE (fh)-[:MANAGES]->(s)
    MERGE (a:AUMFigure {isin: $isin, date: $date})
    SET a.aum_cr = $aum_cr, a.source_file = $source_file
    MERGE (s)-[:HAS_AUM]->(a)
    """
    return cypher, {"isin": scheme_isin, "name": scheme_name, "date": date,
                     "aum_cr": aum_cr, "fund_house": fund_house, "source_file": source_file}


def write_structured_batch(rows: List[Dict], source_file: str) -> int:
    """
    rows: normalized dicts from ingestion/parsers/excel.py (column-aliased).
    Detects NAV vs AUM rows by which fields are present and batches the
    writes into one transaction via graph.client.run_write_batch.
    """
    statements = []
    for row in rows:
        isin = row.get("isin")
        name = row.get("scheme_name", "")
        date = str(row.get("nav_date", ""))
        if not isin or not date:
            continue

        if row.get("nav_value") is not None:
            statements.append(write_nav_row(isin, name, date, float(row["nav_value"]), source_file))
        if row.get("aum_cr") is not None:
            statements.append(
                write_aum_row(isin, name, date, float(row["aum_cr"]), row.get("fund_house", ""), source_file)
            )

    if statements:
        run_write_batch(statements)
    return len(statements)