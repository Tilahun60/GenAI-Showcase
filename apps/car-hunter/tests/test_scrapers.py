"""Tests for scraper parsing logic against static fixtures (no network)."""
from __future__ import annotations

import json

from src.scrapers.olx import OLXScraper
from src.scrapers.otomoto import OtomotoScraper

OTOMOTO_HTML = """
<html><body>
<article data-testid="listing-ad">
  <a href="https://www.otomoto.pl/osobowe/oferta/toyota-c-hr-hybrid-ID6GpXaB.html">link</a>
  <h2 data-testid="ad-title">Toyota C-HR 2.0 Hybrid 2021</h2>
  <span data-testid="ad-price">58 900 PLN</span>
  <dl data-testid="listing-params">
    <dt>Rok produkcji</dt><dd>2021</dd>
    <dt>Przebieg</dt><dd>112 000 km</dd>
    <dt>Paliwo</dt><dd>Hybryda</dd>
    <dt>Skrzynia biegów</dt><dd>Automatyczna</dd>
  </dl>
</article>
</body></html>
"""


def test_otomoto_parses_listing():
    scraper = OtomotoScraper()
    listings = scraper._parse_search_page(OTOMOTO_HTML)
    assert len(listings) == 1
    car = listings[0]
    assert car.make == "toyota"
    assert car.year == 2021
    assert car.price_pln == 58_900
    assert car.mileage_km == 112_000
    assert car.fuel_type == "hybrid"
    assert car.transmission == "automatic"


def test_otomoto_extracts_alphanumeric_id():
    scraper = OtomotoScraper()
    url = "https://www.otomoto.pl/osobowe/oferta/toyota-c-hr-ID6GpXaB.html"
    # Full alphanumeric ID, not truncated at the first non-digit
    assert scraper._extract_external_id(url) == "6GpXaB"


def test_otomoto_extracts_numeric_id():
    scraper = OtomotoScraper()
    url = "https://www.otomoto.pl/osobowe/oferta/ford-kuga-ID987654321.html"
    assert scraper._extract_external_id(url) == "987654321"


def test_otomoto_skips_zero_price():
    scraper = OtomotoScraper()
    html = OTOMOTO_HTML.replace("58 900 PLN", "0 PLN")
    assert scraper._parse_search_page(html) == []


def test_price_parser_handles_polish_formatting():
    scraper = OtomotoScraper()
    assert scraper._parse_price("58 900 zł") == 58_900
    assert scraper._parse_price("112\xa0000 PLN") == 112_000


def test_mileage_parser():
    scraper = OtomotoScraper()
    assert scraper._parse_mileage("112 000 km") == 112_000
    assert scraper._parse_mileage("") == 0


def test_normalize_fuel():
    scraper = OtomotoScraper()
    assert scraper._normalize_fuel("Hybryda") == "hybrid"
    assert scraper._normalize_fuel("Benzyna") == "petrol"
    assert scraper._normalize_fuel("Diesel") == "diesel"
    assert scraper._normalize_fuel("Elektryczny") == "electric"


def test_normalize_transmission():
    scraper = OtomotoScraper()
    assert scraper._normalize_transmission("Automatyczna") == "automatic"
    assert scraper._normalize_transmission("Manualna") == "manual"


def test_olx_parses_next_data_json():
    scraper = OLXScraper()
    next_data = {
        "props": {
            "pageProps": {
                "ads": [
                    {
                        "id": 12345,
                        "url": "https://www.olx.pl/d/oferta/kia-niro-ID12345.html",
                        "title": "Kia Niro Hybrid 2022",
                        "price": {"value": 72000},
                        "params": [
                            {"key": "year", "value": {"label": "2022"}},
                            {"key": "mileage", "value": {"label": "45 000 km"}},
                            {"key": "fuel_type", "value": {"label": "Hybryda"}},
                            {"key": "transmission", "value": {"label": "Automatyczna"}},
                        ],
                        "location": {"city": {"name": "Gdańsk"}},
                        "isBusiness": True,
                    }
                ]
            }
        }
    }
    listings = scraper._parse_next_data(next_data)
    assert len(listings) == 1
    car = listings[0]
    assert car.make == "kia"
    assert car.year == 2022
    assert car.price_pln == 72_000
    assert car.mileage_km == 45_000
    assert car.seller_type == "dealer"
    assert car.location == "Gdańsk"


def test_olx_private_seller_when_not_business():
    scraper = OLXScraper()
    next_data = {
        "props": {"pageProps": {"ads": [{
            "id": 999,
            "url": "https://www.olx.pl/d/oferta/x-ID999.html",
            "title": "Toyota RAV4 2020",
            "price": {"value": 80000},
            "params": [],
            "isBusiness": False,
        }]}}
    }
    listings = scraper._parse_next_data(next_data)
    assert listings[0].seller_type == "private"


def test_olx_extract_id_from_url():
    scraper = OLXScraper()
    assert scraper._extract_id_from_url("https://www.olx.pl/d/oferta/kia-niro-ID12abc.html") == "12abc"


def test_olx_roundtrip_via_json_string():
    # Ensure the JSON structure survives a serialize/parse roundtrip
    scraper = OLXScraper()
    payload = {"props": {"pageProps": {"ads": [{
        "id": 1, "url": "https://www.olx.pl/d/oferta/x-ID1.html",
        "title": "Hyundai Kona 2021", "price": {"value": 65000}, "params": [],
    }]}}}
    data = json.loads(json.dumps(payload))
    assert len(scraper._parse_next_data(data)) == 1
