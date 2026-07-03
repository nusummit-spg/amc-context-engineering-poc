"""Graph schema — uniqueness constraints matching the ontology's canonical keys."""
from graph.client import run_write

CONSTRAINTS = [
    "CREATE CONSTRAINT fund_house_amfi IF NOT EXISTS FOR (fh:FundHouse) REQUIRE fh.amfi_code IS UNIQUE",
    "CREATE CONSTRAINT scheme_isin IF NOT EXISTS FOR (s:Scheme) REQUIRE s.isin_growth IS UNIQUE",
    "CREATE CONSTRAINT holding_isin IF NOT EXISTS FOR (h:Holding) REQUIRE h.isin IS UNIQUE",
    "CREATE CONSTRAINT issuer_name IF NOT EXISTS FOR (i:Issuer) REQUIRE i.name IS UNIQUE",
    "CREATE CONSTRAINT issuer_group_name IF NOT EXISTS FOR (g:IssuerGroup) REQUIRE g.name IS UNIQUE",
    "CREATE CONSTRAINT circular_no IF NOT EXISTS FOR (c:RegulatoryCircular) REQUIRE c.circular_no IS UNIQUE",
    "CREATE CONSTRAINT theme_name IF NOT EXISTS FOR (t:RiskTheme) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT analyst_name IF NOT EXISTS FOR (a:Analyst) REQUIRE a.name IS UNIQUE",
    "CREATE CONSTRAINT benchmark_name IF NOT EXISTS FOR (b:Benchmark) REQUIRE b.name IS UNIQUE",
    "CREATE CONSTRAINT fund_manager_name IF NOT EXISTS FOR (fm:FundManager) REQUIRE fm.name IS UNIQUE",
    # NAVRecord / AUMFigure are append-only time series -> no uniqueness constraint,
    # but index on date for fast range queries.
    "CREATE INDEX nav_date_idx IF NOT EXISTS FOR (n:NAVRecord) ON (n.date)",
    "CREATE INDEX aum_date_idx IF NOT EXISTS FOR (n:AUMFigure) ON (n.date)",
]


def setup_schema():
    for stmt in CONSTRAINTS:
        run_write(stmt)
        print(f"[schema] applied: {stmt.split('FOR')[0].strip()}")


if __name__ == "__main__":
    setup_schema()