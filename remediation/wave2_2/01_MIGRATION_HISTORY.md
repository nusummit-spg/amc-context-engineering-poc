# Migration History — Decision Record

## Finding (W22-01, W22-02)

Migrations 001, 002, 003 were absent from `backend/alembic/versions/` at the
pinned Wave 2.2 HEAD. Migration 004 declared:

    revision = '004_b03_verification'
    down_revision = '003_invitation_token_hash'

causing `alembic upgrade head` to fail immediately with:
    KeyError: '003_invitation_token_hash'

## Decision: RECONSTRUCT_REVIEWED_BASELINE

The original scripts existed in internal history before open-source publication.
Rather than adding an empty no-op bridge (which would leave the DB structurally
wrong), the migrations were reconstructed from the ORM model definitions at
Wave 2.2 HEAD.

## Reconstructed migrations

| Revision | Tables created |
|---|---|
| 001_base_schema | chat_sessions, audit_metadata, auth_users |
| 002_feedback_tables | response_feedback, unified_evaluation_records, query_evidence |
| 003_invitation_token_hash | invitation_tokens, graph_mutations, repair_proposals |

## Compatibility requirement

A maintainer MUST verify that the materialized schema in any existing deployment
matches these reconstructed migrations before running them in production.
Run `alembic current` on live DB and compare with `alembic history -v`.
