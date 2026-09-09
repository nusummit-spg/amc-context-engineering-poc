# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import re
from pathlib import Path
try:
    import pymupdf as fitz  # pymupdf
except ImportError:
    import fitz

from app.ingestion.parsers.base import BaseParser
from app.schemas.documents import Document, DocumentType, Section

# Lines that look like section headings in scheme documents / circulars,
# e.g. "--- Section 4.2: Portfolio Holdings ---", "SECTION 9: EXIT LOAD", "4.2 Portfolio Holdings"
_HEADING_RE = re.compile(
    r"^\s*(-{2,}\s*)?(section\s+[\d.]+|[A-Z][A-Z \d.:&\-]{6,})\s*(-{2,})?\s*$",
    re.IGNORECASE,
)


class PdfParser(BaseParser):
    extensions = (".pdf",)

    def parse(self, path: Path) -> Document:
        doc = fitz.open(path)
        sections: list[Section] = []
        current_title: str | None = None
        current_lines: list[str] = []
        current_page = 1
        order = 0

        def flush():
            nonlocal order
            text = "\n".join(current_lines).strip()
            if text:
                sections.append(Section(
                    title=current_title, text=text, order=order,
                    metadata={"page": current_page},
                ))
                order += 1

        for page_index, page in enumerate(doc, start=1):
            # Tables → pipe-delimited rows so downstream chunking keeps them intact.
            table_text: list[str] = []
            try:
                for table in page.find_tables():
                    rows = table.extract()
                    for row in rows:
                        table_text.append(" | ".join(str(c or "") for c in row))
            except Exception:
                pass

            for line in page.get_text("text").splitlines():
                if _HEADING_RE.match(line) and len(line.strip()) < 90:
                    flush()
                    current_title = line.strip().strip("-").strip()
                    current_lines = []
                    current_page = page_index
                else:
                    current_lines.append(line)
            if table_text:
                current_lines.append("\n[TABLE]\n" + "\n".join(table_text))
        flush()
        page_count = doc.page_count
        doc.close()

        return Document(
            filename=path.name,
            doc_type=DocumentType.PDF,
            title=path.stem.replace("_", " "),
            source_path=str(path),
            sections=sections or [Section(text="", order=0)],
            metadata={"page_count": page_count},
        )
