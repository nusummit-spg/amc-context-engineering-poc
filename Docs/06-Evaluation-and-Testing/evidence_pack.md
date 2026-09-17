📦
📐 Frozen at Delivery
EvidencePack D0–D3: The Immutable Snapshot
The moment a response is delivered, an immutable EvidencePack is created and frozen in storage. All later evaluation references this snapshot—never the live system state. This anchor makes every diagnosis deterministic and auditable.

D0 — Response Finalization
response_id: resp_9c4f1a
response_hash: a7f3c9...d821 (SHA-256)
model_id: claude-3-5-sonnet
prompt_template_version: v2.4.1
citations_shown: [AMFI_v18, perf_v3, mirae_v2]
input_tokens, output_tokens, latency
truncation_flag: FALSE
D1 — Interaction Snapshot
interaction_id: int_8b2e7f
detected_intent: CURRENT_NUMERIC_FACT + COMPARATIVE_CLAIM
entities: INF846K01DP5, INF769K01EW8 (canonical IDs)
attributes: [TER, NAV, 5yr_return]
jurisdiction: IN
channel, user_role, timestamp
D2 — Evidence Pack (Core Metrics)
chunk_ids: Retrieved chunks + rank scores
source_version: AMFI_v18 (2026-08-17)
source_age_days: 3
source_version_mismatch: FALSE
citation_coverage: 3/3 (100%)
evidence_rejected: Chunks dropped at reranking
vector_graph_overlap: HIGH
context_truncation: FALSE
D3 — Policy & Applicability Context
jurisdiction: IN
policy_pack: INDIA_SEBI_v2026_03
applicable_controls: [C01,C02,C03,C07,C08]
mandatory_controls: [C02_source_currency, C03_numeric_accuracy, C07_disclosure]
advice_flag: FALSE
interaction_mode: INFORMATION
🔒
Why D0–D3 are frozen immediately and never modified: If the AMFI file updates to v19 tomorrow (TER changes to 0.85%), the evaluation of today's response must still use source_version=AMFI_v18. Without this freeze, we'd retrospectively judge the response as wrong using knowledge that didn't exist at response time. This also lets a compliance auditor reconstruct exactly what the system knew, said, and cited for any response years later.
Why Each D2 Field Matters for Diagnosis
source_version + source_age_days
Distinguish F05 (stale source) from F07 (hallucination)
evidence_rejected[]
Distinguish F09 (context drop) from F04 (retrieval miss)
citation_coverage + chunk_ids
Verify F06 (citation integrity) vs F04 (retrieval rank)
vector_graph_overlap
Passive anomaly: if overlap LOW, signal retrieval degradation
response_hash
Deterministic proof of what was said, not retroactive claim
template_coverage
Track completeness for COMPARATIVE_CLAIM intent