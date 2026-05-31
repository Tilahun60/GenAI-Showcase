"""Scraper for OLX.pl Auto section."""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..models.schemas import CarListingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.olx.pl/motoryzacja/samochody/"


class OLXScraper(BaseScraper):
    """Scrapes hybrid SUV listings from OLX.pl."""

    source_name = "olx"
    base_url = SEARCH_URL

    DEFAULT_PARAMS = {
        "search[filter_enum_fuel_type][0]": "hybrid",
        "search[filter_enum_transmission][0]": "automatic",
        "search[order]": "created_at:desc",
        "currency": "PLN",
    }

    async def scrape(self) -> list[CarListingCreate]:
        """Scrape listings from OLX search results."""
        listings: list[CarListingCreate] = []
        page = 1
        max_pages = 10

        async with self:
            while page <= max_pages:
                params = {**self.DEFAULT_PARAMS, "page": str(page)}
                try:
                    html = await self._fetch_page(SEARCH_URL, params=params)
                    page_listings = self._parse_page(html)
                    if not page_listings:
                        logger.info("[olx] No more listings at page %d", page)
                        break
                    listings.extend(page_listings)
                    logger.info("[olx] Page %d: found %d listings", page, len(page_listings))
                    page += 1
                except Exception as exc:
                    logger.error("[olx] Error fetching page %d: %s", page, exc)
                    break

        logger.info("[olx] Total scraped: %d listings", len(listings))
        return listings

    def _parse_page(self, html: str) -> list[CarListingCreate]:
        """Parse OLX search results page."""
        soup = BeautifulSoup(html, "lxml")
        listings: list[CarListingCreate] = []

        # OLX injects listing data into a __NEXT_DATA__ JSON script tag
        next_data = self._extract_next_data(soup)
        if next_data:
            return self._parse_next_data(next_data)

        # Fallback: HTML parsing
        # OLX listing items: div[data-testid="listing-grid"] > div[data-testid="l-card"]
        cards = soup.select("[data-testid='l-card']")
        if not cards:
            cards = soup.select("div.css-1sw7q4x") or soup.select("li[class*='offer']")

        for card in cards:
            try:
                listing = self._parse_card(card)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                logger.debug("[olx] Skipping card: %s", exc)

        return listings

    def _extract_next_data(self, soup: BeautifulSoup) -> dict | None:
        """Extract the __NEXT_DATA__ JSON blob from a Next.js page."""
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script or not script.string:
            return None
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            return None

    def _parse_next_data(self, data: dict) -> list[CarListingCreate]:
        """Parse listings from OLX's __NEXT_DATA__ JSON structure."""
        listings: list[CarListingCreate] = []
        try:
            # Navigate the Next.js data tree
            props = data.get("props", {})
            page_props = props.get("pageProps", {})
            # OLX stores ads under different keys depending on version
            ads = (
                page_props.get("ads")
                or page_props.get("listing", {}).get("ads")
                or []
            )
            for ad in ads:
                try:
                    listing = self._parse_ad_dict(ad)
                    if listing:
                        listings.append(listing)
                except Exception as exc:
                    logger.debug("[olx] Skipping ad: %s", exc)
        except Exception as exc:
            logger.debug("[olx] Could not parse __NEXT_DATA__: %s", exc)
        return listings

    def _parse_ad_dict(self, ad: dict) -> CarListingCreate | None:
        """Parse a single ad from OLX JSON data."""
        url = ad.get("url") or ad.get("href") or ""
        if not url:
            return None
        if not url.startswith("http"):
            url = urljoin("https://www.olx.pl", url)

        external_id = str(ad.get("id") or self._extract_id_from_url(url))
        if not external_id:
            return None

        title = ad.get("title") or ad.get("name") or ""
        price_info = ad.get("price") or {}
        price = float(price_info.get("value") or price_info.get("amount") or 0)

        if price <= 0:
            # Try raw price string
            price = self._parse_price(str(price_info))

        # Parameters from the params list
        params = ad.get("params") or []
        param_map: dict[str, str] = {}
        for p in params:
            key = (p.get("key") or "").lower()
            val = p.get("value") or {}
            label = val.get("label") or val.get("key") or "" if isinstance(val, dict) else str(val)
            if key and label:
                param_map[key] = str(label)

        year_str = param_map.get("year") or param_map.get("model_year") or ""
        year = int(re.sub(r"\D", "", year_str)) if year_str else 2020

        mileage_raw = param_map.get("mileage") or param_map.get("milage") or ""
        mileage = self._parse_mileage(mileage_raw)

        fuel_raw = param_map.get("fuel_type") or param_map.get("petrol_type") or ""
        fuel_type = self._normalize_fuel(fuel_raw) if fuel_raw else "hybrid"

        trans_raw = param_map.get("transmission") or param_map.get("gearbox") or ""
        transmission = self._normalize_transmission(trans_raw) if trans_raw else "automatic"

        body_raw = param_map.get("body_type") or param_map.get("car_type") or ""
        body_type = self._normalize_body(body_raw) if body_raw else "suv"

        location_info = ad.get("location") or {}
        if isinstance(location_info, dict):
            city = location_info.get("city", {})
            city_name = city.get("name") if isinstance(city, dict) else str(city)
            location = city_name or ""
        else:
            location = str(location_info)

        is_business = ad.get("isBusiness") or ad.get("is_business") or False
        seller_type = "dealer" if is_business else "private"

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
            body_type=body_type,
            accident_history=None,
            seller_type=seller_type,
            location=location,
            raw_data={"source_url": SEARCH_URL},
        )

    def _parse_card(self, card) -> CarListingCreate | None:
        """Fallback HTML parsing for a single OLX listing card."""
        link = card.select_one("a[href]")
        if not link:
            return None

        url = link.get("href", "")
        if not url.startswith("http"):
            url = urljoin("https://www.olx.pl", url)

        external_id = self._extract_id_from_url(url)
        if not external_id:
            return None

        title_tag = card.select_one("h6") or card.select_one("[class*='title']")
        title = title_tag.get_text(strip=True) if title_tag else ""

        price_tag = card.select_one("[data-testid='ad-price']") or card.select_one("[class*='price']")
        price = self._parse_price(price_tag.get_text(strip=True) if price_tag else "0")

        if price <= 0:
            return None

        year_match = re.search(r"\b(20\d{2})\b", title)
        year = int(year_match.group(1)) if year_match else 2020

        location_tag = card.select_one("[data-testid='location-date']") or card.select_one("[class*='location']")
        location = location_tag.get_text(strip=True).split("-")[0].strip() if location_tag else ""

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
            mileage_km=0,
            fuel_type="hybrid",
            transmission="automatic",
            body_type="suv",
            accident_history=None,
            seller_type="private",
            location=location,
            raw_data={},
        )

    def _extract_id_from_url(self, url: str) -> str:
        """Extract listing ID from OLX URL like /d/oferta/toyota-chr-ID12345.html"""
        path = urlparse(url).path
        id_match = re.search(r"ID(\w+)", path)
        if id_match:
            return id_match.group(1)
        # Try last numeric segment
        num_match = re.search(r"(\d{5,})", path)
        if num_match:
            return num_match.group(1)
        return path.rstrip("/").split("/")[-1].replace(".html", "")

    def _extract_make_model(self, title: str) -> tuple[str, str]:
        """Extract make and model from listing title."""
        known_makes = [
            "toyota", "kia", "hyundai", "ford", "mazda", "honda",
            "renault", "peugeot", "mitsubishi", "volkswagen", "skoda",
            "seat", "audi", "bmw", "mercedes", "volvo", "nissan",
            "suzuki", "dacia", "opel", "citroen",
        ]
        title_lower = title.lower()
        for make in known_makes:
            if make in title_lower:
                pattern = rf"{make}\s+([\w\s\-]+?)(?:\s+\d{{4}}|$)"
                match = re.search(pattern, title_lower)
                if match:
                    model = " ".join(match.group(1).strip().split()[:3])
                    return make, model
                return make, "unknown"
        words = title.split()
        if len(words) >= 2:
            return words[0].lower(), words[1].lower()
        return "unknown", "unknown"
