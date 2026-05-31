"""Discord webhook notifier."""
from __future__ import annotations

import logging

import httpx

from ..models.schemas import CarListingRead, LeasingAnalysisRead, ScoredListingRead
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class DiscordNotifier(BaseNotifier):
    channel_name = "discord"

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    async def send(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> bool:
        payload = self._build_payload(listing, score, leasing)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
                logger.info("[discord] Alert sent for listing %s", listing.id)
                return True
        except Exception as exc:
            logger.error("[discord] Failed to send alert: %s", exc)
            return False

    def _build_payload(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> dict:
        # Color: green for >=8, yellow for >=6, red for <6
        color = 0x27AE60 if score.total_score >= 8 else 0xF39C12 if score.total_score >= 6 else 0xE74C3C

        fields = [
            {"name": "💰 Price", "value": f"{listing.price_pln:,.0f} PLN", "inline": True},
            {"name": "📅 Year", "value": str(listing.year), "inline": True},
            {"name": "🛣 Mileage", "value": f"{listing.mileage_km:,} km", "inline": True},
            {"name": "⛽ Fuel", "value": listing.fuel_type.capitalize(), "inline": True},
            {"name": "🔄 Gearbox", "value": listing.transmission.capitalize(), "inline": True},
            {"name": "🏪 Seller", "value": listing.seller_type.capitalize(), "inline": True},
            {"name": "📍 Location", "value": listing.location or "N/A", "inline": True},
            {"name": "⭐ Score", "value": f"{score.total_score}/10", "inline": True},
        ]

        if score.price_deviation_pct is not None:
            sign = "+" if score.price_deviation_pct > 0 else ""
            fields.append({
                "name": "📊 vs Market",
                "value": f"{sign}{score.price_deviation_pct:.1f}%",
                "inline": True,
            })

        if score.is_suspicious:
            fields.append({
                "name": "⚠️ Warning",
                "value": "Price suspiciously low — verify carefully!",
                "inline": False,
            })

        if leasing:
            fields.append({
                "name": "📋 Leasing Estimate",
                "value": (
                    f"Down: **{leasing.down_payment_pln:,.0f} PLN**\n"
                    f"Monthly: **{leasing.monthly_payment_pln:,.0f} PLN**\n"
                    f"Total ({leasing.term_months}mo): **{leasing.total_cost_pln:,.0f} PLN**"
                ),
                "inline": False,
            })

        return {
            "embeds": [{
                "title": f"🚗 {listing.title}",
                "url": listing.url,
                "color": color,
                "fields": fields,
                "footer": {"text": f"Car Hunter | Source: {listing.source}"},
            }]
        }
