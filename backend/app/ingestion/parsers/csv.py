# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""WS2 — CSV parser: parses structured CSV files into unified Document schema with dataset overview and row sections."""
import csv
import io
from pathlib import Path

from app.ingestion.parsers.base import BaseParser
from app.models.documents import Document, DocumentType, Section


class CsvParser(BaseParser):
    extensions = (".csv",)

    def parse(self, path: Path) -> Document:
        """Parse CSV file into unified Document schema.

        Produces:
          - Section 0: Dataset overview containing filename, column schema, row count,
            and sample rows for global semantic matching.
          - Section 1..N: Grouped row records (e.g. 10 rows per section) with
            'Column: value' pairs for detailed entity/property extraction.

        Args:
            path (Path): Filesystem path to the CSV file.

        Returns:
            Document: Populated Document instance.
        """
        raw_bytes = path.read_bytes()
        # Decode trying utf-8-sig first (handles BOM), then utf-8, fallback to latin-1
        text = ""
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        reader = csv.reader(io.StringIO(text))
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not rows:
            return Document(
                filename=path.name,
                doc_type=DocumentType.CSV,
                title=path.stem.replace("_", " "),
                source_path=str(path),
                sections=[Section(text="", order=0)],
            )

        headers = [h.strip() for h in rows[0]]
        data_rows = rows[1:]
        total_rows = len(data_rows)

        sections: list[Section] = []

        # ── 1. Dataset Overview Section (enables macro questions like "What is in this CSV?") ──
        overview_lines = [
            f"Dataset Name: {path.name}",
            f"Total Records: {total_rows}",
            f"Available Columns: {', '.join(headers)}",
            "",
            "Schema and Sample Records:",
        ]
        sample_limit = min(5, total_rows)
        for i, row in enumerate(data_rows[:sample_limit], start=1):
            sample_pairs = [f"{h}: {val.strip()}" for h, val in zip(headers, row) if val.strip()]
            overview_lines.append(f"Sample {i}: " + " | ".join(sample_pairs))

        sections.append(Section(
            title=f"{path.stem} Dataset Overview",
            text="\n".join(overview_lines),
            order=0,
            metadata={"sheet": "overview", "row_count": total_rows, "columns": headers},
        ))

        # ── 2. Structured Data Rows (grouped into chunks of 10 rows for clean chunking) ──
        batch_size = 10
        for batch_idx, start_idx in enumerate(range(0, total_rows, batch_size), start=1):
            batch = data_rows[start_idx:start_idx + batch_size]
            batch_lines = []
            for r_offset, row in enumerate(batch):
                row_num = start_idx + r_offset + 1
                pairs = [f"{h}: {val.strip()}" for h, val in zip(headers, row) if val.strip()]
                batch_lines.append(f"[Row {row_num}] " + " | ".join(pairs))

            sections.append(Section(
                title=f"{path.stem} Rows {start_idx + 1}-{start_idx + len(batch)}",
                text="\n\n".join(batch_lines),
                order=batch_idx,
                metadata={
                    "start_row": start_idx + 1,
                    "end_row": start_idx + len(batch),
                    "batch_size": len(batch),
                },
            ))

        return Document(
            filename=path.name,
            doc_type=DocumentType.CSV,
            title=path.stem.replace("_", " "),
            source_path=str(path),
            sections=sections,
            metadata={"row_count": total_rows, "columns": headers},
        )
