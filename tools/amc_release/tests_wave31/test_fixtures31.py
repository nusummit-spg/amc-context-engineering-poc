"""WP00 fixture contract. Pure local tests: no services, no credentials."""
import json
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tools.amc_release import fixtures31 as fx

REPO = Path(__file__).resolve().parents[3]
MANIFEST = REPO / "remediation" / "wave3_1" / "TEST_FIXTURE_MANIFEST.json"
TENANTS = (fx.TENANT_ALPHA, fx.TENANT_BETA)


def test_build_is_deterministic():
    assert fx.build_manifest() == fx.build_manifest()
    assert fx.corpus(fx.TENANT_ALPHA, "A") == fx.corpus(fx.TENANT_ALPHA, "A")


def test_committed_manifest_matches_generated():
    assert MANIFEST.is_file(), "run: python -m tools.amc_release.fixtures31 --write <manifest>"
    assert json.loads(MANIFEST.read_text(encoding="utf-8")) == fx.build_manifest()


def test_manifest_declares_synthetic_and_secret_free():
    m = fx.build_manifest()
    assert m["synthetic"] is True and m["contains_secrets"] is False
    flat = json.dumps({k: v for k, v in m.items() if k != "contains_secrets"}).lower()
    for needle in ("password", "secret", "api_key", "private key", "bearer "):
        assert needle not in flat, needle


@pytest.mark.parametrize("tenant", TENANTS)
@pytest.mark.parametrize("gen", ["A", "B"])
def test_corpus_is_complete_tenant_bound_and_synthetic(tenant, gen):
    rows = fx.corpus(tenant, gen)
    assert len(rows) >= 3
    ids = [r["chunk_id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert all(r["tenant_id"] == tenant and r["chunk_id"].startswith(tenant + ":") for r in rows)
    assert all(fx.SYNTHETIC_MARKER in r["text"] for r in rows)


def test_document_ids_overlap_across_tenants_with_different_text():
    shared = set(fx.build_manifest()["shared_document_ids"])
    assert shared >= {"DOC-001", "DOC-002", "DOC-003"}
    a = {r["document_id"]: r["text"] for r in fx.corpus(fx.TENANT_ALPHA, "A")}
    b = {r["document_id"]: r["text"] for r in fx.corpus(fx.TENANT_BETA, "A")}
    assert all(a[d] != b[d] for d in shared)


def test_no_cross_tenant_content_in_corpus_or_graph():
    for gen in ("A", "B"):
        alpha = json.dumps([fx.corpus(fx.TENANT_ALPHA, gen), fx.graph_edges(fx.TENANT_ALPHA, gen)])
        beta = json.dumps([fx.corpus(fx.TENANT_BETA, gen), fx.graph_edges(fx.TENANT_BETA, gen)])
        assert "Beta" not in alpha and "beta" not in alpha
        assert "Alpha" not in beta and "alpha" not in beta


def test_generation_b_changes_the_probed_facts_only():
    for tenant in TENANTS:
        a = {r["document_id"]: r["text"] for r in fx.corpus(tenant, "A")}
        b = {r["document_id"]: r["text"] for r in fx.corpus(tenant, "B")}
        changed = {d for d in a if a[d] != b[d]}
        assert changed, "generation B must differ from A so rollback is observable"
        assert {"DOC-001", "DOC-003"} <= changed


@pytest.mark.parametrize("tenant", TENANTS)
@pytest.mark.parametrize("gen", ["A", "B"])
def test_probes_point_at_chunks_that_prove_the_expected_answer(tenant, gen):
    by_id = {r["chunk_id"]: r["text"] for r in fx.corpus(tenant, gen)}
    for p in fx.probes(tenant):
        cited = by_id[p["expected_citations"][gen]]
        assert p["must_contain"][gen] in cited
        assert not any(bad in cited for bad in p["must_not_contain"])


def test_fault_hooks_and_tamper_cases_cover_the_design_spec():
    m = fx.build_manifest()
    assert len(m["tamper_cases"]) >= 6 and len(m["fault_hooks"]) == 6
    assert {u["role"] for u in m["users"]} == {"user", "admin"}
    assert all("password" not in u for u in m["users"])


@pytest.mark.parametrize("tenant", TENANTS)
def test_fixture_corpus_is_accepted_by_the_real_journal(tenant, tmp_path):
    """The snapshot shape is the one amc_publication.journal.submit really accepts."""
    import sys
    sys.path.insert(0, str(REPO / "backend"))
    from amc_publication.models import Base
    from amc_publication.journal import Journal
    engine = create_engine(f"sqlite:///{tmp_path / 'j.db'}")
    Base.metadata.create_all(engine)
    journal = Journal(sessionmaker(bind=engine))
    work = journal.submit(tenant=tenant, key="fx", proposal_id="P", revision=1,
                          payload={"entity": "E", "attribute": "a", "corrected_value": "v",
                                   "full_vector_snapshot": fx.corpus(tenant, "A")})
    assert work


def test_no_secret_like_strings_in_fixture_source():
    src = Path(fx.__file__).read_text(encoding="utf-8")
    assert not re.search(r"(?i)(password|passwd|secret|token)\s*=\s*['\"][^'\"]+['\"]", src)
    assert "BEGIN PRIVATE KEY" not in src
