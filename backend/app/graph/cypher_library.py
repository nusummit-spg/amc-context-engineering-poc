# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS5e — Cypher query library: parameterized traversal templates.

Each template maps to a query type / retrieval need. The orchestrator selects
templates via the traversal strategy mapper (WS5d) and records which were run
so the UI can display traversal paths.
"""

# 1. Aggregate group-level exposure across all schemes.
#    Scheme -HOLDS-> Issuer -ISSUED_BY-> IssuerGroup
GROUP_EXPOSURE = """
MATCH (s:Scheme)-[h:HOLDS]->(i:Issuer)-[:ISSUED_BY]->(g:IssuerGroup {name: $group_name})
RETURN s.name AS scheme, i.name AS issuer, h.pct_nav AS pct_nav,
       h.source_document_id AS source_document_id
ORDER BY s.name
"""

# 2. Risk themes monitored for an issuer group (links exposure to compliance concepts).
GROUP_RISK_THEMES = """
MATCH (g:IssuerGroup {name: $group_name})-[:MONITORED_FOR]->(t:RiskTheme)
RETURN g.name AS group_name, t.name AS risk_theme
"""

# 3. Schemes affected by a regulatory circular, with compliance status.
#    Circular -APPLIES_TO-> ClauseType -AFFECTS-> Scheme
CIRCULAR_AFFECTED_SCHEMES = """
MATCH (c:RegulatoryCircular)-[:APPLIES_TO]->(cl:ClauseType)-[a:AFFECTS]->(s:Scheme)
WHERE c.name = $circular_name
   OR $circular_name IN coalesce(c.aliases, [])
   OR toLower(c.name) CONTAINS toLower($circular_name)
RETURN c.name AS circular, cl.name AS clause_type, s.name AS scheme,
       a.status AS status, a.action_needed AS action_needed,
       a.source_document_id AS source_document_id
ORDER BY s.name
"""

# 4. Latest circular applying to a clause type (when the user names the clause, not the circular).
CLAUSE_AFFECTED_SCHEMES = """
MATCH (c:RegulatoryCircular)-[:APPLIES_TO]->(cl:ClauseType {name: $clause_name})-[a:AFFECTS]->(s:Scheme)
RETURN c.name AS circular, cl.name AS clause_type, s.name AS scheme,
       a.status AS status, a.action_needed AS action_needed
ORDER BY s.name
"""

# 5. Sector coverage map: analysts, covered issuers, flagged risk themes.
#    Analyst -COVERS-> Issuer -FLAGGED_IN-> RiskTheme
SECTOR_COVERAGE = """
MATCH (a:Analyst)-[:COVERS]->(i:Issuer)-[:IN_SECTOR]->(sec:Sector {name: $sector_name})
OPTIONAL MATCH (i)-[:FLAGGED_IN]->(t:RiskTheme)
RETURN a.name AS analyst, i.name AS issuer,
       collect(DISTINCT t.name) AS risk_themes
ORDER BY i.name
"""

# 6. Shared risk themes across a sector (which names flag the same theme).
SECTOR_RISK_THEMES = """
MATCH (i:Issuer)-[:IN_SECTOR]->(sec:Sector {name: $sector_name})
MATCH (i)-[f:FLAGGED_IN]->(t:RiskTheme)
RETURN t.name AS risk_theme, collect(DISTINCT i.name) AS issuers,
       count(DISTINCT i) AS issuer_count
ORDER BY issuer_count DESC
"""

# 7. Documents mentioning an entity (entity -> provenance).
ENTITY_DOCUMENTS = """
MATCH (d:Document)-[:MENTIONS]->(e {name: $entity_name})
RETURN d.document_id AS document_id, d.name AS title, d.category AS category
"""

# 8. Single-entity neighborhood facts (fallback for entity_lookup queries).
ENTITY_FACTS = """
MATCH (e {name: $entity_name})-[r]-(other)
WHERE other.name IS NOT NULL
RETURN e.name AS entity, type(r) AS rel_type,
       CASE WHEN startNode(r) = e THEN 'out' ELSE 'in' END AS direction,
       other.name AS other, labels(other)[0] AS other_type,
       properties(r) AS props
LIMIT 50
"""

# 9. Documents tagged under a taxonomy path (for /taxonomy node docs).
TAXONOMY_DOCUMENTS = """
MATCH (d:Document)-[:TAGGED_AS]->(t:TaxonomyNode)
WHERE t.path STARTS WITH $path
RETURN DISTINCT d.document_id AS document_id, d.name AS title, d.category AS category
"""

# 10. Latest circular for a clause type — used when the user says "SEBI's latest circular"
#     without naming the circular explicitly. Returns results ordered most-recent first.
LATEST_CIRCULAR_AFFECTED_SCHEMES = """
MATCH (c:RegulatoryCircular)-[:APPLIES_TO]->(cl:ClauseType)-[a:AFFECTS]->(s:Scheme)
WHERE cl.name = $clause_name OR $clause_name IN coalesce(cl.aliases, [])
WITH c, cl, a, s ORDER BY coalesce(c.issued_date, '') DESC
RETURN c.name AS circular, cl.name AS clause_type, s.name AS scheme,
       a.status AS status, a.action_needed AS action_needed,
       a.source_document_id AS source_document_id
"""

# 11. All issuers belonging to a sector — house_view fallback when no Analyst→COVERS
#     edges exist yet (e.g. early in ingestion). Case-insensitive sector name match.
SECTOR_ISSUER_LIST = """
MATCH (i:Issuer)-[:IN_SECTOR]->(sec:Sector)
WHERE toLower(sec.name) = toLower($sector_name)
   OR toLower(sec.name) CONTAINS toLower($sector_name)
