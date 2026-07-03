"""Plain text parser — handles other sources.txt and any raw .txt notes."""
from typing import List

from ingestion.parsers.base import BaseParser, ParsedSection


class TextParser(BaseParser):
    supported_extensions = [".txt"]

    def parse(self, filepath: str) -> List[ParsedSection]:
        with open(filepath, "r", errors="ignore") as f:
            text = f.read()
        if not text.strip():
            return []
        return [
            ParsedSection(
                heading=filepath.split("/")[-1],
                text=text,
                source_file=filepath,
                route_hint="unstructured",
            )
        ]