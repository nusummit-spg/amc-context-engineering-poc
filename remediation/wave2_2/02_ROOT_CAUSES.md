# Root Cause Analysis — Wave 2.2

## W22-01: Missing Alembic ancestor (P0)
Root cause: 001-003 migration scripts absent from public repo.
Fix: Reconstructed from ORM models. See 01_MIGRATION_HISTORY.md.

## W22-05: feedback_loop top-level import crashes app (P0)
Root cause: `app/services/feedback.py` imported from `feedback_loop` at module
level. Package absent in CI and clean checkouts.
Fix: Guarded with try/except; returns None / 503 when evaluator absent.

## W22-10: Graph readback uses intended postimage not actual read (P0)
Root cause: `worker.py::_process_publication` passed `postimage` (the
intended value) directly to `journal.verified` without calling `graph.read()`.
Fix: Call `graph.read()` after CAS; compare actual vs intended; fail if mismatch.

## W22-11: Rollback deletes pointer instead of restoring prior generation (P0)
Root cause: `switch_back` always deleted the GenerationPointer row.
`_process_rollback` passed the CURRENT pointer as `before`, not the vector
effect preimage (which holds the generation that existed before this publication).
Fix: Read vector effect preimage for `before`; CAS-restore prior generation
in `switch_back`; only delete when no prior generation existed.

## W22-12: DurableWorker.execute_work fakes published status (P0)
Root cause: `DurableWorker.execute_work` set work status to 'published' using
stub placeholder hashes without any external effects (no Neo4j, no FAISS).
Fix: Raise RuntimeError in execute_work; route all publication through
Journal + PublicationWorker.

## W22-03: A02 CI uses SQLite despite provisioning PostgreSQL service (P0)
Root cause: A02 job set `DATABASE_URL=sqlite:///./data.db` and rewrote
alembic.ini with sed — the postgres service in the job was never used.
Fix: Set `AMC_MIGRATION_DATABASE_URL` to the postgres service URL; env.py
reads env var and rejects SQLite in CI.
