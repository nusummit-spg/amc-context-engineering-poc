# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

# AMC Compliance Graph Schema

## Nodes

### `:Regulation`
- `id` (UNIQUE, e.g. `SEBI_MF_2024_Q1_001`)
- `title` (String)
- `region` (SEBI | SEC | ESMA)
- `effective_date` (ISO Date String)
- `document_url` (URL String)
- `raw_text` (String)
- `created_at` (ISO Timestamp)

### `:Rule`
- `id` (UNIQUE, e.g. `RULE_PORT_CONC_001`)
- `rule_type` (portfolio | governance | kyc | risk | reporting)
- `title` (String)
- `description` (String)
- `regulation_id` (Foreign Key -> Regulation.id)
- `condition` (DSL String, e.g. `holdings.max_single_holding > 0.15`)
- `severity` (critical | high | medium | low)
- `confidence_threshold` (Float 0.0 - 1.0)
- `applicability` (List[String], e.g. `["equity_fund", "balanced_fund"]`)
- `exclusions` (List[String], e.g. `["sector_fund"]`)
- `enforcement_level` (automatic | audit | escalation)
- `active` (Boolean)
- `created_at` (ISO Timestamp)

### `:FundScheme`
- `id` (UNIQUE, e.g. `Adani_Growth_2024`)
- `isin` (String, e.g. `INF204K01ND0`)
- `name` (String)
- `fund_house` (String)
- `category` (equity_fund | debt_fund | balanced_fund | sector_fund)
- `mandate` (String)
- `risk_profile` (String)
- `aum_cr` (Float)
- `region` (SEBI | SEC | ESMA)
- `created_at` (ISO Timestamp)

### `:Violation`
- `id` (UNIQUE, e.g. `V_20240115_103000_RULE_PORT_CONC_001`)
- `rule_id` (Foreign Key -> Rule.id)
- `fund_id` (Foreign Key -> FundScheme.id)
- `severity` (critical | high | medium | low)
- `confidence` (Float 0.0 - 1.0)
- `actual_value` (String / Number)
- `threshold_value` (String / Number)
- `description` (String)
- `detected_at` (ISO Timestamp)
- `region` (SEBI | SEC | ESMA)
- `status` (detected | reviewed | remediated | closed)
- `resolved_at` (Nullable ISO Timestamp)
- `resolution_action` (Nullable String)

### `:RiskThreshold`
- `id` (UNIQUE)
- `violation_type` (String)
- `confidence_min` (Float)
- `confidence_max` (Float)
- `escalation_priority` (String)
- `sla_minutes` (Integer)

### `:EscalationPath`
- `id` (UNIQUE)
- `region` (SEBI | SEC | ESMA)
- `severity` (critical | high | medium | low)
- `routing_rules` (List[String])
- `notification_channels` (List[String])
- `sla_hours` (Integer)
- `requires_board_approval` (Boolean)

## Relationships

```
(:Regulation) <--[:basedOn]-- (:Rule)
(:FundScheme) --[:governedBy]-> (:Rule)
(:Violation) --[:violates]-> (:Rule)
(:Violation) --[:affects]-> (:FundScheme)
(:Violation) --[:escalatesVia]-> (:EscalationPath)
```
