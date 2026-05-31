"""Leasing cost calculator using PMT formula."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models.schemas import CarListingCreate, CarListingRead, LeasingAnalysisCreate

logger = logging.getLogger(__name__)

# Estimated annual maintenance costs (PLN) by make
MAINTENANCE_YEARLY: dict[str, float] = {
    "toyota": 2_800.0,
    "lexus": 3_500.0,
    "honda": 3_000.0,
    "mazda": 3_200.0,
    "kia": 3_200.0,
    "hyundai": 3_200.0,
    "mitsubishi": 3_400.0,
    "ford": 4_200.0,
    "renault": 4_000.0,
    "peugeot": 4_000.0,
    "citroen": 4_200.0,
    "volkswagen": 4_500.0,
    "skoda": 4_000.0,
    "seat": 4_200.0,
    "default": 4_500.0,
}


@dataclass
class LeasingParams:
    down_payment_pct: float = 0.20   # 20% upfront
    term_months: int = 48             # 4-year lease
    interest_rate_annual: float = 0.089  # 8.9% typical Poland 2024
    buyout_pct: float = 0.30          # 30% residual / buyout


def _pmt(rate_monthly: float, n_months: int, present_value: float) -> float:
    """Standard PMT loan payment formula."""
    if rate_monthly == 0:
        return present_value / n_months
    return present_value * (rate_monthly * (1 + rate_monthly) ** n_months) / ((1 + rate_monthly) ** n_months - 1)


class LeasingCalculator:
    def calculate(
        self,
        listing: CarListingCreate | CarListingRead,
        params: LeasingParams | None = None,
    ) -> LeasingAnalysisCreate:
        p = params or LeasingParams()
        price = listing.price_pln

        down_payment = round(price * p.down_payment_pct, 2)
        buyout_value = round(price * p.buyout_pct, 2)

        # Financed amount = price - down payment - PV of residual
        rate_monthly = p.interest_rate_annual / 12
        # NPV of residual at end of term
        pv_residual = buyout_value / ((1 + rate_monthly) ** p.term_months)
        financed = price - down_payment - pv_residual

        monthly = round(_pmt(rate_monthly, p.term_months, financed), 2)
        total_payments = monthly * p.term_months
        total_cost = round(down_payment + total_payments + buyout_value, 2)
        cost_per_year = round(total_cost / (p.term_months / 12), 2)

        maintenance = self.estimate_maintenance_yearly(listing.make)

        listing_id = getattr(listing, "id", None)

        return LeasingAnalysisCreate(
            listing_id=listing_id,  # type: ignore[arg-type]
            down_payment_pln=down_payment,
            monthly_payment_pln=monthly,
            buyout_value_pln=buyout_value,
            term_months=p.term_months,
            total_cost_pln=total_cost,
            cost_per_year_pln=cost_per_year,
            estimated_maintenance_yearly_pln=maintenance,
        )

    def estimate_maintenance_yearly(self, make: str) -> float:
        return MAINTENANCE_YEARLY.get(make.lower(), MAINTENANCE_YEARLY["default"])
