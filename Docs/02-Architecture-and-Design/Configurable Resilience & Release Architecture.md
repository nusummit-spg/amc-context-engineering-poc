# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

# Implementation Plan — Configurable Resilience & Release Architecture

Implement the 4 strategic enhancements as strictly configurable features with safe, production-grade defaults (e.g., `enable_local_llm_fallback=False`, `enable_multi_provider_fallback=False`, API-key based providers).

---

## User Review Required

> [!IMPORTANT]
> - **API-Key Centric**: Multi-provider support uses standard API keys for Anthropic, OpenAI, and Gemini.
> - **Disabled by Default**: `enable_multi_provider_fallback` and `enable_local_llm_fallback` default to `False`. Primary provider execution is strictly preserved unless explicitly toggled in `.env`.
> - **Safe Canary Rollout**: `QUERY_ENGINE=canary` routes traffic based on `CANARY_PERCENTAGE` (default `0`).

---

## Proposed Changes

### Component 1: Central Configuration (`backend/app/config.py`)
#### [MODIFY] [`backend/app/config.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/config.py)
Add settings:
- `llm_provider: str = "anthropic"` (`"anthropic"`, `"openai"`, `"gemini"`)
- `anthropic_api_key: Optional[str] = None`
- `openai_api_key: Optional[str] = None`
- `gemini_api_key: Optional[str] = None`
- `enable_multi_provider_fallback: bool = False` (Default `False`)
- `enable_local_llm_fallback: bool = False` (Default `False`)
- `local_llm_endpoint: str = "http://127.0.0.1:11434/v1"`
- `enable_pre_retrieval_guardrails: bool = True` (Default `True`)
- `enable_cache_invalidation_on_ingest: bool = True` (Default `True`)
- `canary_percentage: int = 0` (Default `0`)

---

### Component 2: Multi-Provider LLM Synthesizer & Adapter
#### [MODIFY] [`backend/app/retrieval/synthesizer.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/retrieval/synthesizer.py)
- Support provider switching based on `settings.llm_provider` (`anthropic`, `openai`, `gemini`).
- Execute multi-provider fallback only if `enable_multi_provider_fallback == True`.
- Execute local LLM fallback only if `enable_local_llm_fallback == True`.
- Maintain clean extractive fallback when all enabled API providers are unavailable.

---

### Component 3: Pre-Retrieval Safety Guardrail Interceptor
#### [MODIFY] [`backend/app/retrieval/orchestrator.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/retrieval/orchestrator.py)
- When `enable_pre_retrieval_guardrails == True`:
  - Check for SEBI guaranteed-return queries (*"guarantee 15% return"*, *"fixed guaranteed profit"*).
  - Check for explicit out-of-corpus/unrelated queries.
  - Return deterministic compliant refusal with `<5ms` latency and `0` token expenditure.

---

### Component 4: Event-Driven Cache Invalidation on Ingest
#### [MODIFY] [`backend/app/ingestion/pipeline.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/ingestion/pipeline.py)
- When a document version is activated (`IngestionStage.ACTIVATED`), if `enable_cache_invalidation_on_ingest == True`, invoke `cache.invalidate(corpus_version=self._corpus_version)`.

---

### Component 5: Canary Routing Engine
#### [MODIFY] [`backend/app/api/routes/query.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/api/routes/query.py) and [`backend/app/api/routes/chat.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/app/api/routes/chat.py)
- Add `engine == "canary"` handling:
  - Hashes request query / session ID to assign traffic according to `settings.canary_percentage`.
  - Sets response header/metadata `serving_engine="canary-v2"` or `serving_engine="canary-legacy"`.

---

### Component 6: Test Suite for Configurable Enhancements
#### [NEW] [`backend/tests/test_configurable_enhancements.py`](file:///c:/Users/Laptopadmin/Desktop/context-engineering/backend/tests/test_configurable_enhancements.py)
- Test multi-provider configuration & fallback toggles.
- Test pre-retrieval guardrail short-circuiting.
- Test ingestion cache invalidation event trigger.
- Test canary percentage routing distribution.

---

## Verification Plan

### Automated Unit Tests
```powershell
.venv\Scripts\pytest.exe tests/test_configurable_enhancements.py tests/test_source_id_collision.py tests/test_v2_behavior_gap_repairs.py -v
```

### Manual & Integration Validation
1. Verify `enable_multi_provider_fallback=False` does not attempt secondary providers when primary fails.
2. Verify `enable_pre_retrieval_guardrails=True` refuses guaranteed return queries in $<5\text{ms}$.
3. Verify `QUERY_ENGINE=canary` routes accurately according to `CANARY_PERCENTAGE`.
