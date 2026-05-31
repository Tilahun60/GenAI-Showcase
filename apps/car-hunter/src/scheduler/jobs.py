"""APScheduler job definitions for periodic scraping and processing."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import Settings
from ..filters.requirements import Requirements, RequirementsFilter
from ..leasing.calculator import LeasingCalculator
from ..models.database import CarListing, LeasingAnalysis, ScoredListing
from ..models.schemas import CarListingCreate, CarListingRead
from ..notifications.manager import NotificationManager
from ..scoring.market_analysis import MarketAnalyzer
from ..scoring.reliability import ReliabilityScorer
from ..scrapers.aaa_auto import AAAAutoScraper
from ..scrapers.das_weltauto import DasWeltAutoScraper
from ..scrapers.olx import OLXScraper
from ..scrapers.otomoto import OtomotoScraper
from ..scrapers.spoticar import SpoticarScraper
from ..scrapers.toyota_pewne import ToyotaPewneScraper

logger = logging.getLogger(__name__)


def _build_session_factory(db_url: str) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(db_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _run_all_scrapers(config: Settings) -> list[CarListingCreate]:
    scrapers = [
        OtomotoScraper(),
        OLXScraper(),
        AAAAutoScraper(),
        SpoticarScraper(),
        ToyotaPewneScraper(),
        DasWeltAutoScraper(),
    ]

    async def safe_scrape(scraper):
        try:
            return await scraper.scrape()
        except Exception as exc:
            logger.error("[%s] Scrape failed: %s", scraper.source_name, exc)
            return []

    results = await asyncio.gather(*[safe_scrape(s) for s in scrapers])
    all_listings: list[CarListingCreate] = []
    for batch in results:
        all_listings.extend(batch)
    logger.info("Scraped %d total listings across all sources", len(all_listings))
    return all_listings


async def _upsert_listing(session: AsyncSession, data: CarListingCreate) -> CarListing:
    result = await session.execute(
        select(CarListing).where(
            CarListing.source == data.source,
            CarListing.external_id == data.external_id,
        )
    )
    existing = result.scalars().first()
    now = datetime.now(tz=UTC)

    if existing:
        existing.last_seen_at = now
        existing.price_pln = data.price_pln
        existing.is_active = True
        await session.flush()
        return existing

    listing = CarListing(
        **data.model_dump(),
        first_seen_at=now,
        last_seen_at=now,
        is_active=True,
    )
    session.add(listing)
    await session.flush()
    return listing


async def scrape_and_process(config: Settings, session_factory: async_sessionmaker) -> None:
    """Main pipeline: scrape → filter → score → leasing → notify."""
    logger.info("=== Starting scrape_and_process job ===")

    raw_listings = await _run_all_scrapers(config)

    reqs = Requirements(
        max_price_pln=config.max_price_pln,
        min_year=config.min_year,
        max_mileage_km=config.max_mileage_km,
    )
    flt = RequirementsFilter(reqs)
    filtered = flt.filter_batch(raw_listings)
    logger.info("%d listings passed requirements filter (from %d)", len(filtered), len(raw_listings))

    scorer = ReliabilityScorer()
    leasing_calc = LeasingCalculator()

    async with session_factory() as session:
        analyzer = MarketAnalyzer(session)
        notifier = NotificationManager(config, session)

        for data in filtered:
            try:
                listing_row = await _upsert_listing(session, data)
                await session.commit()

                listing_read = CarListingRead.model_validate(listing_row)
                market_avg = await analyzer.get_market_avg(data.make, data.model, data.year)
                score_data = scorer.score(listing_read, market_avg)
                score_data.listing_id = listing_row.id

                # Check if already scored today
                existing_score = await session.execute(
                    select(ScoredListing).where(ScoredListing.listing_id == listing_row.id)
                )
                score_row = existing_score.scalars().first()
                if score_row:
                    score_row.total_score = score_data.total_score
                    score_row.is_suspicious = score_data.is_suspicious
                    score_row.market_avg_price = score_data.market_avg_price
                    score_row.price_deviation_pct = score_data.price_deviation_pct
                    score_row.scored_at = datetime.now(tz=UTC)
                else:
                    score_row = ScoredListing(**score_data.model_dump())
                    session.add(score_row)
                await session.flush()

                leasing_data = leasing_calc.calculate(listing_read)
                leasing_data.listing_id = listing_row.id
                existing_leasing = await session.execute(
                    select(LeasingAnalysis).where(LeasingAnalysis.listing_id == listing_row.id)
                )
                leasing_row = existing_leasing.scalars().first()
                if leasing_row:
                    leasing_row.monthly_payment_pln = leasing_data.monthly_payment_pln
                    leasing_row.total_cost_pln = leasing_data.total_cost_pln
                    leasing_row.cost_per_year_pln = leasing_data.cost_per_year_pln
                else:
                    leasing_row = LeasingAnalysis(**leasing_data.model_dump())
                    session.add(leasing_row)
                await session.commit()

                from ..models.schemas import LeasingAnalysisRead, ScoredListingRead
                score_read = ScoredListingRead.model_validate(score_row)
                leasing_read = LeasingAnalysisRead.model_validate(leasing_row)
                await notifier.notify_new_listing(listing_read, score_read, leasing_read)

            except Exception as exc:
                logger.error("Error processing listing %s/%s: %s", data.source, data.external_id, exc)
                await session.rollback()

    logger.info("=== scrape_and_process job complete ===")


async def cleanup_stale_listings(session_factory: async_sessionmaker) -> None:
    """Mark listings not seen in the last 7 days as inactive."""
    cutoff = datetime.now(tz=UTC) - timedelta(days=7)
    async with session_factory() as session:
        result = await session.execute(
            update(CarListing)
            .where(CarListing.last_seen_at < cutoff, CarListing.is_active.is_(True))
            .values(is_active=False)
        )
        await session.commit()
        logger.info("Marked %d stale listings as inactive", result.rowcount)
