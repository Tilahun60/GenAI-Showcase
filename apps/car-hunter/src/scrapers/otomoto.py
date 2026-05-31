"""Scraper for Otomoto.pl - Poland's largest car marketplace."""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..models.schemas import CarListingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.otomoto.pl/osobowe/uzywane"

# Otomoto uses a GraphQL-like JSON embedded in a <script> tag named __NEXT_DATA__
# We parse it for reliable data extraction.


class OtomotoScraper(BaseScraper):
    """Scrapes hybrid SUV listings from Otomoto.pl."""

    source_name = "otomoto"
    base_url = SEARCH_URL

    # Otomoto query params for filtering
    DEFAULT_PARAMS = {
        "search[filter_enum_fuel_type][]": "hybrid",
        "search[filter_enum_gearbox][]": "automatic",
        "search[category_id]": "29",  # SUV/Crossover category
        "search[order]": "created_at_first:desc",
    }

    async def scrape(self) -> list[CarListingCreate]:
        """Scrape listings from multiple pages of Otomoto search results."""
        listings: list[CarListingCreate] = []
        page = 1
        max_pages = 10

        async with self:
            while page <= max_pages:
                params = {**self.DEFAULT_PARAMS, "page": str(page)}
                try:
                    html = await self._fetch_page(SEARCH_URL, params=params)
                    page_listings = self._parse_search_page(html)
                    if not page_listings:
                        logger.info("[otomoto] No more listings at page %d", page)
                        break
                    listings.extend(page_listings)
                    logger.info("[otomoto] Page %d: found %d listings", page, len(page_listings))
                    page += 1
                except Exception as exc:
                    logger.error("[otomoto] Error fetching page %d: %s", page, exc)
                    break

        logger.info("[otomoto] Total scraped: %d listings", len(listings))
        return listings

    def _parse_search_page(self, html: str) -> list[CarListingCreate]:
        """Parse a search results page and return listings."""
        soup = BeautifulSoup(html, "lxml")
        listings: list[CarListingCreate] = []

        # Otomoto renders listing cards with data-testid="listing-ad"
        # or article tags with specific class patterns
        articles = soup.select("article[data-testid='listing-ad']")
        if not articles:
            # Fallback: look for any article with a link and price
            articles = soup.select("article.ooa-yca59n") or soup.select("article[class*='listing']")

        for article in articles:
            try:
                listing = self._parse_article(article)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                logger.debug("[otomoto] Skipping article due to error: %s", exc)

        return listings

    def _parse_article(self, article) -> CarListingCreate | None:
        """Parse a single listing article element."""
        # Extract URL and external ID
        link_tag = article.select_one("a[href*='otomoto.pl']") or article.select_one("a[href]")
        if not link_tag:
            return None

        url = link_tag.get("href", "")
        if not url.startswith("http"):
            url = urljoin("https://www.otomoto.pl", url)

        # External ID from URL slug (last path segment)
        external_id = self._extract_external_id(url)
        if not external_id:
            return None

        # Title
        title_tag = (
            article.select_one("h2[data-testid='ad-title']")
            or article.select_one("h2")
            or article.select_one("[class*='Title']")
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Price
        price_tag = (
            article.select_one("[data-testid='ad-price']")
            or article.select_one("[class*='Price']")
            or article.select_one("span[class*='price']")
        )
        price_raw = price_tag.get_text(strip=True) if price_tag else "0"
        price = self._parse_price(price_raw)

        if price <= 0:
            return None

        # Parameters list (year, mileage, fuel, transmission, etc.)
        params_container = (
            article.select_one("[data-testid='listing-params']")
            or article.select_one("dl")
            or article.select_one("[class*='params']")
        )

        year = 0
        mileage = 0
        fuel_type = "hybrid"
        transmission = "automatic"
        body_type = "suv"

        if params_container:
            # Try dl/dd pattern
            dds = params_container.select("dd")
            dts = params_container.select("dt")
            param_map: dict[str, str] = {}
            for dt, dd in zip(dts, dds, strict=False):
                param_map[dt.get_text(strip=True).lower()] = dd.get_text(strip=True)

            year_str = param_map.get("rok produkcji") or param_map.get("year") or ""
            year = int(year_str) if year_str.isdigit() else 0

            mileage_raw = param_map.get("przebieg") or param_map.get("mileage") or ""
            mileage = self._parse_mileage(mileage_raw)

            fuel_raw = param_map.get("paliwo") or param_map.get("fuel type") or ""
            fuel_type = self._normalize_fuel(fuel_raw) if fuel_raw else "hybrid"

            trans_raw = param_map.get("skrzynia biegów") or param_map.get("gearbox") or ""
            transmission = self._normalize_transmission(trans_raw) if trans_raw else "automatic"

            body_raw = param_map.get("typ nadwozia") or param_map.get("body type") or ""
            body_type = self._normalize_body(body_raw) if body_raw else "suv"

        # Fallback year extraction from title
        if not year:
            year_match = re.search(r"\b(20\d{2})\b", title)
            year = int(year_match.group(1)) if year_match else 2020

        # Make and model from title
        make, model = self._extract_make_model(title)

        # Location
        location_tag = (
            article.select_one("[data-testid='location-date']")
            or article.select_one("[class*='location']")
            or article.select_one("[class*='Location']")
        )
        location = location_tag.get_text(strip=True).split("-")[0].strip() if location_tag else ""

        # Seller type: otomoto shows "Dealer" or "Prywatny"
        seller_tag = article.select_one("[class*='seller']") or article.select_one("[class*='Seller']")
        seller_raw = seller_tag.get_text(strip=True) if seller_tag else ""
        seller_type = self._normalize_seller(seller_raw)

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
            body_type=body_type,
            accident_history=None,
            seller_type=seller_type,
            location=location,
            raw_data={"source_page": SEARCH_URL},
        )

    def _extract_external_id(self, url: str) -> str:
        """Extract unique listing ID from Otomoto URL."""
        # Otomoto URLs look like: /osobowe/oferta/toyota-c-hr-hybr-ID123456789.html
        # or https://www.otomoto.pl/osobowe/oferta/ford-kuga-ID987654321.html
        path = urlparse(url).path
        # Otomoto IDs are alphanumeric (e.g. ID6GpXaB), so match word chars after "ID"
        id_match = re.search(r"ID([A-Za-z0-9]+)", path)
        if id_match:
            return id_match.group(1)
        # Fallback: use last path segment without extension
        segment = path.rstrip("/").split("/")[-1]
        return segment.replace(".html", "") or ""

    def _extract_make_model(self, title: str) -> tuple[str, str]:
        """Attempt to extract make and model from the listing title."""
        known_makes = [
            "toyota", "kia", "hyundai", "ford", "mazda", "honda",
            "renault", "peugeot", "mitsubishi", "volkswagen", "skoda",
            "seat", "audi", "bmw", "mercedes", "volvo", "nissan",
            "suzuki", "dacia", "opel", "citroen",
        ]
        title_lower = title.lower()
        for make in known_makes:
            if make in title_lower:
                # Extract model as the next word(s) after make
                pattern = rf"{make}\s+([\w\s\-]+?)(?:\s+\d{{4}}|$)"
                match = re.search(pattern, title_lower)
                if match:
                    model_raw = match.group(1).strip()
                    # Limit to 3 words for model
                    model = " ".join(model_raw.split()[:3])
                    return make, model
                return make, "unknown"
        # Could not identify make
        words = title.split()
        if len(words) >= 2:
            return words[0].lower(), words[1].lower()
        return "unknown", "unknown"
