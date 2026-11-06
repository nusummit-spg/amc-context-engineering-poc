# Wave 1.7 Schema Migration Evidence

**Date:** 6 November 2026  
**Migration IDs:** 009_b06, 010_b07

## Migration 009_b06 (P01 - Wave 1.6)

**Purpose:** Publication intents and receipts for durable publication tracking

**Tables created:**
- `publication_intents` - Intent tracking with status lifecycle
- `publication_receipts` - Immutable effect evidence

**Constraints:**
- Primary keys: `intent_id`, `receipt_id`
- Check constraints: status types, publication types
- Indexes: proposal/revision, status/created, tenant/entity

**Schema:**

```sql
publication_intents (
  intent_id VARCHAR(64) PK,
  proposal_id VARCHAR(64),
  approved_revision INT,
  tenant VARCHAR(128),
  target_entity VARCHAR(128),
  source_version VARCHAR(64),
  publication_type VARCHAR(20) CHECK(...),
  payload JSON,
  status VARCHAR(20) CHECK(...),
  created_at VARCHAR(40),
  approved_at VARCHAR(40),
  publishing_at VARCHAR(40),
  published_at VARCHAR(40),
  failed_at VARCHAR(40),
  retry_count INT,
  max_retries INT,
  error TEXT
)

publication_receipts (
  receipt_id VARCHAR(64) PK,
  intent_id VARCHAR(64),
  preimage JSON,
  postimage JSON,
  verified_at VARCHAR(40),
  verification_method VARCHAR(64),
  source_hash VARCHAR(128),
  source_version VARCHAR(64),
  tenant VARCHAR(128),
  signature VARCHAR(256),
  created_at VARCHAR(40)
)
```

## Migration 010_b07 (B01 - Wave 1.7)

**Purpose:** Durable graph/vector effects with preimage/postimage hashes

**Table created:**
- `publication_effects` - Per-effect tracking with CAS fencing

**Constraints:**
- Primary key: `effect_id`
- Check constraints: effect_kind, result_status
- Indexes: intent, kind/target, tenant/status, created

**Schema:**

```sql
publication_effects (
  effect_id VARCHAR(64) PK,
  intent_id VARCHAR(64),
  effect_kind VARCHAR(32) CHECK(...),
  effect_target VARCHAR(128),
  effect_revision INT,
  preimage_hash VARCHAR(64),
  preimage_snapshot JSON,
  postimage_hash VARCHAR(64),
  postimage_snapshot JSON,
  applied_at VARCHAR(40),
  observed_at VARCHAR(40),
  verified BOOLEAN,
  result_status VARCHAR(20) CHECK(...),
  error TEXT,
  tenant VARCHAR(128),
  fencing_token VARCHAR(64),
  source_version VARCHAR(64),
  created_at VARCHAR(40)
)
```

## Migration Verification

**Verified:**
- Migration syntax: PASS (python -m py_compile verified)
- Tables defined: PASS
- Constraints defined: PASS
- Indexes defined: PASS

**Not Verified:**
- Upgrade on actual DB: BLOCKED (no disposable DB available)
- Downgrade: BLOCKED (no disposable DB available)
- Data preservation: BLOCKED (no data to test)
- Schema contract: BLOCKED (no disposable DB)

## Next Steps

1. Create disposable PostgreSQL instance
2. Run `alembic upgrade head`
3. Verify tables exist with `SELECT * FROM information_schema.tables`
4. Run `alembic downgrade base`
5. Run `alembic upgrade head` again
6. Verify no data loss
7. Execute upgrade/downgrade on real DB with production-like data volume
