"""Abstract base notifier."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.schemas import CarListingRead, LeasingAnalysisRead, ScoredListingRead


class BaseNotifier(ABC):
    channel_name: str = "unknown"

    @abstractmethod
    async def send(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> bool:
        """Send alert. Returns True on success."""

    def format_text(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> str:
        lines = [
            f"🚗 NEW CAR FOUND — {listing.title}",
            f"💰 {listing.price_pln:,.0f} PLN",
            f"📅 Year: {listing.year}  |  🛣 {listing.mileage_km:,} km",
            f"⛽ {listing.fuel_type.capitalize()}  |  🔄 {listing.transmission.capitalize()}",
            f"🏪 Seller: {listing.seller_type.capitalize()}  |  📍 {listing.location or 'N/A'}",
            f"⭐ Reliability score: {score.total_score}/10",
        ]
        if score.price_deviation_pct is not None:
            sign = "+" if score.price_deviation_pct > 0 else ""
            lines.append(f"📊 vs market avg: {sign}{score.price_deviation_pct:.1f}%")
        if score.is_suspicious:
            lines.append("⚠️  Price suspiciously low — verify carefully!")
        if leasing:
            lines += [
                "",
                "📋 LEASING ESTIMATE",
                f"  Down payment: {leasing.down_payment_pln:,.0f} PLN",
                f"  Monthly: {leasing.monthly_payment_pln:,.0f} PLN",
                f"  Total cost: {leasing.total_cost_pln:,.0f} PLN",
                f"  Cost/year: {leasing.cost_per_year_pln:,.0f} PLN",
            ]
        lines.append(f"\n🔗 {listing.url}")
        return "\n".join(lines)
