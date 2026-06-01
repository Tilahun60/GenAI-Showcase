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

        # Try __NEXT_DATA__ JSON first — Otomoto is a Next.js app
        next_data = self._extract_next_data(soup)
        if next_data:
            listings = self._parse_next_data(next_data)
            if listings:
                logger.debug("[otomoto] Parsed %d listings from __NEXT_DATA__", len(listings))
                return listings

        # HTML fallback
        articles = (
            soup.select("article[data-testid='listing-ad']")
            or soup.select("article[class*='ooa-']")
            or soup.select("article[class*='listing']")
            or soup.select("div[data-testid='listing-ad']")
        )
        if not articles:
            logger.debug("[otomoto] No articles found. Page snippet: %.400s", html)

        listings = []
        for article in articles:
            try:
                listing = self._parse_article(article)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                logger.debug("[otomoto] Skipping article: %s", exc)
        return listings

    def _parse_next_data(self, data: dict) -> list[CarListingCreate]:
        """Parse listings from Otomoto's __NEXT_DATA__ JSON (handles multiple schema versions)."""
        page_props = data.get("props", {}).get("pageProps", {})
        ads = self._find_ads_in_json(page_props)
        if not ads:
            return []
        # Unwrap GraphQL edges/node pattern
        if ads and isinstance(ads[0], dict) and "node" in ads[0]:
            ads = [item["node"] for item in ads if isinstance(item, dict) and "node" in item]
        listings = []
        for ad in ads:
            try:
                listing = self._parse_ad_dict(ad)
                if listing:
                    listings.append(listing)
            except Exception as exc:
                logger.debug("[otomoto] Skipping JSON ad: %s", exc)
        return listings

    def _parse_ad_dict(self, ad: dict) -> CarListingCreate | None:
        """Parse a single ad from Otomoto JSON data."""
        url = ad.get("url") or ad.get("href") or ad.get("seoPath") or ""
        if not url:
            return None
        if not url.startswith("http"):
            url = urljoin("https://www.otomoto.pl", url)

        external_id = self._extract_external_id(url) or str(ad.get("id", ""))
        if not external_id:
            return None

        title = ad.get("title") or ad.get("name") or ""

        # Price — multiple JSON shapes across Otomoto API versions
        price_info = ad.get("price") or {}
        price = 0.0
        if isinstance(price_info, dict):
            amount = price_info.get("amount") or {}
            if isinstance(amount, dict):
                price = float(amount.get("units") or amount.get("value") or 0)
            else:
                price = float(amount or 0)
            if price <= 0:
                price = self._parse_price(str(price_info.get("gross") or price_info.get("value") or ""))
        if price <= 0:
            price = self._parse_price(str(price_info))
        if price <= 0:
            return None

        params = ad.get("params") or ad.get("parameters") or []
        param_map: dict[str, str] = {}
        for p in params:
            if not isinstance(p, dict):
                continue
            key = (p.get("key") or "").lower()
            val = p.get("value") or {}
            label = val.get("label") or val.get("key") or "" if isinstance(val, dict) else str(val)
            if key and label:
                param_map[key] = str(label)

        year_str = param_map.get("year") or param_map.get("rok_produkcji") or ""
        year = int(re.sub(r"\D", "", year_str)) if re.search(r"\d{4}", year_str) else 2020

        mileage = self._parse_mileage(param_map.get("mileage") or param_map.get("przebieg") or "")
        fuel_raw = param_map.get("fuel_type") or param_map.get("paliwo") or ""
        fuel_type = self._normalize_fuel(fuel_raw) if fuel_raw else "hybrid"
        trans_raw = param_map.get("gearbox") or param_map.get("skrzynia_biegow") or ""
        transmission = self._normalize_transmission(trans_raw) if trans_raw else "automatic"
        body_raw = param_map.get("body_type") or param_map.get("typ_nadwozia") or ""
        body_type = self._normalize_body(body_raw) if body_raw else "suv"

        location_info = ad.get("location") or {}
        if isinstance(location_info, dict):
            city = location_info.get("city") or location_info.get("cityName") or {}
            location = city.get("name") if isinstance(city, dict) else str(city)
        else:
            location = str(location_info)

        is_dealer = ad.get("isBusinessSeller") or ad.get("isBusiness") or False
        seller_type = "dealer" if is_dealer else "private"
        make, model = self._extract_make_model(title)

        return CarListingCreate(
            source=self.source_name,
            external_id=external_id,
            url=url,
            title=title or f"{make} {model} {year}",
            make=make, model=model, year=year,
            price_pln=price, mileage_km=mileage,
            fuel_type=fuel_type, transmission=transmission, body_type=body_type,
            accident_history=None, seller_type=seller_type, location=location or "",
            raw_data={"source_page": SEARCH_URL},
        )

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
