# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Domain Pack loader — swappable ontology for multi-domain support.

Adapted from Agentic Testing Platform's domain pack pattern.
Allows switching between AMC, insurance, banking, and other domains
without code changes — just set DOMAIN_PACK_PATH in .env.

Domain pack YAML format:
  domain: AMC
  version: "1.0"
  concepts:
    - canonical: "nav"
      type: "financial_metric"
      aliases: ["net asset value", "nav per unit"]
  relations:
    - source: "scheme"
      relation: "HOLDS"
      target: "issuer"
  seed_entities:
    - canonical_name: "HDFC Flexi Cap Fund"
      entity_type: "Scheme"
      aliases: ["HDFC Flexi Cap", "HDFC FCF"]
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ingestion.domain_pack")


@dataclass
class DomainConcept:
    """A canonical domain concept with aliases and type."""
    canonical: str
    concept_type: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class DomainRelation:
    """A schema-level relation between two canonical concepts."""
    source: str
    relation: str
    target: str


@dataclass
class SeedEntity:
    """A known entity pre-populated into the resolver."""
    canonical_name: str
    entity_type: str
    aliases: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class DomainPack:
    """A loaded domain ontology pack."""
    domain: str
    version: str
    concepts: list[DomainConcept] = field(default_factory=list)
    relations: list[DomainRelation] = field(default_factory=list)
    seed_entities: list[SeedEntity] = field(default_factory=list)

    @property
    def concept_dict(self) -> dict[str, dict[str, Any]]:
        """Return concepts as a dict compatible with extract_facts() AMC_CONCEPTS format."""
        return {
            c.canonical: {"type": c.concept_type, "aliases": c.aliases}
            for c in self.concepts
        }

    @property
    def alias_seed_data(self) -> dict:
        """Return seed entities in the format expected by EntityResolver._load_seed()."""
        return {
            "entities": [
                {
                    "canonical_name": e.canonical_name,
                    "entity_type": e.entity_type,
                    "aliases": e.aliases,
                    **e.properties,
                }
                for e in self.seed_entities
            ]
        }


def load_domain_pack(path: Optional[str | Path] = None) -> DomainPack:
    """Load a domain pack from a YAML file.
    
    Resolution order:
      1. Explicit `path` argument
      2. DOMAIN_PACK_PATH environment variable
      3. Default: <project_root>/backend/seeds/amc_domain_pack.yaml
    
    Falls back gracefully to an empty DomainPack if no YAML is found.
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed. Domain pack loading disabled. pip install pyyaml")
        return DomainPack(domain="AMC", version="0.0")

    # Resolve path
    if path is None:
        env_path = os.environ.get("DOMAIN_PACK_PATH")
        if env_path:
            path = Path(env_path)
        else:
            # Default path relative to this file
            path = Path(__file__).parent.parent.parent / "seeds" / "amc_domain_pack.yaml"

    path = Path(path)
    if not path.exists():
        logger.warning("Domain pack not found at %s. Using empty pack.", path)
        return DomainPack(domain="AMC", version="0.0")

    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    domain  = data.get("domain", "AMC")
    version = str(data.get("version", "1.0"))

    concepts = [
        DomainConcept(
            canonical=c["canonical"],
            concept_type=c.get("type", "concept"),
            aliases=c.get("aliases", []),
        )
        for c in data.get("concepts", [])
    ]

    relations = [
        DomainRelation(
            source=r["source"],
            relation=r["relation"],
            target=r["target"],
        )
        for r in data.get("relations", [])
    ]

    seed_entities = [
        SeedEntity(
            canonical_name=e["canonical_name"],
            entity_type=e["entity_type"],
            aliases=e.get("aliases", []),
            properties={k: v for k, v in e.items()
                        if k not in {"canonical_name", "entity_type", "aliases"}},
        )
        for e in data.get("seed_entities", [])
    ]

    logger.info("Loaded domain pack: domain=%s version=%s concepts=%d seed_entities=%d",
                domain, version, len(concepts), len(seed_entities))

    return DomainPack(
        domain=domain,
        version=version,
        concepts=concepts,
        relations=relations,
        seed_entities=seed_entities,
    )
