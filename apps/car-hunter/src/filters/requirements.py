"""Requirements engine — filters raw listings against user-defined criteria."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..models.schemas import CarListingCreate, CarListingRead

logger = logging.getLogger(__name__)


@dataclass
class Requirements:
    max_price_pln: float = 60_000.0
    body_types: list[str] = field(default_factory=lambda: ["suv"])
    min_year: int = 2020
    fuel_types: list[str] = field(default_factory=lambda: ["hybrid"])
    transmissions: list[str] = field(default_factory=lambda: ["automatic"])
    max_mileage_km: int = 150_000
    exclude_accident_history: bool = True
    allowed_seller_types: list[str] = field(default_factory=lambda: ["dealer", "private"])


class RequirementsFilter:
    def __init__(self, reqs: Requirements | None = None) -> None:
        self.reqs = reqs or Requirements()

    def matches(self, listing: CarListingCreate | CarListingRead) -> bool:
        r = self.reqs

        if listing.price_pln <= 0 or listing.price_pln > r.max_price_pln:
            return False

        if r.body_types and listing.body_type and listing.body_type.lower() not in r.body_types:
            return False

        if listing.year < r.min_year:
            return False

        if r.fuel_types and listing.fuel_type.lower() not in r.fuel_types:
            return False

        if r.transmissions and listing.transmission.lower() not in r.transmissions:
            return False

        if listing.mileage_km > r.max_mileage_km:
            return False

        if r.exclude_accident_history and listing.accident_history is True:
            return False

        return not (
            r.allowed_seller_types
            and listing.seller_type.lower() not in r.allowed_seller_types
        )

    def filter_batch(
        self, listings: list[CarListingCreate] | list[CarListingRead]
    ) -> list:
        passed = [item for item in listings if self.matches(item)]
        logger.info(
            "Requirements filter: %d/%d listings passed",
            len(passed),
            len(listings),
        )
        return passed
