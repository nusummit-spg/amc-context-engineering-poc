"""WS2 — Markdown + plain text readers. Markdown splits on headings."""
import re
from pathlib import Path

from app.ingestion.parsers.base import BaseParser
from app.schemas.documents import Document, DocumentType, Section

_MD_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$", re.MULTILINE)


class MarkdownParser(BaseParser):
    extensions = (".md", ".markdown")

    def parse(self, path: Path) -> Document:
        text = path.read_text(encoding="utf-8", errors="replace")
        sections: list[Section] = []
        matches = list(_MD_HEADING_RE.finditer(text))

        if not matches:
            sections.append(Section(text=text.strip(), order=0))
        else:
            preamble = text[: matches[0].start()].strip()
            if preamble:
                sections.append(Section(text=preamble, order=0))
            for i, m in enumerate(matches):
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                body = text[m.end():end].strip()
                sections.append(Section(
                    title=m.group(2).strip(),
                    level=len(m.group(1)),
                    text=body,
                    order=len(sections),
                ))

        return Document(
            filename=path.name,
            doc_type=DocumentType.MARKDOWN,
            title=path.stem.replace("_", " "),
            source_path=str(path),
            sections=[s for s in sections if s.text] or [Section(text="", order=0)],
        )


class PlainTextParser(BaseParser):
    extensions = (".txt",)

    def parse(self, path: Path) -> Document:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Split on blank-line paragraphs, group into modest sections.
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        sections = [
            Section(text=p, order=i) for i, p in enumerate(paragraphs)
        ] or [Section(text="", order=0)]
        return Document(
            filename=path.name,
            doc_type=DocumentType.TEXT,
            title=path.stem.replace("_", " "),
            source_path=str(path),
            sections=sections,
        )
