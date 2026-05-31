"""Telegram bot notifier using python-telegram-bot."""
from __future__ import annotations

import logging

import httpx

from ..models.schemas import CarListingRead, LeasingAnalysisRead, ScoredListingRead
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    channel_name = "telegram"

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._api_base = f"https://api.telegram.org/bot{bot_token}"

    async def send(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> bool:
        text = self._build_message(listing, score, leasing)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._api_base}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,
                    },
                )
                resp.raise_for_status()
                logger.info("[telegram] Alert sent for listing %s", listing.id)
                return True
        except Exception as exc:
            logger.error("[telegram] Failed to send alert: %s", exc)
            return False

    def _build_message(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> str:
        score_emoji = "🟢" if score.total_score >= 8 else "🟡" if score.total_score >= 6 else "🔴"
        suspicious_warning = "\n⚠️ <b>Price suspiciously low — verify carefully!</b>" if score.is_suspicious else ""

        leasing_block = ""
        if leasing:
            leasing_block = (
                "\n\n📋 <b>Leasing estimate</b>\n"
                f"  ↳ Down payment: <b>{leasing.down_payment_pln:,.0f} PLN</b>\n"
                f"  ↳ Monthly: <b>{leasing.monthly_payment_pln:,.0f} PLN</b>\n"
                f"  ↳ Buyout: <b>{leasing.buyout_value_pln:,.0f} PLN</b>\n"
                f"  ↳ Total {leasing.term_months}mo cost: <b>{leasing.total_cost_pln:,.0f} PLN</b>\n"
                f"  ↳ Cost/year (incl. maintenance): "
                f"<b>{leasing.cost_per_year_pln + leasing.estimated_maintenance_yearly_pln:,.0f} PLN</b>"
            )

        deviation = ""
        if score.price_deviation_pct is not None:
            sign = "+" if score.price_deviation_pct > 0 else ""
            deviation = f"\n📊 vs market avg: <b>{sign}{score.price_deviation_pct:.1f}%</b>"

        return (
            f"🚗 <b>New car found!</b>\n\n"
            f"<b>{listing.title}</b>\n"
            f"💰 <b>{listing.price_pln:,.0f} PLN</b>\n\n"
            f"📅 Year: {listing.year}\n"
            f"🛣 Mileage: {listing.mileage_km:,} km\n"
            f"⛽ Fuel: {listing.fuel_type.capitalize()}\n"
            f"🔄 Gearbox: {listing.transmission.capitalize()}\n"
            f"🏪 Seller: {listing.seller_type.capitalize()}\n"
            f"📍 Location: {listing.location or 'N/A'}\n\n"
            f"{score_emoji} Reliability score: <b>{score.total_score}/10</b>"
            f"{deviation}"
            f"{suspicious_warning}"
            f"{leasing_block}\n\n"
            f"🔗 <a href=\"{listing.url}\">View listing</a>"
        )
