// ===========================================================================
// Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
// 
// Author: NuSummit Developers
//
// ===========================================================================

// Run every query against the Neo4j endpoint used by the API under test.
// All statements are read-only. Save the output adjacent to the API probe run.

// 1. Graph topology and schema census.
MATCH (n)
RETURN labels(n) AS labels, count(*) AS node_count
ORDER BY node_count DESC;

MATCH ()-[r]->()
RETURN type(r) AS relationship_type, count(*) AS relationship_count
ORDER BY relationship_count DESC;

// 2. Documents seen by the graph, with direct provenance/linkage coverage.
MATCH (d:Document)
OPTIONAL MATCH (d)-[:MENTIONS]->(e)
OPTIONAL MATCH (d)-[:TAGGED_AS]->(t:TaxonomyNode)
RETURN d.document_id AS document_id,
       d.name AS name,
       count(DISTINCT e) AS mentioned_entities,
       count(DISTINCT t) AS taxonomy_tags
ORDER BY document_id;

// 3. Documents that cannot be joined to taxonomy metadata.
MATCH (d:Document)
WHERE NOT (d)-[:TAGGED_AS]->(:TaxonomyNode)
RETURN d.document_id AS document_id, d.name AS name
ORDER BY document_id;

// 4. Relationships without provenance. Results should be reviewed by label;
// schema/taxonomy relationships may be intentional, extracted relationships are not.
MATCH ()-[r]->()
WHERE r.source_document_id IS NULL
RETURN type(r) AS relationship_type, count(*) AS missing_provenance_count
ORDER BY missing_provenance_count DESC;

// 5. Taxonomy content, regardless of whether it was loaded into this database.
MATCH (n)
WHERE n.source_db = 'taxonomy'
RETURN labels(n) AS labels, count(*) AS taxonomy_node_count
ORDER BY taxonomy_node_count DESC;

// 6. Candidate links between extracted entities and taxonomy classes.
MATCH (e)-[r]-(s:SchemeClass)
RETURN labels(e) AS entity_labels, type(r) AS relationship_type, count(*) AS link_count
ORDER BY link_count DESC;
