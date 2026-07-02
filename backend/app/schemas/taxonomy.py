"""WS5a — Taxonomy node + tree schema (4-level AMC domain taxonomy)."""
from typing import Optional

from pydantic import BaseModel, Field


class TaxonomyNode(BaseModel):
    """One node in the taxonomy tree. `path` is slash-joined from root, e.g.
    'Risk/Concentration Exposure/Issuer Group'."""
    node_id: str
    name: str
    path: str
    level: int  # 1..4
    parent_path: Optional[str] = None
    description: Optional[str] = None
    document_count: int = 0
    children: list["TaxonomyNode"] = Field(default_factory=list)


class TaxonomyTree(BaseModel):
    version: str = "1.0"
    domain: str = "AMC"
    roots: list[TaxonomyNode] = Field(default_factory=list)

    def flatten(self) -> list[TaxonomyNode]:
        out: list[TaxonomyNode] = []

        def walk(node: TaxonomyNode) -> None:
            out.append(node)
            for child in node.children:
                walk(child)

        for root in self.roots:
            walk(root)
        return out

    def find(self, path: str) -> Optional[TaxonomyNode]:
        for node in self.flatten():
            if node.path == path:
                return node
        return None


TaxonomyNode.model_rebuild()
