"""Deterministic SYNTHETIC fixtures for AMC Wave 3.1 pilot qualification (WP00).

Everything here is invented: fictional funds, fictional tenants, no customer data,
no credentials and no signing keys. Passwords and keys are generated at test time
and must never be written into this module or the manifest.

    python -m tools.amc_release.fixtures31 --write remediation/wave3_1/TEST_FIXTURE_MANIFEST.json
    python -m tools.amc_release.fixtures31 --check remediation/wave3_1/TEST_FIXTURE_MANIFEST.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

FIXTURE_VERSION = "amc-wave31-fixtures-v1"
SYNTHETIC_MARKER = "SYNTHETIC-FIXTURE"
TENANT_ALPHA = "tenant_alpha"
TENANT_BETA = "tenant_beta"

# Same document IDs in both tenants on purpose (NFR01): content differs, so any
# cross-tenant leak is visible in the answer text and in the citations.
_SHARED_DOC_IDS = ("DOC-001", "DOC-002", "DOC-003")

# (document_id, tenant) -> (title, taxonomy_path, fact sentence per generation)
_FACTS = {
    TENANT_ALPHA: {
        "DOC-001": ("Alpha Liquid Fund factsheet", "scheme/liquid", {
            "A": "Alpha Liquid Fund total expense ratio is 0.21 percent.",
            "B": "Alpha Liquid Fund total expense ratio is 0.19 percent."}),
        "DOC-002": ("Alpha Equity Fund factsheet", "scheme/equity", {
            "A": "Alpha Equity Fund minimum lumpsum investment is 5000 rupees.",
            "B": "Alpha Equity Fund minimum lumpsum investment is 5000 rupees."}),
        "DOC-003": ("Alpha Debt Fund factsheet", "scheme/debt", {
            "A": "Alpha Debt Fund exit load is 1 percent within 30 days.",
            "B": "Alpha Debt Fund exit load is 0.5 percent within 30 days."}),
        "DOC-A04": ("Alpha tenant only note", "scheme/notes", {
            "A": "Alpha tenant only note: the alpha review window closes on the first of the month.",
            "B": "Alpha tenant only note: the alpha review window closes on the first of the month."}),
    },
    TENANT_BETA: {
        "DOC-001": ("Beta Liquid Fund factsheet", "scheme/liquid", {
            "A": "Beta Liquid Fund total expense ratio is 0.35 percent.",
            "B": "Beta Liquid Fund total expense ratio is 0.33 percent."}),
        "DOC-002": ("Beta Equity Fund factsheet", "scheme/equity", {
            "A": "Beta Equity Fund minimum lumpsum investment is 10000 rupees.",
            "B": "Beta Equity Fund minimum lumpsum investment is 10000 rupees."}),
        "DOC-003": ("Beta Debt Fund factsheet", "scheme/debt", {
            "A": "Beta Debt Fund exit load is 2 percent within 90 days.",
            "B": "Beta Debt Fund exit load is 1.5 percent within 90 days."}),
        "DOC-B04": ("Beta tenant only note", "scheme/notes", {
            "A": "Beta tenant only note: the beta audit committee meets every quarter.",
            "B": "Beta tenant only note: the beta audit committee meets every quarter."}),
    },
}

# Natural-language probes and what an authorized answer must contain / must never contain.
_PROBES = {
    TENANT_ALPHA: [
        {"id": "alpha_ter", "query": "What is the total expense ratio of the Liquid Fund?",
         "document_id": "DOC-001", "must_contain": {"A": "0.21", "B": "0.19"},
         "must_not_contain": ["0.35", "0.33", "Beta"]},
        {"id": "alpha_exit_load", "query": "What is the exit load of the Debt Fund?",
         "document_id": "DOC-003", "must_contain": {"A": "1 percent", "B": "0.5 percent"},
         "must_not_contain": ["2 percent", "1.5 percent", "Beta"]},
    ],
    TENANT_BETA: [
        {"id": "beta_ter", "query": "What is the total expense ratio of the Liquid Fund?",
         "document_id": "DOC-001", "must_contain": {"A": "0.35", "B": "0.33"},
         "must_not_contain": ["0.21", "0.19", "Alpha"]},
        {"id": "beta_min_lumpsum", "query": "What is the minimum lumpsum investment of the Equity Fund?",
         "document_id": "DOC-002", "must_contain": {"A": "10000", "B": "10000"},
         "must_not_contain": ["5000 rupees", "Alpha"]},
    ],
}

# Graph: two tenant-scoped edges per tenant. One edge (the TER) is the mutated one.
_GRAPH = {
    TENANT_ALPHA: [
        {"source": "Alpha Liquid Fund", "relation": "HAS_TER", "target": {"A": "0.21", "B": "0.19"}},
        {"source": "Alpha Debt Fund", "relation": "HAS_EXIT_LOAD", "target": {"A": "1%/30d", "B": "0.5%/30d"}},
    ],
    TENANT_BETA: [
        {"source": "Beta Liquid Fund", "relation": "HAS_TER", "target": {"A": "0.35", "B": "0.33"}},
        {"source": "Beta Debt Fund", "relation": "HAS_EXIT_LOAD", "target": {"A": "2%/90d", "B": "1.5%/90d"}},
    ],
}

# Failure cases are DESCRIPTORS only. Tests materialize them from a real disposable
# FAISS build; no binary index, key or signature is stored in Git.
TAMPER_CASES = (
    {"id": "gen_c_tampered_bytes", "mutation": "flip one byte of the index file after signing"},
    {"id": "gen_c_missing_index", "mutation": "delete the index file but keep the manifest"},
    {"id": "gen_c_invalid_signature", "mutation": "sign the manifest with a different disposable key"},
    {"id": "gen_c_wrong_tenant", "mutation": "bind the manifest to tenant_beta but publish for tenant_alpha"},
    {"id": "gen_c_digest_mismatch", "mutation": "alter the manifest digest field only"},
    {"id": "gen_c_duplicate_chunk_id", "mutation": "repeat one chunk_id inside the snapshot"},
)

FAULT_HOOKS = (
    "after_scope_claim", "after_graph_write", "before_receipt_commit",
    "after_receipt_commit_before_reader_reload", "during_sse_response", "during_rollback",
)

USERS = (
    {"username": "alpha_analyst", "tenant": TENANT_ALPHA, "role": "user"},
    {"username": "beta_analyst", "tenant": TENANT_BETA, "role": "user"},
    {"username": "alpha_operator", "tenant": TENANT_ALPHA, "role": "admin"},
)


def _chunk_id(tenant: str, doc: str, generation: str) -> str:
    return f"{tenant}:{doc}:{generation}:c0"


def corpus(tenant: str, generation: str) -> list[dict]:
    """COMPLETE nonempty snapshot rows in the shape amc_publication journal.submit accepts."""
    if tenant not in _FACTS or generation not in ("A", "B"):
        raise ValueError("unknown tenant or generation")
    rows = []
    for doc, (title, taxonomy, facts) in sorted(_FACTS[tenant].items()):
        rows.append({
            "chunk_id": _chunk_id(tenant, doc, generation),
            "tenant_id": tenant,
            "document_id": doc,
            "source_id": f"src-{doc.lower()}",
            "source_version": generation,
            "title": title,
            "taxonomy_path": taxonomy,
            "text": f"[{SYNTHETIC_MARKER}] {facts[generation]}",
        })
    return rows


def graph_edges(tenant: str, generation: str) -> list[dict]:
    return [{"tenant_id": tenant, "source": e["source"], "relation": e["relation"],
             "target": e["target"][generation]} for e in _GRAPH[tenant]]


def probes(tenant: str) -> list[dict]:
    out = []
    for p in _PROBES[tenant]:
        out.append({
            "id": p["id"], "tenant_id": tenant, "query": p["query"],
            "expected_citations": {g: _chunk_id(tenant, p["document_id"], g) for g in ("A", "B")},
            "must_contain": dict(p["must_contain"]),
            "must_not_contain": list(p["must_not_contain"]),
        })
    return out


def canonical_json(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_obj(obj) -> str:
    return hashlib.sha256(canonical_json(obj)).hexdigest()


def build_manifest() -> dict:
    tenants = {}
    for tenant in (TENANT_ALPHA, TENANT_BETA):
        tenants[tenant] = {
            "documents": sorted(_FACTS[tenant]),
            "corpus_sha256": {g: sha256_obj(corpus(tenant, g)) for g in ("A", "B")},
            "graph_sha256": {g: sha256_obj(graph_edges(tenant, g)) for g in ("A", "B")},
            "probes_sha256": sha256_obj(probes(tenant)),
            "expected_citations": {p["id"]: p["expected_citations"] for p in probes(tenant)},
        }
    shared = sorted(set(_FACTS[TENANT_ALPHA]) & set(_FACTS[TENANT_BETA]))
    body = {
        "fixture_version": FIXTURE_VERSION,
        "synthetic": True,
        "license": "Invented test data created for this repository; no third-party source text.",
        "contains_secrets": False,
        "tenants": tenants,
        "shared_document_ids": shared,
        "users": [dict(u) for u in USERS],
        "tamper_cases": [dict(c) for c in TAMPER_CASES],
        "fault_hooks": list(FAULT_HOOKS),
        "generations": {"A": "initial ACTIVE", "B": "staged then ACTIVE; changes TER and exit-load facts",
                        "C": "tampered variants, see tamper_cases"},
    }
    body["fixture_set_sha256"] = sha256_obj(body)
    return body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", type=Path)
    group.add_argument("--check", type=Path)
    args = parser.parse_args(argv)
    manifest = build_manifest()
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.write} fixture_set_sha256={manifest['fixture_set_sha256']}")
        return 0
    committed = json.loads(args.check.read_text(encoding="utf-8"))
    if committed != manifest:
        print("MANIFEST MISMATCH: regenerate with --write and review the diff", file=sys.stderr)
        return 2
    print(f"manifest OK fixture_set_sha256={manifest['fixture_set_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
