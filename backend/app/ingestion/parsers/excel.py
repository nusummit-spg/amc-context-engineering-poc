"""WS2 — Excel parser (openpyxl): table rows -> structured text, one section per sheet."""
from pathlib import Path

import openpyxl

from app.ingestion.parsers.base import BaseParser
from app.schemas.documents import Document, DocumentType, Section


class ExcelParser(BaseParser):
    extensions = (".xlsx", ".xlsm")

    def parse(self, path: Path) -> Document:
        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        sections: list[Section] = []

        for order, ws in enumerate(wb.worksheets):
            rows = [
                [("" if c is None else str(c)) for c in row]
                for row in ws.iter_rows(values_only=True)
                if any(c is not None for c in row)
            ]
            if not rows:
                continue
            headers = rows[0]
            lines = [" | ".join(headers)]
            # Render each data row as "Header: value" pairs so entity/relationship
            # extraction sees column semantics, not just positional cells.
            for row in rows[1:]:
                pairs = [f"{h}: {v}" for h, v in zip(headers, row) if v]
                lines.append("; ".join(pairs))
            sections.append(Section(
                title=ws.title, text="\n".join(lines), order=order,
                metadata={"sheet": ws.title, "row_count": len(rows)},
            ))
        wb.close()

        return Document(
            filename=path.name,
            doc_type=DocumentType.EXCEL,
            title=path.stem.replace("_", " "),
            source_path=str(path),
            sections=sections or [Section(text="", order=0)],
        )
