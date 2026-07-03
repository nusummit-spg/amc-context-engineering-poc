"""
PDF parser — handles SEBI Circulars/, SEBI Master Circulars/, and any other
unstructured PDF in the corpus. Always routed to the NER pipeline.
"""
from typing import List
import pdfplumber

from ingestion.parsers.base import BaseParser, ParsedSection


class PDFParser(BaseParser):
    supported_extensions = [".pdf"]

    def parse(self, filepath: str) -> List[ParsedSection]:
        sections = []
        with pdfplumber.open(filepath) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    sections.append(
                        ParsedSection(
                            heading=f"page_{i}",
                            text=text,
                            source_file=filepath,
                            route_hint="unstructured",
                            metadata={"page_number": i},
                        )
                    )
        return sections