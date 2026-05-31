"""Scraper for AAA Auto Polska - certified used car dealer network."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models.schemas import CarListingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE_URL = "https://www.aaaauto.pl"
SEARCH_URL = f"{BASE_URL}/pl/cars.php"


class AAAAutoScraper(BaseScraper):
    """Scrapes listings from AAA Auto Poland (dealer-only, certified used cars)."""

    source_name = "aaa_auto"
    base_url = SEARCH_URL

    DEFAULT_PARAMS = {
        "fuel": "hybrid",
        "gearbox": "2",  # 2 = automatic on AAA Auto
        "category": "SUV",
        "sort": "date_desc",
        "limit": "20",
    }

    async def scrape(self) -> list[CarListingCreate]:
        """Scrape hybrid SUV listings from AAA Auto."""
        listings: list[CarListingCreate] = []
        page = 1
        max_pages = 8

        async with self:
            while page <= max_pages:
                params = {**self.DEFAULT_PARAMS, "page": str(page)}
                try:
                    html = await self._fetch_page(SEARCH_URL, params=params)
                    page_listings = self._parse_page(html)
                    if not page_listings:
                        logger.info("[aaa_auto] No more listings at page %d", page)
                        break
                    listings.extend(page_listings)
                    logger.info("[aaa_auto] Page %d: found %d listings", page, len(page_listings))
                    page += 1
                except Exception as exc:
                    logger.error("[aaa_auto] Error fetching page %d: %s", page, exc)
                    break

        logger.info("[aaa_auto] Total scraped: %d listings", len(listings))
        return listings

    def _parse_page(self, html: str) -> list[CarListingCreate]:
        """Parse AAA Auto search results page."""
        soup = BeautifulSoup(html, "lxml")
        listings: list[CarListingCreate] = []

        # AAA Auto uses article or div cards for each listing
        cards = (
            soup.select("article.offer-item")
            or soup.select("div.car-offer")
            or soup.select("div[class*='car-item']")
            or soup.select("div[class*='offer']")
        )

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                logger.debug("[aaa_auto] Skipping card: %s", exc)

        return listings

    def _parse_card(self, card) -> CarListingCreate | None:
        """Parse a single AAA Auto listing card."""
        link = card.select_one("a[href]")
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = urljoin(BASE_URL, url)

        # Extract external ID from URL
        id_match = re.search(r"[?&]id=(\d+)", url) or re.search(r"/(\d+)(?:\.html)?$", url)
        external_id = id_match.group(1) if id_match else url.split("/")[-1].replace(".html", "")
        if not external_id:
            return None

        # Title: usually "Make Model Year"
        title_tag = (
            card.select_one("h2.offer-title")
            or card.select_one("h2")
            or card.select_one("[class*='title']")
            or link
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Price
        price_tag = (
            card.select_one("span.price")
            or card.select_one("[class*='price']")
            or card.select_one("strong.offer-price")
        )
        price = self._parse_price(price_tag.get_text(strip=True) if price_tag else "0")
        if price <= 0:
            return None

        # Parameters: year, mileage, etc.
        # AAA Auto typically shows these as list items or spans
        params_list = card.select("li") or card.select("span[class*='param']")
        param_texts = [p.get_text(strip=True) for p in params_list]
        param_text = " | ".join(param_texts)

        year = self._extract_year(title + " " + param_text)
        mileage = self._extract_mileage_from_params(params_list)

        # Fuel type
        fuel_type = "hybrid"  # Filter is applied in query params
        for text in param_texts:
            if any(f in text.lower() for f in ["hybr", "benzyna", "diesel", "elektryczny"]):
                fuel_type = self._normalize_fuel(text)
                break

        # Transmission
        transmission = "automatic"
        for text in param_texts:
            if any(t in text.lower() for t in ["automat", "manual", "mechan"]):
                transmission = self._normalize_transmission(text)
                break

        # Location (branch)
        location_tag = card.select_one("[class*='location']") or card.select_one("[class*='branch']")
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
            transmission=transmission,
            body_type="suv",
            accident_history=None,  # AAA claims all cars inspected
            seller_type="dealer",  # AAA Auto is always dealer
            location=location,
            raw_data={"source": "aaa_auto", "certified": True},
        )

    def _extract_year(self, text: str) -> int:
        """Extract year from text."""
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else 2020

    def _extract_mileage_from_params(self, params) -> int:
        """Find mileage among list of param elements."""
        for p in params:
            text = p.get_text(strip=True)
            if "km" in text.lower():
                return self._parse_mileage(text)
        return 0

    def _extract_make_model(self, title: str) -> tuple[str, str]:
        """Extract make and model from title."""
        known_makes = [
            "toyota", "kia", "hyundai", "ford", "mazda", "honda",
            "renault", "peugeot", "mitsubishi", "volkswagen", "skoda",
            "seat", "audi", "bmw", "mercedes", "volvo", "nissan",
            "suzuki", "dacia", "opel", "citroen",
        ]
        title_lower = title.lower()
        for make in known_makes:
            if make in title_lower:
                pattern = rf"{make}\s+([\w\s\-]+?)(?:\s+\d{{4}}|\s+\d{{3}}\s*\d{{3}}|$)"
                match = re.search(pattern, title_lower)
                if match:
                    model = " ".join(match.group(1).strip().split()[:3])
                    return make, model
                return make, "unknown"
        words = title.split()
        if len(words) >= 2:
            return words[0].lower(), words[1].lower()
        return "unknown", "unknown"
