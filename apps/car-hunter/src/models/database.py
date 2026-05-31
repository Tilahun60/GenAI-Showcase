"""SQLAlchemy async models for the Car Hunter application."""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all models."""
    pass


class CarListing(Base):
    """A car listing scraped from one of the monitored sources."""
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    make: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    price_pln: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    mileage_km: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(50), nullable=False)
    transmission: Mapped[str] = mapped_column(String(50), nullable=False)
    body_type: Mapped[str] = mapped_column(String(50), nullable=True)
    accident_history: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    seller_type: Mapped[str] = mapped_column(String(50), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    scores: Mapped[list[ScoredListing]] = relationship(
        "ScoredListing", back_populates="listing", cascade="all, delete-orphan"
    )
    leasing_analyses: Mapped[list[LeasingAnalysis]] = relationship(
        "LeasingAnalysis", back_populates="listing", cascade="all, delete-orphan"
    )
    alert_logs: Mapped[list[AlertLog]] = relationship(
        "AlertLog", back_populates="listing", cascade="all, delete-orphan"
    )


class ScoredListing(Base):
    """Scoring breakdown for a car listing."""
    __tablename__ = "scored_listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Scoring components
    reliability_score: Mapped[float] = mapped_column(Float, nullable=False)
    reliability_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    maintenance_score: Mapped[float] = mapped_column(Float, nullable=False)
    maintenance_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.20)
    mileage_score: Mapped[float] = mapped_column(Float, nullable=False)
    mileage_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    service_history_score: Mapped[float] = mapped_column(Float, nullable=False)
    service_history_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    price_value_score: Mapped[float] = mapped_column(Float, nullable=False)
    price_value_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)
    resale_score: Mapped[float] = mapped_column(Float, nullable=False)
    resale_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.10)

    total_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    market_avg_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped[CarListing] = relationship("CarListing", back_populates="scores")


class LeasingAnalysis(Base):
    """Leasing cost analysis for a car listing."""
    __tablename__ = "leasing_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    down_payment_pln: Mapped[float] = mapped_column(Float, nullable=False)
    monthly_payment_pln: Mapped[float] = mapped_column(Float, nullable=False)
    buyout_value_pln: Mapped[float] = mapped_column(Float, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_pln: Mapped[float] = mapped_column(Float, nullable=False)
    cost_per_year_pln: Mapped[float] = mapped_column(Float, nullable=False)
    estimated_maintenance_yearly_pln: Mapped[float] = mapped_column(Float, nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    listing: Mapped[CarListing] = relationship("CarListing", back_populates="leasing_analyses")


class AlertLog(Base):
    """Log of sent alert notifications."""
    __tablename__ = "alert_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    message_preview: Mapped[str | None] = mapped_column(String(500), nullable=True)

    listing: Mapped[CarListing] = relationship("CarListing", back_populates="alert_logs")


# ---------------------------------------------------------------------------
# Engine / session helpers
# ---------------------------------------------------------------------------

_engine = None
_async_session_factory = None


def _get_engine(db_url: str):
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory(db_url: str):
    global _async_session_factory
    if _async_session_factory is None:
        engine = _get_engine(db_url)
        _async_session_factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
    return _async_session_factory


async def get_async_session(db_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Dependency / context manager that yields an AsyncSession."""
    factory = _get_session_factory(db_url)
    async with factory() as session:
        yield session


async def init_db(db_url: str) -> None:
    """Create all tables (for development / testing without alembic)."""
    engine = _get_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
