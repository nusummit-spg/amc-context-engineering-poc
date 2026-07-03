"""
Abstract base for every format parser. Every parser returns a list of
ParsedSection so ingestion/chunker.py can treat PDF/DOCX/PPTX/Excel/Email/Text
uniformly downstream.

route_hint tells ingestion/pipeline.py whether this section should go through
the expensive NER/LLM path or the cheap direct-ETL path (see pipeline.py).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ParsedSection:
    heading: str
    text: str
    source_file: str
    route_hint: str = "unstructured"  # "unstructured" -> NER pipeline | "structured" -> direct ETL
    structured_rows: List[Dict[str, Any]] = field(default_factory=list)  # populated only when route_hint == "structured"
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    supported_extensions: List[str] = []

    @abstractmethod
    def parse(self, filepath: str) -> List[ParsedSection]:
        ...

    def can_handle(self, filepath: str) -> bool:
        return any(filepath.lower().endswith(ext) for ext in self.supported_extensions)