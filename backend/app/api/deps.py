"""WS3 — Dependency injection: wires the whole stack once at startup and
exposes FastAPI dependencies."""
import json
from pathlib import Path

from backend.app.config import get_settings
from backend.app.core.llm import get_llm_client
from backend.app.extraction.classifier import TaxonomyClassifier
from backend.app.extraction.entities import EntityExtractor
from backend.app.extraction.relationships import RelationshipExtractor
from backend.app.extraction.resolver import EntityResolver
from backend.app.graph.client import get_graph_client
from backend.app.ingestion.pipeline import IngestionPipeline
from backend.app.retrieval.context import ContextAssembler
from backend.app.retrieval.intent import IntentClassifier
from backend.app.retrieval.orchestrator import RetrievalOrchestrator
from backend.app.retrieval.synthesizer import Synthesizer
from backend.app.retrieval.traversal import GraphTraversal
from backend.app.schemas.taxonomy import TaxonomyNode, TaxonomyTree

SEEDS_DIR = Path(__file__).resolve().parents[2] / "seeds"
ALIAS_SEED_PATH = SEEDS_DIR / "entity_aliases.json"
TAXONOMY_SEED_PATH = SEEDS_DIR / "taxonomy.json"


def load_taxonomy() -> TaxonomyTree:
    """Builds the TaxonomyTree from the WS5b seed JSON (nested dict / leaf lists)."""
    data = json.loads(TAXONOMY_SEED_PATH.read_text(encoding="utf-8"))

    def build(name: str, subtree, parent_path: str, level: int) -> TaxonomyNode:
        path = f"{parent_path}/{name}" if parent_path else name
        node = TaxonomyNode(
            node_id=path.replace("/", "::").lower().replace(" ", "-"),
            name=name, path=path, level=level,
            parent_path=parent_path or None,
        )
        if isinstance(subtree, dict):
            node.children = [build(k, v, path, level + 1) for k, v in subtree.items()]
        elif isinstance(subtree, list):
            node.children = [build(leaf, None, path, level + 1) for leaf in subtree]
        return node

    roots = [build(k, v, "", 1) for k, v in data["tree"].items()]
    return TaxonomyTree(version=data.get("version", "1.0"),
                        domain=data.get("domain", "AMC"), roots=roots)


class Container:
    """Singleton service container, built once in the lifespan handler."""

    def __init__(self) -> None:
        from backend.app.vector.client import get_vector_store

        self.settings = get_settings()
        self.taxonomy = load_taxonomy()
        self.llm = get_llm_client()
        self.graph = get_graph_client()
        self.vector = get_vector_store()

        self.resolver = EntityResolver(self.llm, ALIAS_SEED_PATH)
        self.classifier = TaxonomyClassifier(self.llm, self.taxonomy)
        self.entity_extractor = EntityExtractor(self.llm)
        self.relationship_extractor = RelationshipExtractor(self.llm)

        self.pipeline = IngestionPipeline(
            vector_store=self.vector,
            graph_client=self.graph,
            classifier=self.classifier,
            entity_extractor=self.entity_extractor,
            resolver=self.resolver,
            relationship_extractor=self.relationship_extractor,
            alias_seed_path=ALIAS_SEED_PATH,
        )

        self.orchestrator = RetrievalOrchestrator(
            intent_classifier=IntentClassifier(self.llm, self.taxonomy),
            resolver=self.resolver,
            traversal=GraphTraversal(self.graph),
            vector_store=self.vector,
            assembler=ContextAssembler(),
            synthesizer=Synthesizer(self.llm),
        )


_container: Container | None = None


def init_container() -> Container:
    global _container
    if _container is None:
        _container = Container()
    return _container


def get_container() -> Container:
    if _container is None:
        raise RuntimeError("Container not initialized — app startup did not run")
    return _container
