"""Das WeltAuto Polska scraper — VW Group certified used cars."""

from __future__ import annotations

import logging

from bs4 import BeautifulSoup

from ..models.schemas import CarListingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.dasweltauto.pl/samochody-uzywane"

PARAMS = {
    "bodyType": "SUV",
    "fuel": "hybrid",
    "gearbox": "automatic",
    "priceMax": "60000",
    "yearMin": "2020",
    "mileageMax": "150000",
    "page": "1",
}


class DasWeltAutoScraper(BaseScraper):
    source_name = "das_weltauto"

    async def scrape(self) -> list[CarListingCreate]:
        listings: list[CarListingCreate] = []
        page = 1
        async with self:
            while True:
                params = {**PARAMS, "page": str(page)}
                html = await self._fetch_page(SEARCH_URL, params=params)
                if not html:
                    break
                page_listings, has_next = self._parse_page(html)
                listings.extend(page_listings)
                logger.info("DasWeltAuto page %d: %d listings", page, len(page_listings))
                if not has_next or page >= 10:
                    break
                page += 1
        return listings

    def _parse_page(self, html: str) -> tuple[list[CarListingCreate], bool]:
        soup = BeautifulSoup(html, "lxml")
        results = []

        for card in soup.select(".vehicle-item, .car-item, article.offer, [class*='vehicle-card']"):
            try:
                link = card.select_one("a[href]")
                url = link["href"] if link else ""
                if url and not url.startswith("http"):
                    url = f"https://www.dasweltauto.pl{url}"

                title_tag = card.select_one("h2, h3, .vehicle-name, .model-name")
                title = self._clean_str(title_tag.get_text() if title_tag else "")

                price_tag = card.select_one(".price, [class*='price']")
                price = self._parse_price(price_tag.get_text() if price_tag else "0")

                # DWA typically shows year and mileage in spec list
                specs = card.select("dd, .spec-value, [class*='spec']")
                spec_text = " ".join(s.get_text() for s in specs)
                year = self._parse_year(spec_text)
                mileage = self._parse_mileage(spec_text)

                parts = title.split()
                make = parts[0] if parts else ""
                model_name = " ".join(parts[1:3]) if len(parts) > 1 else ""

                fuel_tag = card.select_one("[class*='fuel'], [data-fuel]")
                fuel_raw = self._clean_str(fuel_tag.get_text() if fuel_tag else "hybrid")

                results.append(CarListingCreate(
                    source=self.source_name,
                    external_id=self._slugify_to_id(url),
                    url=url, title=title, make=make, model=model_name,
                    year=year, price_pln=price, mileage_km=mileage,
                    fuel_type=fuel_raw, transmission="automatic", body_type="suv",
                    seller_type="dealer", location="",
                    raw_data={"spec_text": spec_text},
                ))
            except Exception as exc:
                logger.debug("DasWeltAuto parse error: %s", exc)

        has_next = bool(soup.select_one("a[rel='next'], .pager__next, .pagination__next"))
        return results, has_next
