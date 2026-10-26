# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Retrieval steps 2-3 — WS5d query-type -> traversal-strategy mapper,
multi-hop depth controller, and WS5e graph traversal execution.

Changes vs. original:
  - Bug fix: BaseEntity was instantiated directly in _exposure() group-hop fallback;
    replaced with IssuerGroup() (concrete subclass required after WS5a schema change).
  - intent is now passed to every strategy method so fallbacks can inspect
    intent.taxonomy_paths when entity resolution returns nothing.
  - _compliance(): added last-resort fallback — if no circular/clause entity resolves,
    runs CLAUSE_AFFECTED_SCHEMES with the known default "Exit Load Clause".
  - _house_view(): added two-stage fallback — (1) try SECTOR_COVERAGE using the leaf
    node of each intent.taxonomy_path; (2) if still empty, run SECTOR_ISSUER_LIST to
    at least surface which issuers are in the sector for synthesis context.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import uuid4

from app.config import get_settings
from app.engine import config
from app.graph import cypher_library as cql
from app.graph.client import GraphClient
from app.models.entities import BaseEntity, EntityType, IssuerGroup
from app.models.query import GraphFact, QueryIntent, QueryType

logger = logging.getLogger("retrieval")


class GraphTraversal:
    """Selects and runs Cypher templates based on the classified query type."""

    def __init__(self, graph: GraphClient):
        """Initialize a new instance of GraphTraversal.

        Args:
            graph (GraphClient): Graph database client or graph representation.
        """
        self._graph = graph
        self._max_depth = get_settings().max_traversal_depth

    def _audit_traversal(
        self,
        user_id: Optional[str],
        tenant_id: Optional[str],
        start_entities: list[str],
        result_count: int,
    ) -> None:
        """Log graph access for security auditing.

        Args:
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            start_entities (list[str]): Collection or list of start entities.
            result_count (int): The result count.
        """
        logger.info(
            "Graph traversal: user=%s tenant=%s entities=%s results=%d",
            user_id, tenant_id, start_entities, result_count,
        )

    async def traverse(
        self,
        intent_or_entities: Any,
        entities_or_depth: Any = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        authorized_labels: Optional[list[str]] = None,
    ) -> Any:
        """Traverse graph with authorization constraints and auditing.

        Supports both:
        1. (intent: QueryIntent, entities: list[BaseEntity], user_id, tenant_id) -> (facts, paths, cyphers)
        2. (start_entities: list[str], max_depth: int, user_id, tenant_id, authorized_labels) -> dict

        Args:
            intent_or_entities (Any): Collection or list of intent or entities.
            entities_or_depth (Any): The entities or depth.
            user_id (Optional[str]): Unique identifier of the user.
            tenant_id (Optional[str]): Unique identifier of the tenant.
            authorized_labels (Optional[list[str]]): Collection or list of authorized labels.

        Returns:
            Any: Resulting Any instance.
        """
        if isinstance(intent_or_entities, list) and (entities_or_depth is None or isinstance(entities_or_depth, int)):
            start_entities = intent_or_entities
            max_depth = entities_or_depth if isinstance(entities_or_depth, int) else self._max_depth
            constraints = []
            if tenant_id:
                constraints.append(f"n.tenant_id = '{tenant_id}'")
            if authorized_labels:
                label_filter = " OR ".join(f"'{label}' IN labels(n)" for label in authorized_labels)
                constraints.append(f"({label_filter})")
            constraint_clause = " AND ".join(constraints) if constraints else "1=1"
            cypher = f"""
            MATCH path = (start)-[*1..{max_depth}]-(n)
            WHERE start.id IN $start_ids
            AND {constraint_clause}
            RETURN path
            LIMIT 1000
            """
            try:
                results = await self._graph.run(cypher, start_ids=start_entities)
            except Exception as exc:
                logger.warning("Graph query failed in parameterized traversal: %s", exc)
                results = []
            self._audit_traversal(user_id, tenant_id, start_entities, len(results))
            return {"results": results, "count": len(results)}

        intent: QueryIntent = intent_or_entities
        entities: list[BaseEntity] = entities_or_depth or []
        strategy = {
            QueryType.EXPOSURE_AGGREGATION: self._exposure,
            QueryType.COMPLIANCE_CHECK: self._compliance,
            QueryType.HOUSE_VIEW_SYNTHESIS: self._house_view,
            QueryType.ENTITY_LOOKUP: self._entity_lookup,
            QueryType.GENERAL: self._noop,
        }[intent.query_type]
        # Pass intent so strategies can use taxonomy_paths as fallback
        facts, paths, cyphers = await strategy(intent, entities)
        self._audit_traversal(user_id, tenant_id, [e.name for e in entities], len(facts))
        return facts, paths, cyphers

    async def _gather_rows(self, calls: list[tuple]) -> list[list[dict]]:
        """Runs independent graph queries concurrently when parallelization is on.

        Each call is (cypher, kwargs). Multi-entity queries previously issued one
        sequential Neo4j roundtrip per entity; the templates are independent, so
        the wall-clock cost collapses to that of the slowest one. Failures are
        isolated — a single bad template yields [] instead of aborting traversal.

        Args:
            calls (list[tuple]): Collection or list of calls.

        Returns:
            list[list[dict]]: List of resulting items or records.
        """
        if not calls:
            return []

        async def _run(cypher, kwargs):
            """Run operation.

            Args:
                cypher: The cypher.
                kwargs: Keyword arguments.

            Returns:
                Result of the operation.
            """
            try:
                return await self._graph.run(cypher, **kwargs)
            except Exception as exc:
                logger.warning("Graph query failed during parallel traversal: %s", exc)
                return []

        if not config.ENABLE_PARALLELIZATION or len(calls) == 1:
            return [await _run(cypher, kwargs) for cypher, kwargs in calls]

        return list(await asyncio.gather(*[_run(cypher, kwargs) for cypher, kwargs in calls]))

    # ---------- strategies ----------

    async def _exposure(self, intent: QueryIntent, entities: list[BaseEntity]):
        """Exposure.

        Args:
            intent (QueryIntent): Classified query intent.
            entities (list[BaseEntity]): List of entity identifiers or objects.

        Returns:
            Result of the operation.
        """
        facts, paths, cyphers = [], [], []
        groups = [e for e in entities if e.entity_type == EntityType.ISSUER_GROUP]
        # If only an Issuer was resolved, hop up to its group (depth controller: +1 hop).
        if not groups:
            issuers = [e for e in entities if e.entity_type == EntityType.ISSUER]
            group_hops = await self._gather_rows([
                ("MATCH (:Issuer {name: $name})-[:ISSUED_BY]->(g:IssuerGroup) RETURN g.name AS name",
                 {"name": issuer.name})
                for issuer in issuers
            ])
            for rows in group_hops:
                for row in rows:
                    # FIX: use concrete IssuerGroup subclass (BaseEntity is abstract
                    # after WS5a schema change and cannot be instantiated directly).
                    groups.append(IssuerGroup(name=row["name"]))

        # Exposure and risk-theme lookups are independent across every group —
        # issue them in one concurrent wave instead of 2xN sequential roundtrips.
        group_results = await self._gather_rows(
            [(cql.GROUP_EXPOSURE, {"group_name": g.name}) for g in groups]
            + [(cql.GROUP_RISK_THEMES, {"group_name": g.name}) for g in groups]
        )
        exposure_rows = group_results[:len(groups)]
        risk_theme_rows = group_results[len(groups):]

        for group, rows, risk_rows in zip(groups, exposure_rows, risk_theme_rows):
            cyphers.append("GROUP_EXPOSURE")
            for row in rows:
                pct = row.get("pct_nav")
                facts.append(GraphFact(
                    fact_id=str(uuid4()),
                    statement=f"{row['scheme']} holds {row['issuer']}"
                              + (f" at {pct}% of NAV" if pct is not None else ""),
                    subject=row["scheme"], predicate="HOLDS", object=row["issuer"],
                    properties={"pct_nav": pct, "issuer_group": group.name},
                    source_document_ids=[d for d in [row.get("source_document_id")] if d],
                    traversal_path="Scheme→HOLDS→Issuer→ISSUED_BY→IssuerGroup",
                ))
            if rows:
                paths.append(
                    f"Scheme → HOLDS → Issuer → ISSUED_BY → {group.name}: "
                    f"aggregated exposure across {len({r['scheme'] for r in rows})} scheme(s)"
                )

            cyphers.append("GROUP_RISK_THEMES")
            for row in risk_rows:
                facts.append(GraphFact(
                    fact_id=str(uuid4()),
                    statement=f"{row['group_name']} is monitored for {row['risk_theme']}",
                    subject=row["group_name"], predicate="MONITORED_FOR", object=row["risk_theme"],
                    traversal_path="IssuerGroup→MONITORED_FOR→RiskTheme",
                ))
            if risk_rows:
                paths.append(f"{group.name} → MONITORED_FOR → Risk Concept "
                             "(links exposure to the compliance taxonomy branch)")
        return facts, paths, cyphers

    async def _compliance(self, intent: QueryIntent, entities: list[BaseEntity]):
        """Compliance.

        Args:
            intent (QueryIntent): Classified query intent.
            entities (list[BaseEntity]): List of entity identifiers or objects.

        Returns:
            Result of the operation.
        """
        facts, paths, cyphers = [], [], []
        circulars = [e for e in entities if e.entity_type == EntityType.REGULATORY_CIRCULAR]
        clauses   = [e for e in entities if e.entity_type == EntityType.CLAUSE_TYPE]

        rows: list[dict] = []
        if circulars:
            for result in await self._gather_rows(
                [(cql.CIRCULAR_AFFECTED_SCHEMES, {"circular_name": c.name}) for c in circulars]
            ):
                rows += result
                cyphers.append("CIRCULAR_AFFECTED_SCHEMES")
        elif clauses:
            for result in await self._gather_rows(
                [(cql.CLAUSE_AFFECTED_SCHEMES, {"clause_name": c.name}) for c in clauses]
            ):
                rows += result
                cyphers.append("CLAUSE_AFFECTED_SCHEMES")

        # Last-resort fallback: if entity resolution failed entirely (no circular,
        # no clause), try the known default Exit Load Clause.  This covers the case
        # where the user says "SEBI's latest circular" but nothing resolves in the
        # alias index (e.g. "SEBI" alone is not yet an alias for any entity).
        if not rows:
            rows = await self._graph.run(
                cql.CLAUSE_AFFECTED_SCHEMES, clause_name="Exit Load Clause"
            )
            if rows:
                cyphers.append("CLAUSE_AFFECTED_SCHEMES(default-fallback)")
                logger.info(
                    "Compliance traversal: no entity resolved, fell back to 'Exit Load Clause'"
                )

        for row in rows:
            facts.append(GraphFact(
                fact_id=str(uuid4()),
                statement=f"{row['scheme']}: {row['clause_type']} status is "
                          f"{row.get('status', 'unknown')} under {row['circular']}"
                          + (f" — action: {row['action_needed']}" if row.get("action_needed") else ""),
                subject=row["circular"], predicate="AFFECTS", object=row["scheme"],
                properties={"status": row.get("status"), "clause_type": row["clause_type"]},
                source_document_ids=[d for d in [row.get("source_document_id")] if d],
                traversal_path="Circular→APPLIES_TO→ClauseType→AFFECTS→Scheme",
            ))
        if rows:
            paths.append(
                "Circular → APPLIES_TO → Clause Type → AFFECTS → Scheme: "
                f"automatic compliance flagging across {len({r['scheme'] for r in rows})} scheme(s)"
            )
        return facts, paths, cyphers

    async def _house_view(self, intent: QueryIntent, entities: list[BaseEntity]):
        """House view.

        Args:
            intent (QueryIntent): Classified query intent.
            entities (list[BaseEntity]): List of entity identifiers or objects.

        Returns:
            Result of the operation.
        """
        facts, paths, cyphers = [], [], []
        sectors = [e for e in entities if e.entity_type == EntityType.SECTOR]
        # Coverage and risk-theme lookups are independent per sector.
        sector_results = await self._gather_rows(
            [(cql.SECTOR_COVERAGE, {"sector_name": s.name}) for s in sectors]
            + [(cql.SECTOR_RISK_THEMES, {"sector_name": s.name}) for s in sectors]
        )
        coverage_rows = sector_results[:len(sectors)]
        theme_rows_all = sector_results[len(sectors):]

        for sector, coverage, theme_rows in zip(sectors, coverage_rows, theme_rows_all):
            cyphers.append("SECTOR_COVERAGE")
            for row in coverage:
                themes = ", ".join(t for t in row["risk_themes"] if t) or "none flagged"
                facts.append(GraphFact(
                    fact_id=str(uuid4()),
                    statement=f"{row['analyst']} covers {row['issuer']} (risk themes: {themes})",
                    subject=row["analyst"], predicate="COVERS", object=row["issuer"],
                    properties={"risk_themes": row["risk_themes"]},
                    traversal_path="Analyst→COVERS→Issuer→FLAGGED_IN→RiskTheme",
                ))
            cyphers.append("SECTOR_RISK_THEMES")
            for row in theme_rows:
                facts.append(GraphFact(
                    fact_id=str(uuid4()),
                    statement=f"Risk theme '{row['risk_theme']}' is flagged for "
                              f"{row['issuer_count']} {sector.name} name(s): "
                              f"{', '.join(row['issuers'])}",
                    subject=row["risk_theme"], predicate="FLAGGED_IN_BY", object=sector.name,
                    properties={"issuers": row["issuers"], "count": row["issuer_count"]},
                    traversal_path="Issuer→FLAGGED_IN→RiskTheme (grouped by shared concept)",
                ))
            if coverage or theme_rows:
                paths.append(
                    f"Analyst → COVERS → Entity → FLAGGED_IN → Risk Theme: entity resolution "
                    f"groups {sector.name} names by shared risk concepts before synthesis"
                )

        # Fallback stage 1: entity resolution produced nothing → infer sector name
        # from the tail of each intent taxonomy path and retry SECTOR_COVERAGE.
        if not facts:
            resolved_sector_names = {s.name.lower() for s in sectors}
            for path in (intent.taxonomy_paths or []):
                leaf = path.split("/")[-1].strip()
                if not leaf or leaf.lower() in resolved_sector_names:
                    continue
                coverage_fb = await self._graph.run(cql.SECTOR_COVERAGE, sector_name=leaf)
                cyphers.append(f"SECTOR_COVERAGE(taxonomy-fallback:{leaf})")
                for row in coverage_fb:
                    themes = ", ".join(t for t in row["risk_themes"] if t) or "none flagged"
                    facts.append(GraphFact(
                        fact_id=str(uuid4()),
                        statement=f"{row['analyst']} covers {row['issuer']} (risk themes: {themes})",
                        subject=row["analyst"], predicate="COVERS", object=row["issuer"],
                        properties={"risk_themes": row["risk_themes"]},
                        traversal_path=f"Analyst→COVERS→Issuer→IN_SECTOR→Sector({leaf})",
                    ))
                if coverage_fb:
                    paths.append(f"Taxonomy-fallback: {leaf} sector coverage "
                                 f"({len(coverage_fb)} analyst-issuer pairs)")
                    break

        # Fallback stage 2: still no facts → surface at least which issuers are IN
        # the sector, so the synthesis has some graph grounding.
        if not facts:
            for path in (intent.taxonomy_paths or []):
                leaf = path.split("/")[-1].strip()
                if not leaf:
                    continue
                issuer_rows = await self._graph.run(cql.SECTOR_ISSUER_LIST, sector_name=leaf)
                cyphers.append(f"SECTOR_ISSUER_LIST(fallback:{leaf})")
                for row in issuer_rows:
                    facts.append(GraphFact(
                        fact_id=str(uuid4()),
                        statement=f"{row['issuer']} operates in the {row['sector']} sector",
                        subject=row["issuer"], predicate="IN_SECTOR", object=row["sector"],
                        properties={},
                        traversal_path=f"Issuer→IN_SECTOR→Sector({row['sector']})",
                    ))
                if issuer_rows:
                    paths.append(
                        f"Sector issuer list fallback: {leaf} "
                        f"({len(issuer_rows)} issuers found)"
                    )
                    break

        return facts, paths, cyphers

    async def _entity_lookup(self, intent: QueryIntent, entities: list[BaseEntity]):
        """Entity lookup.

        Args:
            intent (QueryIntent): Classified query intent.
            entities (list[BaseEntity]): List of entity identifiers or objects.

        Returns:
            Result of the operation.
        """
        facts, paths, cyphers = [], [], []
        lookup_names = []
        for e in entities[:3]:
            ename = getattr(e, "name", None)
            if ename and ename not in lookup_names:
                lookup_names.append(ename)
        for m in (intent.entities_mentioned or [])[:3]:
            if m and m not in lookup_names:
                lookup_names.append(m)

        if not lookup_names:
            lookup_names = ["Mutual Funds"]

        entity_rows = await self._gather_rows(
            [(cql.ENTITY_FACTS, {"entity_name": name}) for name in lookup_names[:4]]
        )
        for name, rows in zip(lookup_names[:4], entity_rows):
            if rows:
                cyphers.append("ENTITY_FACTS")
            for row in rows:
                ent_name = row.get("entity") or name
                oth_name = row.get("other") or "Entity"
                rel_type = row.get("rel_type") or "RELATED_TO"
                if row.get("direction") == "out":
                    statement = f"{ent_name} {rel_type} {oth_name}"
                else:
                    statement = f"{oth_name} {rel_type} {ent_name}"
                props = {k: v for k, v in (row.get("props") or {}).items()
                         if k not in ("extraction_method", "confidence", "source_document_id")}
                if props:
                    statement += f" ({', '.join(f'{k}={v}' for k, v in props.items())})"
                facts.append(GraphFact(
                    fact_id=str(uuid4()),
                    statement=statement,
                    subject=ent_name, predicate=rel_type, object=oth_name,
                    properties=props,
                    traversal_path=f"{row.get('entity', 'Entity')}→{rel_type}→{row.get('other_type', 'Entity')}",
                ))
            if rows:
                paths.append(f"1-hop neighborhood of {name} ({len(rows)} facts)")

        # Subgraph fallback if no exact entity rows found
        if not facts:
            try:
                from app.engine import graph_store
                q_ents = [{"text": n} for n in lookup_names]
                sub = graph_store.get_subgraph_for_query_with_fallback(
                    query=" ".join(lookup_names),
                    limit=12,
                    query_entities=q_ents
                )
                edges = sub.get("edges", [])
                if edges:
                    cyphers.append("SUBGRAPH_FALLBACK")
                for e in edges:
                    s_name = e.get("s") or "Entity"
                    o_name = e.get("o") or "Target"
                    rel_name = e.get("rel") or "CONNECTED_TO"
                    facts.append(GraphFact(
                        fact_id=str(uuid4()),
                        statement=f"{s_name} {rel_name} {o_name}",
                        subject=s_name, predicate=rel_name, object=o_name,
                        properties={"confidence": e.get("conf", 1.0)},
                        traversal_path=f"{e.get('s_label', 'Entity')}→{rel_name}→{e.get('o_label', 'Entity')}",
                    ))
                if edges:
                    paths.append(f"Connected knowledge graph neighborhood ({len(edges)} facts)")
            except Exception as f_exc:
                logger.debug("Entity lookup subgraph fallback notice: %s", f_exc)

        return facts, paths, cyphers

    async def _noop(self, intent: QueryIntent, entities: list[BaseEntity]):
        """Noop.

        Args:
            intent (QueryIntent): Classified query intent.
            entities (list[BaseEntity]): List of entity identifiers or objects.

        Returns:
            Result of the operation.
        """
        return [], [], []
