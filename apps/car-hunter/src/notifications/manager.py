"""Notification manager — routes alerts to active channels and deduplicates."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models.database import AlertLog
from ..models.schemas import CarListingRead, LeasingAnalysisRead, ScoredListingRead
from .base import BaseNotifier
from .discord import DiscordNotifier
from .gmail import GmailNotifier
from .telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class NotificationManager:
    def __init__(self, config: Settings, db_session: AsyncSession) -> None:
        self._config = config
        self._db = db_session
        self._notifiers: list[BaseNotifier] = self._build_notifiers(config)

    def _build_notifiers(self, cfg: Settings) -> list[BaseNotifier]:
        notifiers: list[BaseNotifier] = []
        if cfg.telegram_bot_token and cfg.telegram_chat_id:
            notifiers.append(TelegramNotifier(cfg.telegram_bot_token, cfg.telegram_chat_id))
        if cfg.gmail_user and cfg.gmail_app_password and cfg.gmail_to:
            notifiers.append(GmailNotifier(cfg.gmail_user, cfg.gmail_app_password, cfg.gmail_to))
        if cfg.discord_webhook_url:
            notifiers.append(DiscordNotifier(cfg.discord_webhook_url))
        if not notifiers:
            logger.warning("No notification channels configured. Set env vars to enable alerts.")
        return notifiers

    async def notify_new_listing(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> None:
        if score.total_score < self._config.alert_score_threshold:
            logger.debug(
                "Listing %s score %.2f below threshold %.2f — skipping alert",
                listing.id, score.total_score, self._config.ALERT_SCORE_THRESHOLD,
            )
            return

        tasks = []
        for notifier in self._notifiers:
            if await self._already_alerted(listing.id, notifier.channel_name):
                logger.debug("[%s] Already alerted for listing %s", notifier.channel_name, listing.id)
                continue
            tasks.append(self._send_and_log(notifier, listing, score, leasing))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_and_log(
        self,
        notifier: BaseNotifier,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> None:
        success = await notifier.send(listing, score, leasing)
        preview = notifier.format_text(listing, score, leasing)[:200]
        log_entry = AlertLog(
            listing_id=listing.id,
            channel=notifier.channel_name,
            sent_at=datetime.now(tz=UTC),
            success=success,
            message_preview=preview,
        )
        self._db.add(log_entry)
        await self._db.commit()

    async def _already_alerted(self, listing_id, channel: str) -> bool:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
        result = await self._db.execute(
            select(AlertLog).where(
                AlertLog.listing_id == listing_id,
                AlertLog.channel == channel,
                AlertLog.sent_at >= cutoff,
                AlertLog.success.is_(True),
            )
        )
        return result.scalars().first() is not None
