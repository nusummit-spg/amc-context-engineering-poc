"""
Excel/CSV parser — handles Fund Performance.xlsx, Average AUM/Fundwise/*.xlsx,
History NAV_.../*.xlsx|csv, mutual_fund_data.csv.

These are already structured (clean column headers, one fact per row) so they
are routed as "structured" — ingestion/pipeline.py sends route_hint=="structured"
sections straight to a deterministic ETL writer in graph/cypher_library.py,
skipping the NER/LLM extraction path entirely. This is a deliberate cost/
accuracy decision: don't pay an LLM to re-discover what a column header
already tells you.
"""
from typing import List, Dict
import pandas as pd

from ingestion.parsers.base import BaseParser, ParsedSection

# Column name variants we normalize to canonical keys. Extend as new sheet
# layouts show up in the corpus.
_COLUMN_ALIASES = {
    "scheme_name": {"scheme", "scheme name", "fund", "fund name", "plan"},
    "isin": {"isin", "isin code", "isin_growth"},
    "nav_date": {"date", "nav date", "as_of_date", "as on date"},
    "nav_value": {"nav", "nav value", "net asset value"},
    "aum_cr": {"aum", "aum (cr)", "aum in cr", "average aum"},
    "fund_house": {"amc", "fund house", "amc name"},
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for col in df.columns:
        col_clean = str(col).strip().lower()
        for canonical, aliases in _COLUMN_ALIASES.items():
            if col_clean in aliases:
                rename_map[col] = canonical
                break
    return df.rename(columns=rename_map)


class ExcelParser(BaseParser):
    supported_extensions = [".xlsx", ".xls", ".csv"]

    def parse(self, filepath: str) -> List[ParsedSection]:
        is_csv = filepath.lower().endswith(".csv")
        sheets: Dict[str, pd.DataFrame]

        if is_csv:
            sheets = {"csv": pd.read_csv(filepath)}
        else:
            sheets = pd.read_excel(filepath, sheet_name=None)  # all sheets

        sections: List[ParsedSection] = []
        for sheet_name, df in sheets.items():
            if df.empty:
                continue
            df = _normalize_columns(df)
            df = df.dropna(how="all")
            rows = df.to_dict(orient="records")

            sections.append(
                ParsedSection(
                    heading=sheet_name,
                    text=f"[structured data: {len(rows)} rows from sheet '{sheet_name}']",
                    source_file=filepath,
                    route_hint="structured",
                    structured_rows=rows,
                    metadata={"columns": list(df.columns), "row_count": len(rows)},
                )
            )
        return sections