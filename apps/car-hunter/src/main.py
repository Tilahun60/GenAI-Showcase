"""Car Hunter entry point — run scheduler, one-shot scrape, or list top listings."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from rich.console import Console
from rich.table import Table
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .config import get_settings
from .models.database import Base, CarListing, ScoredListing
from .scheduler.jobs import _build_session_factory, cleanup_stale_listings, scrape_and_process

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
console = Console()


async def _ensure_schema(db_url: str) -> None:
    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    logger.info("Database schema ready")


async def cmd_run(config) -> None:
    """Start the scheduler and run indefinitely."""
    await _ensure_schema(config.db_url)
    session_factory = _build_session_factory(config.db_url)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scrape_and_process,
        "interval",
        minutes=config.scrape_interval_minutes,
        args=[config, session_factory],
        id="scrape_and_process",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        cleanup_stale_listings,
        "cron",
        hour=3,
        minute=0,
        args=[session_factory],
        id="cleanup_stale",
    )

    scheduler.start()
    logger.info(
        "Scheduler started. Scraping every %d minutes. Press Ctrl+C to stop.",
        config.scrape_interval_minutes,
    )

    # Run immediately on startup
    await scrape_and_process(config, session_factory)

    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")


async def cmd_scrape(config) -> None:
    """Run a single scrape cycle and exit."""
    await _ensure_schema(config.db_url)
    session_factory = _build_session_factory(config.db_url)
    await scrape_and_process(config, session_factory)
    console.print("[green]One-shot scrape complete.[/green]")


async def cmd_list(config) -> None:
    """Pretty-print top 20 active listings sorted by reliability score."""
    engine = create_async_engine(config.db_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            select(CarListing, ScoredListing)
            .join(ScoredListing, ScoredListing.listing_id == CarListing.id)
            .where(CarListing.is_active.is_(True))
            .order_by(ScoredListing.total_score.desc())
            .limit(20)
        )
        rows = result.all()

    if not rows:
        console.print("[yellow]No active listings found. Run 'scrape' first.[/yellow]")
        return

    table = Table(title="Top Car Listings", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="bold")
    table.add_column("Price", justify="right", style="green")
    table.add_column("Year", justify="center")
    table.add_column("km", justify="right")
    table.add_column("Score", justify="center", style="cyan")
    table.add_column("vs Mkt", justify="right")
    table.add_column("Seller")
    table.add_column("Source", style="dim")

    for i, (listing, score) in enumerate(rows, 1):
        deviation = ""
        if score.price_deviation_pct is not None:
            sign = "+" if score.price_deviation_pct > 0 else ""
            deviation = f"{sign}{score.price_deviation_pct:.1f}%"
        score_style = "green" if score.total_score >= 8 else "yellow" if score.total_score >= 6 else "red"
        table.add_row(
            str(i),
            f"{listing.title[:45]}{'…' if len(listing.title) > 45 else ''}",
            f"{listing.price_pln:,.0f}",
            str(listing.year),
            f"{listing.mileage_km:,}",
            f"[{score_style}]{score.total_score}[/{score_style}]",
            deviation,
            listing.seller_type,
            listing.source,
        )

    console.print(table)
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Car Hunter — automated Polish used-car monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Start scheduler (runs indefinitely)")
    sub.add_parser("scrape", help="Run one scrape cycle and exit")
    sub.add_parser("list", help="Print top 20 listings by reliability score")

    args = parser.parse_args()
    config = get_settings()

    commands = {"run": cmd_run, "scrape": cmd_scrape, "list": cmd_list}
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(commands[args.command](config))


if __name__ == "__main__":
    main()
