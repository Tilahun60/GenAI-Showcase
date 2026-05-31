"""Market intelligence: average prices, fraud detection, resale estimates."""

from __future__ import annotations

import logging
import statistics
from typing import TYPE_CHECKING

from sqlalchemy import func, select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import CarListing
from ..models.schemas import CarListingCreate, CarListingRead

logger = logging.getLogger(__name__)

# Annual depreciation rates by brand origin
DEPRECIATION_RATES: dict[str, float] = {
    "toyota": 0.08,
    "lexus": 0.09,
    "honda": 0.10,
    "mazda": 0.10,
    "kia": 0.12,
    "hyundai": 0.12,
    "mitsubishi": 0.13,
    "ford": 0.14,
    "renault": 0.15,
    "peugeot": 0.15,
    "citroen": 0.16,
    "volkswagen": 0.13,
    "skoda": 0.13,
    "seat": 0.14,
    "default": 0.14,
}

SUSPICIOUS_PRICE_THRESHOLD = 0.70  # flag if < 70% of market avg


class MarketAnalyzer:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_market_avg(self, make: str, model: str, year: int) -> float | None:
        """Return avg price from DB for same make/model/year active listings."""
        result = await self._session.execute(
            select(func.avg(CarListing.price_pln)).where(
                CarListing.make == make.lower(),
                CarListing.model == model.lower(),
                CarListing.year == year,
                CarListing.is_active.is_(True),
            )
        )
        avg = result.scalar()
        return float(avg) if avg else None

    async def build_market_data(self, listings: list) -> dict[str, float]:
        """Build a market avg dict for a batch of listings efficiently."""
        market: dict[str, float] = {}
        seen: set[tuple] = set()
        for listing in listings:
            key_tuple = (listing.make.lower(), listing.model.lower(), listing.year)
            if key_tuple in seen:
                continue
            seen.add(key_tuple)
            avg = await self.get_market_avg(*key_tuple)
            if avg:
                market[f"{key_tuple[0]}_{key_tuple[1]}_{key_tuple[2]}"] = avg
        return market

    def is_suspiciously_cheap(self, listing: CarListingCreate | CarListingRead, market_avg: float) -> bool:
        return bool(market_avg > 0 and listing.price_pln < market_avg * SUSPICIOUS_PRICE_THRESHOLD)

    def estimate_resale_value(self, listing: CarListingCreate | CarListingRead, years: int = 3) -> float:
        rate = DEPRECIATION_RATES.get(listing.make.lower(), DEPRECIATION_RATES["default"])
        return listing.price_pln * ((1 - rate) ** years)

    def get_price_percentile(
        self,
        listing: CarListingCreate | CarListingRead,
        similar: list[CarListingCreate | CarListingRead],
    ) -> float:
        """Return 0-100 percentile of listing's price among similar listings (lower = cheaper)."""
        if not similar:
            return 50.0
        prices = sorted(l.price_pln for l in similar)
        below = sum(1 for p in prices if p <= listing.price_pln)
        return round((below / len(prices)) * 100, 1)

    def compute_inline_avg(self, listings: list) -> dict[str, float]:
        """Compute market averages from the batch itself (no DB needed)."""
        groups: dict[tuple, list[float]] = {}
        for l in listings:
            key = (l.make.lower(), l.model.lower(), l.year)
            groups.setdefault(key, []).append(l.price_pln)
        return {
            f"{k[0]}_{k[1]}_{k[2]}": statistics.mean(prices)
            for k, prices in groups.items()
            if prices
        }
