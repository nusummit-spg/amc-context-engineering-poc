# ---------------------------------------------------------
# TABLE 6: fund_schemes
# ---------------------------------------------------------

from app.core.database import Base
from sqlalchemy import (
    CheckConstraint,
    Float,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from app.schemas.models import (
    Region,
    _now_iso,
)

class FundScheme(Base):
    __tablename__ = "fund_schemes"

    fund_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    isin: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fund_house: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    mandate: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_profile: Mapped[str | None] = mapped_column(String(40), nullable=True)

    aum_crores: Mapped[float | None] = mapped_column(Float, nullable=True)
    nav_per_unit: Mapped[float | None] = mapped_column(Float, nullable=True)

    region: Mapped[Region] = mapped_column(String(10), nullable=False, index=True)
    applicable_rules_json: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False, default=_now_iso)

    __table_args__ = (
        UniqueConstraint("fund_id", "region", name="uq_fund_region"),
        CheckConstraint("region IN ('SEBI','SEC','ESMA')", name="ck_fund_region"),
    )

