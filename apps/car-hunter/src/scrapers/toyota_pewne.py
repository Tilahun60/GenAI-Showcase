"""Toyota Pewne Auto scraper — Toyota certified used cars in Poland."""

from __future__ import annotations

import json
import logging

from bs4 import BeautifulSoup

from ..models.schemas import CarListingCreate
from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://pewneauto.toyota.pl/samochody"

PARAMS = {
    "nadwozie": "SUV",
    "paliwo": "hybryda",
    "skrzynia": "automatyczna",
    "cena_do": "60000",
    "rok_od": "2020",
    "przebieg_do": "150000",
}


class ToyotaPewneScraper(BaseScraper):
    source_name = "toyota_pewne"

    async def scrape(self) -> list[CarListingCreate]:
        listings: list[CarListingCreate] = []
        page = 1
        async with self:
            while True:
                params = {**PARAMS, "strona": str(page)}
                html = await self._fetch_page(SEARCH_URL, params=params)
                if not html:
                    break
                page_listings, has_next = self._parse_page(html)
                listings.extend(page_listings)
                logger.info("Toyota Pewne page %d: %d listings", page, len(page_listings))
                if not has_next or page >= 10:
                    break
                page += 1
        return listings

    def _parse_page(self, html: str) -> tuple[list[CarListingCreate], bool]:
        soup = BeautifulSoup(html, "lxml")
        results = []

        for card in soup.select(".car-tile, .vehicle-card, .offer-item, [class*='car-offer']"):
            try:
                link = card.select_one("a[href]")
                url = link["href"] if link else ""
                if url and not url.startswith("http"):
                    url = f"https://pewneauto.toyota.pl{url}"

                title_tag = card.select_one("h2, h3, .car-name, .vehicle-name, [class*='title']")
                title = self._clean_str(title_tag.get_text() if title_tag else "")

                price_tag = card.select_one(".price, .car-price, [class*='price']")
                price = self._parse_price(price_tag.get_text() if price_tag else "0")

                year_mileage = card.select_one(".params, .details, [class*='params']")
                text = year_mileage.get_text() if year_mileage else ""
                year = self._parse_year(text)
                mileage = self._parse_mileage(text)

                parts = title.split()
                make = "Toyota"
                model_name = " ".join(parts[1:3]) if len(parts) > 1 else title

                results.append(CarListingCreate(
                    source=self.source_name,
                    external_id=self._slugify_to_id(url),
                    url=url, title=title, make=make, model=model_name,
                    year=year, price_pln=price, mileage_km=mileage,
                    fuel_type="hybrid", transmission="automatic", body_type="suv",
                    seller_type="dealer", location="",
                    raw_data={"raw_text": text},
                ))
            except Exception as exc:
                logger.debug("Toyota Pewne parse error: %s", exc)

        has_next = bool(
            soup.select_one("a[rel='next'], .pagination .next, [aria-label='Następna strona']")
        )
        return results, has_next
