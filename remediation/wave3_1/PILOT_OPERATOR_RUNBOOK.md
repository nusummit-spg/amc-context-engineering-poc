# AMC Wave 3.1 — Pilot Operator Runbook (WP08)

**Status: REHEARSED LOCALLY, NOT ACCEPTED.** The procedures below were exercised on one Windows development
machine against disposable local PostgreSQL 16.2, Neo4j 5.24.2 and FAISS (see
[LOCAL_VALIDATION_SUMMARY.md](LOCAL_VALIDATION_SUMMARY.md) and `backend/tests/live31/`). That is not a staging
rehearsal, not an SLO window and not an independent review. Every item in §1 is still open.

Use only disposable, localhost-bound services and synthetic data until the release owner says otherwise.
Never put a password, key or token in this file, in Git, in logs, or in a PR comment.

## 1. Open items that still block a real pilot

1. **Publication owner is unassigned** (scope decision Q4). Someone must be named to publish, revoke,
   recover and sign a corpus.
2. **Stranded claims are not auto-reconciled.** If a publication fails for good after it took the scope
   (for example the graph is changed by someone else, so every retry is refused), serving stays denied and the
   claim stays HELD. `status` reports it and says operator review is required; there is deliberately no
   force-release command. The review procedure itself is not written.
3. **Readiness is not defined.** `/health` and `/api/health` report liveness only; they do not show whether a
   tenant can be served. Do not treat a 200 as "ready".
4. **SLO thresholds are undefined** (Q5) and no staging environment is confirmed (Q6). The measured numbers in the
   validation summary describe one machine with a stubbed LLM.
5. **The index generation is digest-bound, not signed.** SHA-256 over the manifest, payload map and index bytes is
   bound to the PostgreSQL receipt. There is no asymmetric signature on the index itself.

## 2. Configuration to freeze before a pilot run

| Setting | Required value | Notes |
|---|---|---|
| `AMC_VERIFIED_SERVING_MODE` | `enforce` | Never switch to `off` to make a failing check pass |
| `QUERY_ENGINE` | `v2` | `legacy`, `canary` and `shadow` are refused in enforce mode |
| `DATABASE_URL` | `postgresql+psycopg://…` | Must be the same database Alembic migrated |
| `AMC_MIGRATION_DATABASE_URL` | identical to `DATABASE_URL` | Compare with SQLAlchemy `make_url`; print masked values only |
| `AMC_VERIFIED_FAISS_ROOT` | path to the generation root | Required; serving is denied without it |
| `AUTH_SECRET_KEY` | long random value | Never the development default |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | the disposable instance | Local test password only |
| `AMC_PUBLICATION_GRAPH_ATTRIBUTES` | explicit comma list, e.g. `ter,exit_load` | The operator CLI's graph allowlist |
| `AMC_PUBLICATION_EMBEDDER` | `package.module:factory` | Must be the SAME embedder the app queries with |
| `VITE_AMC_PILOT_MODE` | `true` at frontend build time | Hides denied features, refuses denied calls, shows citations as provenance |

Record the application commit SHA, flag values and migration revision with the run, without credentials.

## 3. Start sequence

1. **Providers (no Docker):** `ops/validation/local_services31.ps1 -Action Start` starts an embedded PostgreSQL and a
   portable Neo4j on `127.0.0.1` (setup notes and a Windows Java workaround are in that script). The Docker Compose
   file `ops/validation/compose.wave31.local.yml` is only an alternative for machines that have Docker.
2. **Migrate:** from `backend/` run `python scripts/alembic_dag_preflight.py`, then
   `python -m alembic -c alembic.ini upgrade head` and `… current`. The revision must be
   `015_app_schema_alignment_v31` (014 alone leaves chat and token revocation without their tables and columns).
   Never downgrade a database that is not disposable.
3. **Publish (operator, offline):**
   `python -m amc_publication.operator_cli submit --tenant T --entity E --attribute A --value V --corpus corpus.json
   --proposal-id P --revision 1 --proposer <person> --reviewer <different person> --attest-independent-approval`
   then `python -m amc_publication.operator_cli run-once`. Confirm with
   `python -m amc_publication.operator_cli status --tenant T`: authority ACTIVE and no "attention" lines. The CLI
   refuses a non-PostgreSQL URL, a database that is not at the exact revision, a missing attestation, identical
   proposer and reviewer, and any corpus row whose tenant differs. Do not edit SQL rows by hand.
4. **Start the app** in enforce mode, then smoke-test as an authenticated tenant user (not just `/health`).

Startup in enforce mode refuses to run unless the engine is PostgreSQL at exactly revision 015, creates no
schema or rows, writes nothing to the graph, and starts no scheduler, ingest queue, FAISS or cache warm-up, or
feedback worker. It also refuses an invalid mode or a SQLite URL.

## 4. Rollback and recovery (rehearsed locally)

- **Separate three things:** runtime serving rollback, Git revert, and database downgrade. Only the first is a rollback
  procedure. A schema downgrade is not.
- **Serving rollback:** `operator_cli rollback --tenant T --work-id W` suspends serving at once (queries are denied),
  then `operator_cli run-once` restores the previous graph value and generation and re-activates it. Rolling back
  the FIRST publication returns the tenant to the fail-closed state (no authority), never a guessed one. The running
  app needs no restart in either direction.
- **Crash recovery:** a worker that dies at any of the six durable boundaries is recovered by running `run-once` again
  after its lease expires, with no duplicated effects or receipts. A killed app process leaves publication state
  untouched.
- **Outages:** with PostgreSQL down a request is refused in about 3 s (it took 130 s before the connect timeout fix) and
  the app recovers without a restart; with Neo4j down nothing stale or foreign is served, and a publication that
  cannot reach the graph fails before it suspends serving and completes after the graph returns.
- **Backup/restore:** a `pg_dump` restored into a new database serves the same state with the existing index.
- **If restoration cannot be proven,** serving stays denied and the case goes to operator review (§1, item 2).
- **Mid-stream revocation:** content already sent before a rollback cannot be retracted. The guarantee is that no further
  stale content is delivered; in the rehearsal the answer was withheld entirely.

## 5. What to check, and what to never conclude

| Question | Evidence that answers it | Not evidence |
|---|---|---|
| Can a tenant be served? | An authenticated query returns a cited answer and the PG receipt, graph and FAISS agree | `/health` returning 200 |
| Is isolation intact? | `tenant_beta` cannot see `tenant_alpha` content, graph edges or citations, including in the LLM prompts | A passing mocked test |
| Did rollback work? | Generation A answers again, generation B is absent, the receipt epoch moved forward | A status field alone |
| Are logs clean? | A scan finds no credentials, tokens or document bodies (the live suite does this) | The absence of an obvious error |

## 6. Hygiene

- Keep raw logs, JUnit files and screenshots in a directory outside the checkout; commit only a sanitized summary.
- Do not commit binary indexes, corpora, signing keys or connection strings.
- Do not run the repository-root `docker-compose.yml`; it carries demo and cloud logging settings.
- `ops/validation/local_services31.ps1 -Action Stop` shuts the local stack down; delete its data folder only when it
  holds nothing you need.
