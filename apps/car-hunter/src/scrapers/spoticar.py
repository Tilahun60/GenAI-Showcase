"""Scraper for Spoticar.pl - Stellantis certified used car program."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models.schemas import CarListingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.spoticar.pl"

# Spoticar has migrated to Polish URL paths; try both in order
SEARCH_URL_CANDIDATES = [
    f"{BASE_URL}/pl/samochody-uzywane",
    f"{BASE_URL}/pl/used-cars",
    f"{BASE_URL}/used-cars",
]

SEARCH_URL = SEARCH_URL_CANDIDATES[0]


class SpoticarScraper(BaseScraper):
    """Scrapes hybrid SUV listings from Spoticar.pl (Stellantis certified used)."""

    source_name = "spoticar"
    base_url = SEARCH_URL

    DEFAULT_PARAMS = {
        "fuelType": "hybrid",
        "gearboxType": "automatic",
        "bodyType": "SUV",
        "sort": "price_asc",
    }

    async def scrape(self) -> list[CarListingCreate]:
        """Scrape Spoticar listings, trying URL candidates until one succeeds."""
        listings: list[CarListingCreate] = []

        async with self:
            # Find a working URL
            working_url = await self._resolve_search_url()
            if not working_url:
                logger.warning("[spoticar] No working search URL found")
                return listings

            page = 1
            max_pages = 6
            while page <= max_pages:
                params = {**self.DEFAULT_PARAMS, "page": str(page)}
                try:
                    html = await self._fetch_page(working_url, params=params)
                    page_listings = self._parse_page(html)
                    if not page_listings:
                        logger.info("[spoticar] No more listings at page %d", page)
                        break
                    listings.extend(page_listings)
                    logger.info("[spoticar] Page %d: found %d listings", page, len(page_listings))
                    page += 1
                except Exception as exc:
                    logger.error("[spoticar] Error fetching page %d: %s", page, exc)
                    break

        logger.info("[spoticar] Total scraped: %d listings", len(listings))
        return listings

    async def _resolve_search_url(self) -> str | None:
        """Return the first URL candidate that responds with 200."""
        for url in SEARCH_URL_CANDIDATES:
            try:
                html = await self._fetch_page(url)
                if html:
                    logger.info("[spoticar] Using search URL: %s", url)
                    return url
            except Exception as exc:
                logger.debug("[spoticar] URL %s failed: %s", url, exc)
        return None

    def _parse_page(self, html: str) -> list[CarListingCreate]:
        """Parse Spoticar search results page."""
        soup = BeautifulSoup(html, "lxml")
        listings: list[CarListingCreate] = []

        # Spoticar uses Bootstrap-based card layout
        cards = (
            soup.select("div.vehicle-card")
            or soup.select("article.car-offer")
            or soup.select("div[class*='vehicle-item']")
            or soup.select("div[class*='car-card']")
        )

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                logger.debug("[spoticar] Skipping card: %s", exc)

        return listings

    def _parse_card(self, card) -> CarListingCreate | None:
        """Parse a single Spoticar listing card."""
        link = card.select_one("a[href]")
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = urljoin(BASE_URL, url)

        # External ID from URL
        id_match = re.search(r"[/-](\d{5,})", url)
        external_id = id_match.group(1) if id_match else url.rstrip("/").split("/")[-1]

        title_tag = card.select_one("h2") or card.select_one("h3") or card.select_one("[class*='title']")
        title = title_tag.get_text(strip=True) if title_tag else ""

        price_tag = (
            card.select_one("[class*='price']")
            or card.select_one("strong")
            or card.select_one("span[class*='Price']")
        )
        price = self._parse_price(price_tag.get_text(strip=True) if price_tag else "0")
        if price <= 0:
            return None

        # Year from title or dedicated element
        year_tag = card.select_one("[class*='year']") or card.select_one("[class*='Year']")
        if year_tag:
            year_str = re.sub(r"\D", "", year_tag.get_text(strip=True))
            year = int(year_str) if year_str.isdigit() else 2020
        else:
            year = self._extract_year(title)

        # Mileage
        mileage_tag = card.select_one("[class*='mileage']") or card.select_one("[class*='km']")
        mileage = 0
        if mileage_tag:
            mileage = self._parse_mileage(mileage_tag.get_text(strip=True))
        else:
            # Search all text for km pattern
            for text in card.stripped_strings:
                if "km" in text.lower() and any(c.isdigit() for c in text):
                    mileage = self._parse_mileage(text)
                    if mileage > 0:
                        break

        # Fuel type
        fuel_type = "hybrid"
        for text in card.stripped_strings:
            text_lower = text.lower()
            if any(f in text_lower for f in ["hybr", "benzyna", "diesel", "elektryczny", "plug"]):
                fuel_type = self._normalize_fuel(text)
                break

        # Location
        location_tag = (
            card.select_one("[class*='dealer']")
            or card.select_one("[class*='location']")
            or card.select_one("[class*='city']")
        )
        location = location_tag.get_text(strip=True) if location_tag else "Polska"

        make, model = self._extract_make_model(title)

        return CarListingCreate(
            source=self.source_name,
            external_id=external_id,
            url=url,
            title=title or f"{make} {model} {year}",
            make=make,
            model=model,
            year=year,
            price_pln=price,
            mileage_km=mileage,
            fuel_type=fuel_type,
            transmission="automatic",
            body_type="suv",
            accident_history=False,  # Spoticar certified cars pass multi-point inspection
            seller_type="dealer",
            location=location,
            raw_data={"certified": "spoticar", "stellantis": True},
        )

    def _extract_year(self, text: str) -> int:
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else 2020

    def _extract_make_model(self, title: str) -> tuple[str, str]:
        # Spoticar brands: Peugeot, Citroën, Opel, DS, Fiat, Alfa Romeo, Jeep, Vauxhall
        known_makes = [
            "peugeot", "citroen", "citroën", "opel", "ds", "fiat",
            "alfa romeo", "jeep", "vauxhall", "lancia",
            "toyota", "kia", "hyundai", "ford", "mazda",
        ]
        title_lower = title.lower()
        for make in known_makes:
            if make in title_lower:
                # Normalize citroën
                canonical_make = make.replace("ë", "e").replace("é", "e")
                rest = title_lower.split(make, 1)[-1].strip()
                model_words = rest.split()[:3]
                model = " ".join(model_words).strip() or "unknown"
                return canonical_make, model
        words = title.split()
        if len(words) >= 2:
            return words[0].lower(), words[1].lower()
        return "unknown", "unknown"