RETURN i.name AS issuer, sec.name AS sector
ORDER BY i.name
"""

# 12. Phase 3: Temporal regulatory chain — find active circulars as of a specific date
TEMPORAL_CIRCULAR_STATE = """
MATCH (c:RegulatoryCircular)-[:APPLIES_TO]->(cl:ClauseType)-[a:AFFECTS]->(s:Scheme)
WHERE (c.effective_date IS NULL OR c.effective_date <= $as_of_date)
  AND (c.valid_to IS NULL OR c.valid_to >= $as_of_date)
RETURN c.name AS circular, c.effective_date AS effective_date,
       cl.name AS clause_type, s.name AS scheme, a.status AS status
ORDER BY c.effective_date DESC
"""

# 13. Phase 3: Financial & Table Facts for an entity (from Table-to-FinancialFact extractor)
FINANCIAL_FACTS_BY_ENTITY = """
MATCH (fm:FinancialMetric {metric_name: $metric_name})
WHERE toLower(fm.document_id) CONTAINS toLower($entity_name)
   OR $entity_name = 'all'
RETURN fm.metric_name AS metric, fm.value AS value, fm.unit AS unit,
       fm.period AS period, fm.document_id AS doc_id, fm.page_num AS page_num
ORDER BY fm.period DESC
"""

# 14. Phase 3: ESG Metrics for corporate entities
ESG_FACTS_BY_ENTITY = """
MATCH (em:ESGMetric)
WHERE toLower(em.metric_name) CONTAINS toLower($query_term)
   OR toLower(em.document_id) CONTAINS toLower($query_term)
RETURN em.metric_name AS metric, em.value AS value, em.unit AS unit,
       em.period AS period, em.document_id AS doc_id
LIMIT 25
"""

# 15. Phase 3: Cross-document entity resolution aliases
SAME_AS_CANONICAL_ENTITIES = """
MATCH (e {name: $entity_name})-[r:SAME_AS]-(other)
RETURN e.name AS entity, r.confidence AS score, r.resolved_type AS rel_type,
       other.name AS canonical_alias, labels(other)[0] AS label
"""

# 16. Phase 3: Federation — all context variances requiring resolution
CONTEXT_VARIANCES_PENDING = """
MATCH (cv:ContextVariance {requires_resolution: true})
OPTIONAL MATCH (cv)-[:CONFLICTS_BETWEEN]->(d:Document)
RETURN cv.variance_id        AS variance_id,
       cv.canonical_name     AS canonical_name,
       cv.attribute          AS attribute,
       cv.classification     AS classification,
       cv.reason             AS reason,
       cv.document_count     AS document_count,
       collect(DISTINCT d.name) AS documents
ORDER BY cv.canonical_name
"""

# 17. Phase 3: Variances for a specific concept name
CONTEXT_VARIANCES_BY_CONCEPT = """
MATCH (cv:ContextVariance)
WHERE toLower(cv.canonical_name) = toLower($canonical_name)
   OR toLower(cv.attribute)       = toLower($canonical_name)
OPTIONAL MATCH (cv)-[:CONFLICTS_BETWEEN]->(d:Document)
RETURN cv.variance_id    AS variance_id,
       cv.canonical_name AS canonical_name,
       cv.attribute      AS attribute,
       cv.classification AS classification,
       cv.reason         AS reason,
       d.name            AS document,
       d.document_id     AS document_id
ORDER BY cv.classification DESC
"""

# 18. Phase 3: Financial facts filtered by temporal validity
FINANCIAL_FACTS_TEMPORAL = """
MATCH (fm:FinancialMetric)
WHERE ($entity_name = 'all' OR toLower(fm.document_id) CONTAINS toLower($entity_name))
  AND (fm.valid_from IS NULL OR fm.valid_from <= $as_of_date)
  AND (fm.valid_to   IS NULL OR fm.valid_to   >= $as_of_date)
RETURN fm.metric_name AS metric, fm.value AS value, fm.unit AS unit,
       fm.period AS period, fm.document_id AS doc_id,
       fm.valid_from AS valid_from, fm.valid_to AS valid_to
ORDER BY fm.period DESC
"""

# 19. Phase 3: Traceability — find all chains for a given finding_id
TRACEABILITY_BY_FINDING = """
MATCH (t:TraceabilityChain {finding_id: $finding_id})
OPTIONAL MATCH (t)-[:HAS_SOURCE]->(s:SourceLink)-[:FROM_DOCUMENT]->(d:Document)
RETURN t.chain_id      AS chain_id,
       t.finding_type  AS finding_type,
       s.artifact_type AS artifact_type,
       s.artifact_id   AS artifact_id,
       s.section_title AS section,
       s.page_num      AS page_num,
       d.name          AS document,
       s.evidence_text AS evidence
ORDER BY s.page_num
"""

# 20. Phase 3: Coverage gap — sections with no traceability source links
UNCOVERED_SECTIONS = """
MATCH (d:Document {document_id: $document_id})
MATCH (sec:Section {document_id: $document_id})
WHERE NOT EXISTS {
  MATCH (t:TraceabilityChain)-[:HAS_SOURCE]->(s:SourceLink)
  WHERE s.document_id = $document_id AND s.section_id = sec.section_id
}
RETURN sec.section_id AS section_id, sec.title AS title, sec.level AS level
ORDER BY sec.order
"""
