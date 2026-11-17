# AMC Wave 3.1 — Pilot Operator Runbook (WP08 draft)

**Status: DRAFT. NOT REHEARSED.** Nothing below has been executed against live PostgreSQL, Neo4j or
FAISS, and no rollback drill has been run. Treat every procedure as unverified until the matching
gate (G2–G5, G8) has real evidence. This file states what the design requires; it does not prove it.

Use only disposable, localhost-bound services and synthetic data until the release owner says otherwise.
Never put a password, key or token in this file, in Git, in logs, or in a PR comment.

## 1. Known gaps that block a real pilot

1. **No production publication entry point exists.** The only code that drives `PublicationWorker`
   outside tests is `backend/amc_publication/demo_smoke.py`, which runs with `simulation_mode=True`.
   The design calls publication an offline operator/CLI action (design §2.2, §8), but no CLI is in the
   repository. A real worker needs a `FaissGenerationStore`, a `Neo4jGraphPort` and a serving probe.
   Building that entry point is open work and cannot be validated without live services.
2. **Publication owner is unassigned** (scope decision Q4). Someone must be named to publish, revoke,
   recover and sign a corpus.
3. **Readiness is not defined.** `/health` and `/api/health` report liveness only; they do not show
   whether a signed tenant corpus can be served. Do not treat a 200 as "ready".
4. **SLO thresholds are undefined** (Q5) and no staging environment is confirmed (Q6).

## 2. Configuration to freeze before a pilot run

| Setting | Required value | Notes |
|---|---|---|
| `AMC_VERIFIED_SERVING_MODE` | `enforce` | Never switch to `off` to make a failing check pass |
| `QUERY_ENGINE` | `v2` | `legacy`, `canary` and `shadow` are refused in enforce mode |
| `DATABASE_URL` | `postgresql+psycopg://…` | Must be the same database Alembic migrated |
| `AMC_MIGRATION_DATABASE_URL` | identical to `DATABASE_URL` | Compare with SQLAlchemy `make_url`; print masked values only |
| `AMC_VERIFIED_FAISS_ROOT` | path to the signed generation root | Required; serving is denied without it |
| `AMC_PUBLICATION_CORPUS_SNAPSHOT` / `AMC_PUBLICATION_CORPUS_SIGNING_KEY` / `AMC_PUBLICATION_SOURCE_CATALOG` | per the approval adapter | Test key is disposable and never a production secret |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | the disposable instance | Local test password only |
| `VITE_AMC_PILOT_MODE` | `true` at frontend build time | Renders citations as provenance, not dead links |

Record the application commit SHA, flag values and migration revision with the run, without credentials.

## 3. Start sequence

1. Start the disposable providers: `docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml up -d`
   with `AMC_TEST_PG_PASSWORD` and `AMC_TEST_NEO4J_PASSWORD` set in the shell (the file refuses to start without them).
2. From `backend/`, run `python scripts/alembic_dag_preflight.py`, then `python -m alembic -c alembic.ini upgrade head`
   and `… current`. The revision must be `014_publication_scope_claim_v31`. Never downgrade a database that is not disposable.
3. Publish the synthetic corpus through the operator path (see §1, item 1) and confirm an ACTIVE receipt,
   the graph readback and the signed FAISS generation. Do not edit SQL rows by hand to force a state.
4. Start the app in enforce mode, then smoke-test as an authenticated tenant user (not just `/health`).

Startup in enforce mode refuses to run unless the engine is PostgreSQL at exactly revision 014, creates no
schema, and starts no scheduler, ingest queue, FAISS or cache warm-up, or feedback worker.

## 4. Rollback and recovery (design contract, unrehearsed)

- **Separate three things:** runtime serving rollback, Git revert, and database downgrade. Only the first is a rollback
  procedure. A schema downgrade is not.
- **Serving rollback:** stop new publication, suspend authority, confirm the prior graph and FAISS preimage, reconcile the
  work/receipt journal, re-activate only a generation proven to match, then re-run authenticated Q&A.
- **Crash recovery:** a crash at any durable boundary must converge to one verified ACTIVE corpus, or deny serving and leave an
  auditable item for an operator. A stranded HELD scope claim is recovered from durable work identity and the stored
  preimage, never by a time-based force release.
- **If restoration cannot be proven,** serving stays denied and the case goes to operator review.
- **Mid-stream revocation:** content already sent before a rollback cannot be retracted. The guarantee is that no further
  stale content is delivered.

## 5. What to check, and what to never conclude

| Question | Evidence that answers it | Not evidence |
|---|---|---|
| Can a tenant be served? | An authenticated query returns a cited answer and the PG receipt, graph and signed FAISS agree | `/health` returning 200 |
| Is isolation intact? | `tenant_beta` cannot see `tenant_alpha` content, graph edges or citations | A passing mocked test |
| Did rollback work? | Generation A answers again, generation B is absent, the receipt epoch moved forward | A status field alone |
| Are logs clean? | A scan finds no credentials, tokens or document bodies | The absence of an obvious error |

## 6. Hygiene

- Keep raw logs, JUnit files and screenshots in a directory outside the checkout; commit only a sanitized summary.
- Do not commit binary indexes, corpora, signing keys or connection strings.
- Do not run the repository-root `docker-compose.yml`; it carries demo and cloud logging settings.
- Shut the disposable stack down with `docker compose -p amc31-qa -f ops/validation/compose.wave31.local.yml down -v`
  only when its volumes hold nothing you need.
