# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Phase 3 — Layer D: Table-to-FinancialFact Extractor.

Converts markdown tables extracted from PDFs/CSVs into structured FinancialFact
and TableFact nodes for Neo4j graph ingestion.
"""
import logging
import re
from typing import Any

logger = logging.getLogger("extraction.tables")

# Pattern for matching numeric values with currency/units (e.g. ₹2,300 Cr, 25.6%, 4.50%)
_NUMERIC_VAL_RE = re.compile(r"(?:₹|Rs\.?|\$)?\s*([+\-]?\d[\d,]*\.?\d*)\s*(Cr|Crore|Lakh|%|Billion|Million|bps)?", re.IGNORECASE)


def extract_financial_facts_from_table(
    table_md: str, document_id: str, page_num: int = 1
) -> list[dict[str, Any]]:
    """Parses a markdown table string into structured FinancialFact dicts.
    
    Example input:
      | Metric | FY24 | FY25 |
      | Revenue | ₹2,300 Cr | ₹2,890 Cr |
      | EBITDA | ₹450 Cr | ₹620 Cr |
    """
    if not table_md or "|" not in table_md:
        return []

    lines = [line.strip() for line in table_md.strip().split("\n") if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    
    if len(table_lines) < 3:  # Header, separator, at least 1 data row
        return []

    def _parse_row(row_str: str) -> list[str]:
        return [cell.strip() for cell in row_str.strip("|").split("|")]

    headers = _parse_row(table_lines[0])
    data_rows = [line for line in table_lines[2:] if not all(c == "-" for c in line.replace("|", "").strip())]

    facts: list[dict[str, Any]] = []

    for row_idx, row_line in enumerate(data_rows):
        cells = _parse_row(row_line)
        if not cells or len(cells) < 2:
            continue

        metric_label = cells[0]
        if not metric_label or metric_label.startswith("---"):
            continue

        for col_idx, cell_value in enumerate(cells[1:], start=1):
            if not cell_value or cell_value in ("-", "N/A", "NA", "nil"):
                continue

            period_header = headers[col_idx] if col_idx < len(headers) else f"Col_{col_idx}"
            
            # Match numeric figures and units
            match = _NUMERIC_VAL_RE.search(cell_value)
            if match:
                raw_num = match.group(1).replace(",", "")
                try:
                    val_num = float(raw_num)
                except ValueError:
                    continue

                unit = match.group(2) or ""
                
                facts.append({
                    "entity_type": "FinancialMetric",
                    "metric_name": metric_label,
                    "value": val_num,
                    "unit": unit,
                    "period": period_header,
                    "raw_text": cell_value,
                    "document_id": document_id,
                    "page_num": page_num,
                    "row_index": row_idx,
                })
            else:
                # Store non-numeric tabular fact as TableFact
                facts.append({
                    "entity_type": "TableFact",
                    "metric_name": metric_label,
                    "value": cell_value,
                    "column_header": period_header,
                    "document_id": document_id,
                    "page_num": page_num,
                })

    logger.info("Extracted %d table facts from document %s (page %d)", len(facts), document_id, page_num)
    return facts
