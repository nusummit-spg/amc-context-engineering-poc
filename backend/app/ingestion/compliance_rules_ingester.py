# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
compliance_rules_ingester.py
============================
Ingests regulatory circulars, deterministic compliance rules, and fund scheme
metadata from CSV files into the Neo4j compliance graph.
"""
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.graph.client import GraphClient, get_graph_client

logger = logging.getLogger("compliance.ingester")


class ComplianceRulesIngester:
    """Ingests regulatory rules from CSV files into Neo4j compliance graph."""

    def __init__(self, graph_client: Optional[GraphClient] = None):
        self.graph = graph_client or get_graph_client()

    async def ingest_regulations_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        CSV columns: region | regulation_id | title | effective_date | document_url | raw_text
        """
        regulations_created = 0
        errors = []

        if not csv_path.exists():
            return {"status": "error", "message": f"File not found: {csv_path}"}

        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    reg_id = row.get("regulation_id")
                    if not reg_id:
                        continue
                    try:
                        cypher = """
                        MERGE (r:Regulation {id: $reg_id})
                        SET r.title = $title,
                            r.region = $region,
                            r.effective_date = $eff_date,
                            r.section = $section,
                            r.description = $description,
                            r.applicability = $applicability,
                            r.document_url = $url,
                            r.raw_text = $text,
                            r.created_at = coalesce(r.created_at, $now)
                        RETURN r.id AS id
                        """
                        await self.graph.run(
                            cypher,
                            reg_id=reg_id,
                            title=row.get("title", ""),
                            region=row.get("region", "SEBI"),
                            eff_date=row.get("effective_date", ""),
                            section=row.get("section", ""),
                            description=row.get("description", ""),
                            applicability=row.get("applicability", ""),
                            url=row.get("document_url", ""),
                            text=row.get("raw_text", ""),
                            now=datetime.now().isoformat(),
                        )
                        regulations_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx} ({reg_id}): {str(e)}")
                        logger.warning("Failed to ingest regulation at row %d: %s", row_idx, e)
        except Exception as e:
            logger.error("Failed to read regulations CSV from %s: %s", csv_path, e)
            return {"status": "error", "message": str(e)}

        logger.info("Ingested %d regulations from %s (%d errors)", regulations_created, csv_path, len(errors))
        return {
            "status": "success",
            "regulations_created": regulations_created,
            "errors": errors,
            "error_count": len(errors),
        }

    async def ingest_rules_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        CSV columns: rule_id | rule_type | title | description | regulation_id |
                     condition | metric | threshold | severity | confidence_threshold |
                     applicable_funds | region
        """
        rules_created = 0
        errors = []

        if not csv_path.exists():
            return {"status": "error", "message": f"File not found: {csv_path}"}

        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    rule_id = row.get("rule_id")
                    if not rule_id:
                        continue
                    try:
                        app_raw = row.get("applicability_categories") or row.get("applicable_funds", "[]")
                        excl_raw = row.get("exclusion_categories", "[]")
                        applicability = json.loads(app_raw) if (app_raw and app_raw.startswith("[")) else [app_raw] if app_raw else []
                        exclusions = json.loads(excl_raw) if (excl_raw and excl_raw.startswith("[")) else [excl_raw] if excl_raw else []

                        conf_thresh = float(row.get("confidence_threshold", 0.95))

                        cypher = """
                        MERGE (r:Rule {id: $rule_id})
                        SET r.rule_type = $rule_type,
                            r.title = $title,
                            r.description = $description,
                            r.regulation_id = $regulation_id,
                            r.condition = $condition,
                            r.metric = $metric,
                            r.threshold = $threshold,
                            r.severity = $severity,
                            r.region = $region,
                            r.confidence_threshold = $conf_threshold,
                            r.applicability = $applicability,
                            r.exclusions = $exclusions,
                            r.enforcement_level = $enforcement_level,
                            r.active = true,
                            r.created_at = coalesce(r.created_at, $now)
                        WITH r
                        OPTIONAL MATCH (reg:Regulation {id: $regulation_id})
                        FOREACH (_ IN CASE WHEN reg IS NOT NULL THEN [1] ELSE [] END |
                            MERGE (r)-[:basedOn]->(reg)
                        )
                        RETURN r.id AS id
                        """
                        await self.graph.run(
                            cypher,
                            rule_id=rule_id,
                            rule_type=row.get("rule_type", "portfolio"),
                            title=row.get("title", ""),
                            description=row.get("description", ""),
                            regulation_id=row.get("regulation_id", ""),
                            condition=row.get("condition", ""),
                            metric=row.get("metric", ""),
                            threshold=row.get("threshold", ""),
                            severity=row.get("severity", "high"),
                            region=row.get("region", "SEBI"),
                            conf_threshold=conf_thresh,
                            applicability=applicability,
                            exclusions=exclusions,
                            enforcement_level=row.get("enforcement_level", "automatic"),
                            now=datetime.now().isoformat(),
                        )
                        rules_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx} ({rule_id}): {str(e)}")
                        logger.warning("Failed to ingest rule at row %d: %s", row_idx, e)
        except Exception as e:
            logger.error("Failed to read rules CSV from %s: %s", csv_path, e)
            return {"status": "error", "message": str(e)}

        logger.info("Ingested %d rules from %s (%d errors)", rules_created, csv_path, len(errors))
        return {
            "status": "success",
            "rules_created": rules_created,
            "errors": errors,
            "error_count": len(errors),
        }

    async def ingest_fund_schemes_csv(self, csv_path: Path) -> Dict[str, Any]:
        """
        CSV columns: fund_id | isin | name | fund_house | category | mandate |
                     risk_profile | aum_cr | region | rules_applicable_ids
        """
        funds_created = 0
        errors = []

        if not csv_path.exists():
            return {"status": "error", "message": f"File not found: {csv_path}"}

        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row_idx, row in enumerate(reader, start=2):
                    fund_id = row.get("fund_id")
                    if not fund_id:
                        continue
                    try:
                        rule_ids_raw = row.get("rules_applicable_ids", "[]")
                        rule_ids = json.loads(rule_ids_raw) if (rule_ids_raw and rule_ids_raw.startswith("[")) else []
                        aum_val = float(row.get("aum_cr", 0.0))

                        cypher = """
                        MERGE (f:FundScheme {id: $fund_id})
                        SET f.isin = $isin,
                            f.name = $name,
                            f.fund_house = $fund_house,
                            f.category = $category,
                            f.mandate = $mandate,
                            f.risk_profile = $risk_profile,
                            f.aum_cr = $aum,
                            f.region = $region,
                            f.created_at = coalesce(f.created_at, $now)
                        WITH f
                        UNWIND $rule_ids AS rid
                        MATCH (r:Rule {id: rid})
                        MERGE (f)-[:governedBy]->(r)
                        RETURN f.id AS id
                        """
                        await self.graph.run(
                            cypher,
                            fund_id=fund_id,
                            isin=row.get("isin", ""),
                            name=row.get("name", ""),
                            fund_house=row.get("fund_house", ""),
                            category=row.get("category", "equity_fund"),
                            mandate=row.get("mandate", ""),
                            risk_profile=row.get("risk_profile", "High"),
                            aum=aum_val,
                            region=row.get("region", "SEBI"),
                            rule_ids=rule_ids,
                            now=datetime.now().isoformat(),
                        )
                        funds_created += 1
                    except Exception as e:
                        errors.append(f"Row {row_idx} ({fund_id}): {str(e)}")
                        logger.warning("Failed to ingest fund scheme at row %d: %s", row_idx, e)
        except Exception as e:
            logger.error("Failed to read fund schemes CSV from %s: %s", csv_path, e)
            return {"status": "error", "message": str(e)}

        logger.info("Ingested %d fund schemes from %s (%d errors)", funds_created, csv_path, len(errors))
        return {
            "status": "success",
            "funds_created": funds_created,
            "errors": errors,
            "error_count": len(errors),
        }


async def seed_compliance_data(
    graph_client: Optional[GraphClient] = None,
    data_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Seed all compliance regulations, rules, and fund schemes across SEBI, SEC, and ESMA."""
    if data_dir is None:
        data_dir = Path(__file__).resolve().parents[2] / "data" / "compliance"

    ingester = ComplianceRulesIngester(graph_client)
    results = {
        "regulations": await ingester.ingest_regulations_csv(data_dir / "sebi_regulations.csv"),
        "rules": await ingester.ingest_rules_csv(data_dir / "rules.csv"),
        "funds": await ingester.ingest_fund_schemes_csv(data_dir / "fund_schemes.csv"),
    }

    # Ingest SEC & ESMA datasets if present
    sec_reg = data_dir / "sec_regulations.csv"
    if sec_reg.exists():
        results["sec_regulations"] = await ingester.ingest_regulations_csv(sec_reg)
    sec_rules = data_dir / "sec_rules.csv"
    if sec_rules.exists():
        results["sec_rules"] = await ingester.ingest_rules_csv(sec_rules)

    esma_reg = data_dir / "esma_regulations.csv"
    if esma_reg.exists():
        results["esma_regulations"] = await ingester.ingest_regulations_csv(esma_reg)
    esma_rules = data_dir / "esma_rules.csv"
    if esma_rules.exists():
        results["esma_rules"] = await ingester.ingest_rules_csv(esma_rules)

    return results

