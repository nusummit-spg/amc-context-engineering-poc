"""
DOCX parser — handles the narrative commentary docs, e.g.
Average AUM/Fundwise/April - June 2026.docx. Splits on heading styles so
chunking stays section-aware. Always routed to the NER pipeline (the
companion .xlsx for the same period is structured data — see excel.py).
"""
from typing import List
import docx

from ingestion.parsers.base import BaseParser, ParsedSection


class DOCXParser(BaseParser):
    supported_extensions = [".docx"]

    def parse(self, filepath: str) -> List[ParsedSection]:
        document = docx.Document(filepath)
        sections: List[ParsedSection] = []
        current_heading = "Document Start"
        current_text: List[str] = []

        def flush():
            if current_text:
                sections.append(
                    ParsedSection(
                        heading=current_heading,
                        text="\n".join(current_text).strip(),
                        source_file=filepath,
                        route_hint="unstructured",
                    )
                )

        for para in document.paragraphs:
            style = (para.style.name or "").lower()
            if style.startswith("heading") or style == "title":
                flush()
                current_heading = para.text.strip() or current_heading
                current_text = []
            elif para.text.strip():
                current_text.append(para.text.strip())

        flush()
        return [s for s in sections if s.text]