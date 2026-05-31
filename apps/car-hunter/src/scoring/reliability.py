"""Weighted reliability scorer for hybrid SUV listings."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models.schemas import CarListingCreate, CarListingRead, ScoredListingCreate

logger = logging.getLogger(__name__)

# (make_lower, model_lower_fragment) -> scores out of 10
RELIABILITY_DATA: dict[tuple[str, str], dict[str, float]] = {
    ("toyota", "c-hr"):          {"reliability": 9.2, "maintenance": 8.5, "resale": 9.0},
    ("toyota", "rav4"):          {"reliability": 9.0, "maintenance": 8.0, "resale": 9.2},
    ("toyota", "yaris cross"):   {"reliability": 9.1, "maintenance": 8.6, "resale": 8.8},
    ("toyota", "corolla cross"): {"reliability": 9.0, "maintenance": 8.4, "resale": 8.7},
    ("kia", "niro"):             {"reliability": 8.5, "maintenance": 8.8, "resale": 8.0},
    ("kia", "sportage"):         {"reliability": 8.3, "maintenance": 8.5, "resale": 8.2},
    ("kia", "sorento"):          {"reliability": 8.0, "maintenance": 8.2, "resale": 8.0},
    ("hyundai", "kona"):         {"reliability": 8.4, "maintenance": 8.7, "resale": 7.8},
    ("hyundai", "tucson"):       {"reliability": 8.2, "maintenance": 8.3, "resale": 8.0},
    ("hyundai", "santa fe"):     {"reliability": 7.9, "maintenance": 8.0, "resale": 7.8},
    ("mazda", "cx-5"):           {"reliability": 8.8, "maintenance": 8.0, "resale": 8.5},
    ("mazda", "cx-60"):          {"reliability": 8.4, "maintenance": 7.8, "resale": 8.2},
    ("honda", "hr-v"):           {"reliability": 8.6, "maintenance": 8.2, "resale": 7.9},
    ("honda", "cr-v"):           {"reliability": 8.4, "maintenance": 8.0, "resale": 8.1},
    ("ford", "kuga"):            {"reliability": 7.0, "maintenance": 6.5, "resale": 7.0},
    ("ford", "puma"):            {"reliability": 7.3, "maintenance": 6.8, "resale": 7.2},
    ("renault", "captur"):       {"reliability": 7.2, "maintenance": 7.8, "resale": 6.8},
    ("renault", "arkana"):       {"reliability": 7.0, "maintenance": 7.5, "resale": 6.5},
    ("peugeot", "3008"):         {"reliability": 7.5, "maintenance": 7.2, "resale": 7.3},
    ("peugeot", "2008"):         {"reliability": 7.3, "maintenance": 7.4, "resale": 7.0},
    ("mitsubishi", "eclipse cross"): {"reliability": 7.8, "maintenance": 7.5, "resale": 7.0},
    ("mitsubishi", "outlander"): {"reliability": 7.6, "maintenance": 7.3, "resale": 7.2},
    ("lexus", "ux"):             {"reliability": 9.3, "maintenance": 7.8, "resale": 8.8},
    ("lexus", "nx"):             {"reliability": 9.1, "maintenance": 7.6, "resale": 9.0},
}

# Default scores for unknown models (conservative)
DEFAULT_SCORES: dict[str, float] = {"reliability": 6.5, "maintenance": 6.5, "resale": 6.0}

# Weights must sum to 1.0
WEIGHTS = {
    "reliability": 0.35,
    "maintenance": 0.20,
    "mileage": 0.15,
    "service_history": 0.10,
    "price_value": 0.10,
    "resale": 0.10,
}


def _mileage_score(mileage_km: int) -> float:
    """Linear decay: 0 km -> 10.0, 150k km -> 5.0, 250k+ -> 0."""
    if mileage_km <= 0:
        return 10.0
    if mileage_km >= 250_000:
        return 0.0
    if mileage_km <= 150_000:
        return 10.0 - (mileage_km / 150_000) * 5.0
    return 5.0 - ((mileage_km - 150_000) / 100_000) * 5.0


def _service_history_score(seller_type: str, raw_data: dict | None) -> float:
    """Infer service history score from available metadata."""
    raw = raw_data or {}
    history_flag = str(raw.get("service_history", raw.get("serwis", ""))).lower()
    if "pełna" in history_flag or "full" in history_flag or "complete" in history_flag:
        return 8.5
    if "częściowa" in history_flag or "partial" in history_flag:
        return 6.0
    if "brak" in history_flag or "none" in history_flag:
        return 2.0
    # Dealer listings statistically more likely to have history
    return 7.0 if seller_type == "dealer" else 5.0


def _price_value_score(price_pln: float, market_avg: float | None) -> float:
    """Score pricing vs market average. 10 = great deal, 5 = average, 0 = overpriced."""
    if not market_avg or market_avg <= 0:
        return 5.0
    ratio = price_pln / market_avg
    if ratio <= 0.80:
        return 10.0
    if ratio <= 0.90:
        return 8.0
    if ratio <= 1.00:
        return 6.0
    if ratio <= 1.10:
        return 4.0
    return 2.0


def _lookup_model_scores(make: str, model: str) -> dict[str, float]:
    make_l = make.lower().strip()
    model_l = model.lower().strip()
    for (m, mod), scores in RELIABILITY_DATA.items():
        if m == make_l and mod in model_l:
            return scores
    # Try partial make match
    for (m, mod), scores in RELIABILITY_DATA.items():
        if m == make_l:
            return scores
    return DEFAULT_SCORES


class ReliabilityScorer:
    def score(
        self,
        listing: CarListingCreate | CarListingRead,
        market_avg: float | None = None,
    ) -> ScoredListingCreate:
        model_scores = _lookup_model_scores(listing.make, listing.model)
        reliability_s = model_scores["reliability"]
        maintenance_s = model_scores["maintenance"]
        resale_s = model_scores["resale"]
        mileage_s = _mileage_score(listing.mileage_km)
        service_s = _service_history_score(listing.seller_type, listing.raw_data)
        price_s = _price_value_score(listing.price_pln, market_avg)

        total = (
            reliability_s * WEIGHTS["reliability"]
            + maintenance_s * WEIGHTS["maintenance"]
            + mileage_s * WEIGHTS["mileage"]
            + service_s * WEIGHTS["service_history"]
            + price_s * WEIGHTS["price_value"]
            + resale_s * WEIGHTS["resale"]
        )

        deviation_pct: float | None = None
        if market_avg and market_avg > 0:
            deviation_pct = ((listing.price_pln - market_avg) / market_avg) * 100

        is_suspicious = bool(market_avg and listing.price_pln < market_avg * 0.70)

        listing_id = getattr(listing, "id", None)

        return ScoredListingCreate(
            listing_id=listing_id,  # type: ignore[arg-type]
            reliability_score=round(reliability_s, 2),
            reliability_weight=WEIGHTS["reliability"],
            maintenance_score=round(maintenance_s, 2),
            maintenance_weight=WEIGHTS["maintenance"],
            mileage_score=round(mileage_s, 2),
            mileage_weight=WEIGHTS["mileage"],
            service_history_score=round(service_s, 2),
            service_history_weight=WEIGHTS["service_history"],
            price_value_score=round(price_s, 2),
            price_value_weight=WEIGHTS["price_value"],
            resale_score=round(resale_s, 2),
            resale_weight=WEIGHTS["resale"],
            total_score=round(min(total, 10.0), 2),
            market_avg_price=market_avg,
            price_deviation_pct=round(deviation_pct, 1) if deviation_pct is not None else None,
            is_suspicious=is_suspicious,
        )

    def rank_listings(
        self,
        listings: list,
        market_data: dict[str, float] | None = None,
    ) -> list[ScoredListingCreate]:
        market_data = market_data or {}
        scored = []
        for listing in listings:
            key = f"{listing.make}_{listing.model}_{listing.year}"
            avg = market_data.get(key)
            scored.append(self.score(listing, avg))
        return sorted(scored, key=lambda s: s.total_score, reverse=True)
