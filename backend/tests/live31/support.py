"""Helpers for the LIVE31 suite: real PostgreSQL, real Neo4j, real FAISS.

Nothing here replaces the system under test with a mock. The only synthetic piece is the
embedder, which is deterministic and offline so a real FAISS index can be built without a
model download. All data comes from tools/amc_release/fixtures31.py (invented, no secrets).
"""
from __future__ import annotations

import hashlib
import math
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
for p in (str(REPO), str(REPO / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools.amc_release import fixtures31 as fx  # noqa: E402
from amc_publication.journal import Journal  # noqa: E402
from amc_publication.faiss_artifacts import FaissGenerationStore  # noqa: E402
from amc_publication.faiss_reader27 import VerifiedFaissRetriever  # noqa: E402
from amc_publication.serving28 import ActiveReceiptResolver  # noqa: E402
from amc_publication.graph import Neo4jGraphPort  # noqa: E402
from amc_publication.worker import PublicationWorker  # noqa: E402

NAMESPACE = "vector_faiss"
GRAPH_ATTRS = {"ter", "exit_load"}
ALPHA, BETA = fx.TENANT_ALPHA, fx.TENANT_BETA
DIM = 64


class Crash(BaseException):
    """Simulates the process dying at a failpoint (not an Exception, so nothing catches it)."""


def crash_at(point: str):
    def failpoint(name: str):
        if name == point:
            raise Crash(point)
    return failpoint


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder. Offline; real vectors for a real index."""
    _dim = DIM

    @staticmethod
    def _vec(text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in re.findall(r"[a-z0-9.]+", text.lower()):
            h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:4], "big")
            v[h % DIM] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    async def embed_async(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)


def _fixture_tenant(tenant: str) -> str:
    """Per-test tenants (live31_*) reuse the alpha fixture content under their own tenant id."""
    return tenant if tenant in (ALPHA, BETA) else ALPHA


# Facts used for publication: (entity, attribute) -> value per fixture generation.
def graph_target(tenant: str, generation: str) -> tuple[str, str, str]:
    edge = next(e for e in fx.graph_edges(_fixture_tenant(tenant), generation) if e["relation"] == "HAS_TER")
    return edge["source"], "ter", edge["target"]


def snapshot(tenant: str, generation: str) -> list[dict]:
    rows = fx.corpus(_fixture_tenant(tenant), generation)
    if tenant == _fixture_tenant(tenant):
        return rows
    return [{**r, "tenant_id": tenant, "chunk_id": r["chunk_id"].replace(ALPHA, tenant, 1)} for r in rows]


def pg_state(sessions, tenant: str) -> dict:
    """Read the durable publication state straight from PostgreSQL (never via the code under test)."""
    from sqlalchemy import select
    from amc_publication.models import GenerationPointer, PublicationReceipt, PublicationWork, PublicationEffect
    from amc_publication.active_authority28 import ActiveReceiptAuthority, PublicationScopeClaim31
    with sessions() as s:
        a = s.get(ActiveReceiptAuthority, (tenant, NAMESPACE))
        p = s.get(GenerationPointer, (tenant, NAMESPACE))
        c = s.get(PublicationScopeClaim31, (tenant, NAMESPACE))
        works = s.scalars(select(PublicationWork).where(PublicationWork.tenant == tenant)).all()
        receipts = s.scalars(select(PublicationReceipt).where(PublicationReceipt.tenant == tenant)).all()
        effects = s.scalars(select(PublicationEffect).where(PublicationEffect.tenant == tenant)).all()
        return {
            "authority": None if a is None else {"generation": a.generation_id, "digest": a.digest,
                                                  "epoch": a.pointer_epoch, "work": a.work_id,
                                                  "receipt": a.receipt_id, "status": a.status,
                                                  "suspended_by": a.suspended_by},
            "pointer": None if p is None else {"generation": p.generation_id, "digest": p.artifact_digest,
                                                "epoch": p.epoch},
            "claim": None if c is None else {"owner": c.owner_work_id, "status": c.status, "epoch": c.claim_epoch},
            "works": {w.id: w.status for w in works},
            "receipts": [r.id for r in receipts],
            "effects": [(e.work_id, e.kind, e.state) for e in effects],
        }


def serving_allowed(stack, tenant: str) -> bool:
    """True only if the real resolver would serve this tenant right now."""
    from amc_publication.serving27 import ServingDenied
    try:
        stack.retriever.resolver.resolve_for_serving(tenant)
        return True
    except ServingDenied:
        return False


def seed_graph(driver, tenant: str, entity: str, attr: str, value) -> None:
    with driver.session() as s:
        s.run("MERGE (n:Entity {tenant_id:$t, entity_id:$e}) SET n.`%s` = $v" % attr,
              t=tenant, e=entity, v=value).consume()


def read_graph(driver, tenant: str, entity: str, attr: str):
    with driver.session() as s:
        rec = s.run("MATCH (n:Entity {tenant_id:$t, entity_id:$e}) RETURN n.`%s` AS v" % attr,
                    t=tenant, e=entity).single()
        return None if rec is None else rec["v"]


def read_fence(driver, tenant: str, entity: str):
    with driver.session() as s:
        rec = s.run("MATCH (n:Entity {tenant_id:$t, entity_id:$e}) RETURN n.publication_fence AS f",
                    t=tenant, e=entity).single()
        return None if rec is None else rec["f"]


def clean_graph(driver) -> None:
    with driver.session() as s:
        s.run("MATCH (n:Entity) WHERE n.tenant_id STARTS WITH 'tenant_' OR n.tenant_id STARTS WITH 'live31_' "
              "DETACH DELETE n").consume()


@dataclass
class Stack:
    sessions: object
    journal: Journal
    store: FaissGenerationStore
    retriever: VerifiedFaissRetriever
    graph: Neo4jGraphPort
    driver: object
    root: Path

    def worker(self, *, failpoint=None, owner: str | None = None) -> PublicationWorker:
        return PublicationWorker(self.journal, self.graph, self.store,
                                 owner=owner or "w_" + uuid.uuid4().hex[:8],
                                 failpoint=failpoint, serving_probe=self.retriever.probe_activation)

    def submit(self, tenant: str, generation: str, *, key: str | None = None,
               entity: str | None = None, attr: str | None = None, value=None) -> str:
        ent, at, val = graph_target(tenant, generation)
        return self.journal.submit(
            tenant=tenant, key=key or f"{tenant}-{generation}-{uuid.uuid4().hex[:6]}",
            proposal_id=f"P-{generation}", revision=1,
            payload={"entity": entity or ent, "attribute": attr or at,
                     "corrected_value": val if value is None else value,
                     "full_vector_snapshot": snapshot(tenant, generation)})


def alembic_cmd(url: str, action: str, revision: str = "head") -> None:
    """Run Alembic in-process against `url` (disposable databases only)."""
    import os
    from alembic import command
    from alembic.config import Config
    backend = REPO / "backend"
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    old = {k: os.environ.get(k) for k in ("AMC_MIGRATION_DATABASE_URL", "DATABASE_URL")}
    os.environ["AMC_MIGRATION_DATABASE_URL"] = url
    os.environ.pop("DATABASE_URL", None)
    try:
        getattr(command, action)(cfg, revision)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def make_stack(sessions, driver, root: Path, *, lease_seconds: int = 60) -> Stack:
    root.mkdir(parents=True, exist_ok=True)
    journal = Journal(sessions, lease_seconds=lease_seconds)
    store = FaissGenerationStore(root, HashEmbedder())
    retriever = VerifiedFaissRetriever(sessions, root)
    retriever.resolver = ActiveReceiptResolver(sessions, retriever.store, serving_loader=retriever._load)
    graph = Neo4jGraphPort(driver, label="Entity", allowed_attributes=GRAPH_ATTRS)
    return Stack(sessions, journal, store, retriever, graph, driver, root)
