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

