"""WS5a — Taxonomy node + tree schema (4-level AMC domain taxonomy).

Path convention: slash-separated from root.
  Level 1:  "Risk"
  Level 2:  "Risk/Concentration Exposure"
  Level 3:  "Risk/Concentration Exposure/Issuer Group"
  Level 4:  "Risk/Concentration Exposure/Issuer Group/Monitoring"

Unified with WS5a extended design:
  - TaxonomyNode gains 3 structural validators (depth/level parity,
    parent_path consistency, Level-1 root enforcement)
  - TaxonomyTree gains a build_from_seed() classmethod that understands
    the nested-dict seed JSON format (seeds/taxonomy.json)
  - TaxonomyTag and TaxonomyClassificationResult added for the
    ingestion taxonomy-classification step output
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class TaxonomyNode(BaseModel):
    """One node in the taxonomy tree.

    `path` is slash-joined from root, e.g.:
      'Risk/Concentration Exposure/Issuer Group'

    Structural invariants (enforced by validators):
      1. path segment count must equal level
      2. parent_path must equal path up to last '/' segment
      3. Level-1 roots must have no parent_path
    """
    node_id:        str           = Field(description="Unique node key, e.g. 'risk::concentration-exposure'")
    name:           str           = Field(min_length=1)
    path:           str           = Field(description="Slash-joined full path from root")
    level:          int           = Field(ge=1, le=4)
    parent_path:    Optional[str] = None
    description:    Optional[str] = None
    document_count: int           = Field(default=0, ge=0)
    children:       list["TaxonomyNode"] = Field(default_factory=list)

    # ── Structural validators ─────────────────────────────────────────────

    @model_validator(mode="after")
    def path_segment_count_matches_level(self) -> "TaxonomyNode":
        """path.split('/') segment count must equal level.
        Level 1 nodes: single-segment path (no '/' present).
        Level 2–4: exactly `level` slash-separated segments.
        """
        segments = self.path.split("/")
        if len(segments) != self.level:
            raise ValueError(
                f"path '{self.path}' has {len(segments)} segment(s) "
                f"but level is {self.level}. "
                "path segment count must equal level."
            )
        return self

    @model_validator(mode="after")
    def level1_must_have_no_parent(self) -> "TaxonomyNode":
        """Root nodes (level=1) must not have a parent_path."""
        if self.level == 1 and self.parent_path is not None:
            raise ValueError(
                f"Level-1 node '{self.node_id}' must have parent_path=None "
                f"(got '{self.parent_path}'). Only root nodes exist at level 1."
            )
        return self

    @model_validator(mode="after")
    def parent_path_consistent_with_path(self) -> "TaxonomyNode":
        """For level 2+ nodes, parent_path must equal path minus the last segment."""
        if self.level > 1:
            expected_parent = "/".join(self.path.split("/")[:-1])
            if self.parent_path != expected_parent:
                raise ValueError(
                    f"parent_path '{self.parent_path}' is inconsistent with "
                    f"path '{self.path}'. Expected parent_path='{expected_parent}'."
                )
        return self

    # ── Utility properties ────────────────────────────────────────────────

    @property
    def is_leaf(self) -> bool:
        """True if this node has no children or is at the maximum depth (level 4)."""
        return self.level == 4 or len(self.children) == 0

    def derive_parent_path(self) -> str | None:
        """Compute the expected parent_path from this node's path."""
        parts = self.path.rsplit("/", 1)
        return parts[0] if len(parts) > 1 else None


class TaxonomyTag(BaseModel):
    """A single taxonomy classification tag assigned to a document or chunk."""
    node_id:    str
    path:       str   = Field(description="Slash-joined path, e.g. 'Risk/Concentration Exposure'")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class TaxonomyClassificationResult(BaseModel):
    """Output of the taxonomy classification step (ingestion pipeline).
    Tags are sorted by confidence descending on construction.
    """
    document_id: str
    tags:        list[TaxonomyTag] = Field(default_factory=list)
    model_used:  Optional[str]     = None

    @model_validator(mode="after")
    def sort_tags_by_confidence(self) -> "TaxonomyClassificationResult":
        self.tags = sorted(self.tags, key=lambda t: t.confidence, reverse=True)
        return self


class TaxonomyTree(BaseModel):
    version: str              = "1.0"
    domain:  str              = "AMC"
    roots:   list[TaxonomyNode] = Field(default_factory=list)

    def flatten(self) -> list[TaxonomyNode]:
        """Returns all nodes in pre-order (root first, then children recursively)."""
        out: list[TaxonomyNode] = []

        def walk(node: TaxonomyNode) -> None:
            out.append(node)
            for child in node.children:
                walk(child)

        for root in self.roots:
            walk(root)
        return out

    def find(self, path: str) -> Optional[TaxonomyNode]:
        """Find a node by its slash-joined path."""
        for node in self.flatten():
            if node.path == path:
                return node
        return None

    def valid_paths(self) -> list[str]:
        """Sorted list of all node paths — used by IntentClassifier for validation."""
        return sorted(n.path for n in self.flatten())

    @classmethod
    def build_from_seed(cls, data: dict, version: str = "1.0", domain: str = "AMC") -> "TaxonomyTree":
        """Build a TaxonomyTree from the nested-dict seed format (seeds/taxonomy.json).

        Seed format:
          {
            "tree": {
              "Risk": {
                "Concentration Exposure": {
                  "Issuer Group": ["Monitoring", "Limits"]
                }
              }
            }
          }
        Leaf lists produce level-4 nodes; nested dicts produce intermediate nodes.
        """
        def build(name: str, subtree, parent_path: str, level: int) -> TaxonomyNode:
            path = f"{parent_path}/{name}" if parent_path else name
            node = TaxonomyNode(
                node_id=path.replace("/", "::").lower().replace(" ", "-"),
                name=name,
                path=path,
                level=level,
                parent_path=parent_path if parent_path else None,
            )
            if isinstance(subtree, dict):
                node.children = [build(k, v, path, level + 1) for k, v in subtree.items()]
            elif isinstance(subtree, list):
                node.children = [build(leaf, None, path, level + 1) for leaf in subtree]
            return node

        roots = [build(k, v, "", 1) for k, v in data["tree"].items()]
        return cls(version=version, domain=domain, roots=roots)


TaxonomyNode.model_rebuild()
