# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================
"""Document ingestion and processing module for pdf."""


import logging
import re
from pathlib import Path
try:
    import pymupdf as fitz  # pymupdf
except ImportError:
    import fitz

from app.ingestion.parsers.base import BaseParser
from app.models.documents import Document, DocumentType, Section

logger = logging.getLogger(__name__)

def _is_heading(line: str) -> bool:
    """Check whether heading.

    Args:
        line (str): The line.

    Returns:
        bool: True if condition is met or operation succeeded, False otherwise.
    """
    s = line.strip().strip("-").strip()
    if not s or len(s) > 90 or len(s) < 3:
        return False
    # Explicit Section/Part/Clause/Chapter headings: e.g. "Section 4", "SECTION 1.2: OBJECTIVE"
    if re.match(r"^(section|part|clause|chapter)\s+[\d.A-Za-z]+", s, re.IGNORECASE):
        return True
    # Numbered headings: e.g. "1.2 Investment Policy", "3.1.4 Risk Factors"
    if re.match(r"^\d+(\.\d+)+\s+[A-Z]", s):
        return True
    # Markdown-style headings: "# Introduction", "## Holdings"
    if line.strip().startswith("#"):
        return True
    # Explicit banner headings: "--- Portfolio Holdings ---"
    if re.match(r"^-{2,}.*-{2,}$", line.strip()):
        return True
    # All-uppercase headings with at least 2 words and all uppercase letters: e.g. "PORTFOLIO HOLDINGS", "EXIT LOAD DETAILS"
    words = [w for w in s.split() if any(c.isalpha() for c in w)]
    if len(words) >= 2 and all(w.isupper() for w in words):
        return True
    return False


class PdfParser(BaseParser):
    extensions = (".pdf",)

    def parse(self, path: Path) -> Document:
        """Parse operation.

        Args:
            path (Path): Filesystem path or resource path.

        Returns:
            Document: Resulting Document instance.
        """
        doc = fitz.open(path)
        try:
            sections: list[Section] = []
            current_title: str | None = None
            current_lines: list[str] = []
            current_page = 1
            order = 0

            def flush():
                """Flush.
                """
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
                    if _is_heading(line):
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
            
            return Document(
                filename=path.name,
                doc_type=DocumentType.PDF,
                title=path.stem.replace("_", " "),
                source_path=str(path),
                sections=sections or [Section(text="", order=0)],
                metadata={"page_count": page_count},
            )
        finally:
            # ALWAYS close, even on exception
            try:
                doc.close()
            except Exception as close_exc:
                logger.warning("Error closing PDF %s: %s", path.name, close_exc)

