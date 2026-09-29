"""
adapters.py
===========
Bridges amc-feedback-loop and amc-repair-engine modular packages
into the AMC Backend platform infrastructure.
"""
import logging
from pathlib import Path
from typing import Any, Optional

from amc_feedback import FeedbackConfig, FeedbackLoop, SQLiteAdapter as FeedbackSQLiteAdapter
from amc_repair import RepairConfig, RepairEngine, MemoryCacheAdapter, GraphAdapter, MemoryGraphAdapter

from app.core.database import BASE_DIR
from app.engine import config as engine_config

logger = logging.getLogger("app.core.adapters")

_feedback_loop_instance: Optional[FeedbackLoop] = None
_repair_engine_instance: Optional[RepairEngine] = None


class PlatformNeo4jGraphAdapter(GraphAdapter):
    """Bridges RepairEngine's GraphAdapter with AMC backend's graph store / driver."""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j"):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            try:
                from neo4j import GraphDatabase
                self._driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            except Exception as e:
                logger.warning("Neo4j driver connection failed: %s", e)
        return self._driver

    async def apply_entity_patch(self, entity_id: str, attribute: str, value: Any) -> bool:
        driver = self._get_driver()
        if not driver:
            return False
        try:
            cypher = f"""
            MATCH (e) WHERE e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id
            SET e.{attribute} = $value,
                e.{attribute}_updated_at = datetime()
            RETURN count(e) AS updated
            """
            with driver.session(database=self.database) as session:
                res = session.run(cypher, entity_id=entity_id, value=value)
                record = res.single()
                return bool(record and record["updated"] > 0)
        except Exception as exc:
            logger.error("Failed to apply entity patch to Neo4j: %s", exc)
            return False

    async def get_entity_property(self, entity_id: str, attribute: str) -> Optional[Any]:
        driver = self._get_driver()
        if not driver:
            return None
        try:
            cypher = f"""
            MATCH (e) WHERE e.isin = $entity_id OR e.id = $entity_id OR e.name = $entity_id
            RETURN e.{attribute} AS val
            """
            with driver.session(database=self.database) as session:
                res = session.run(cypher, entity_id=entity_id)
                record = res.single()
                return record["val"] if record else None
        except Exception as exc:
            logger.error("Failed to query entity property from Neo4j: %s", exc)
            return None

    async def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None


def create_feedback_config() -> FeedbackConfig:
    fund_master_path = BASE_DIR / "data" / "raw" / "fund_names_cleaned.json"
    return FeedbackConfig(
        domain_name="amc",
        entity_types=["fund", "scheme", "amc", "regulation"],
        attribute_keywords={
            "TER": ["ter", "expense ratio", "total expense", "expense"],
            "NAV": ["nav", "net asset value", "price"],
            "AUM": ["aum", "assets under management", "corpus"],
            "EXIT_LOAD": ["exit load", "exit penalty", "redemption fee"],
        },
        entity_master_path=str(fund_master_path) if fund_master_path.exists() else None,
        fuzzy_match_threshold=0.70,
        use_spacy=True,
        use_gliner=True,
        gliner_model_id=engine_config.GLINER_MODEL_ID,
        enable_onnx=engine_config.ENABLE_ONNX_GLINER,
        dissatisfaction_threshold=0.65,
        correction_confidence_min=0.60,
        enable_passive_capture=True,
        passive_timeout_seconds=180,
    )


def create_repair_config() -> RepairConfig:
    return RepairConfig(
        patch_ttl_days=7,
        patch_confidence_threshold=0.70,
        use_redis=False,
        enable_tier1_rules=True,
        auto_approve_confidence=0.80,
        graph_adapter="neo4j",
        graph_uri=engine_config.NEO4J_URI,
        graph_user=engine_config.NEO4J_USER,
        graph_password=engine_config.NEO4J_PASSWORD,
        graph_database=engine_config.NEO4J_DATABASE,
    )


def get_feedback_loop() -> FeedbackLoop:
    global _feedback_loop_instance
    if _feedback_loop_instance is None:
        cfg = create_feedback_config()
        db_path = str(BASE_DIR / "data.db")
        db_adapter = FeedbackSQLiteAdapter(db_path)
        _feedback_loop_instance = FeedbackLoop(config=cfg, db_adapter=db_adapter)
    return _feedback_loop_instance


def get_repair_engine() -> RepairEngine:
    global _repair_engine_instance
    if _repair_engine_instance is None:
        cfg = create_repair_config()
        cache = MemoryCacheAdapter()
        graph = PlatformNeo4jGraphAdapter(
            uri=cfg.graph_uri or "bolt://localhost:7687",
            user=cfg.graph_user or "neo4j",
            password=cfg.graph_password or "password",
            database=cfg.graph_database or "neo4j",
        )
        _repair_engine_instance = RepairEngine(config=cfg, cache_adapter=cache, graph_adapter=graph)
    return _repair_engine_instance
