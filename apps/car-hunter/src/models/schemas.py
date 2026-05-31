"""Pydantic v2 schemas for serialization and validation."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CarListingCreate(BaseModel):
    """Schema for creating a new car listing (from scrapers)."""
    model_config = ConfigDict(populate_by_name=True)

    source: str
    external_id: str
    url: str
    title: str
    make: str
    model: str
    year: int = Field(ge=1990, le=2030)
    price_pln: float = Field(ge=0)
    mileage_km: int = Field(ge=0)
    fuel_type: str
    transmission: str
    body_type: str | None = None
    accident_history: bool | None = None
    seller_type: str
    location: str | None = None
    raw_data: dict | None = None


class CarListingRead(CarListingCreate):
    """Schema for reading a car listing from the DB."""
    id: uuid.UUID
    first_seen_at: datetime
    last_seen_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class ScoredListingCreate(BaseModel):
    """Schema for creating a scored listing."""
    listing_id: uuid.UUID
    reliability_score: float
    reliability_weight: float = 0.35
    maintenance_score: float
    maintenance_weight: float = 0.20
    mileage_score: float
    mileage_weight: float = 0.15
    service_history_score: float
    service_history_weight: float = 0.10
    price_value_score: float
    price_value_weight: float = 0.10
    resale_score: float
    resale_weight: float = 0.10
    total_score: float
    market_avg_price: float | None = None
    price_deviation_pct: float | None = None
    is_suspicious: bool = False


class ScoredListingRead(ScoredListingCreate):
    """Schema for reading a scored listing from the DB."""
    id: uuid.UUID
    scored_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LeasingAnalysisCreate(BaseModel):
    """Schema for creating a leasing analysis."""
    listing_id: uuid.UUID
    down_payment_pln: float
    monthly_payment_pln: float
    buyout_value_pln: float
    term_months: int
    total_cost_pln: float
    cost_per_year_pln: float
    estimated_maintenance_yearly_pln: float


class LeasingAnalysisRead(LeasingAnalysisCreate):
    """Schema for reading a leasing analysis from the DB."""
    id: uuid.UUID
    calculated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertLogCreate(BaseModel):
    """Schema for creating an alert log entry."""
    listing_id: uuid.UUID
    channel: str
    success: bool = False
    message_preview: str | None = None


class AlertLogRead(AlertLogCreate):
    """Schema for reading an alert log entry from the DB."""
    id: uuid.UUID
    sent_at: datetime

    model_config = ConfigDict(from_attributes=True)
