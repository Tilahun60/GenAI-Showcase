"""Abstract base scraper with shared HTTP and parsing utilities."""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..models.schemas import CarListingCreate

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

RETRYABLE_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)

# GDPR/cookie consent button selectors common on Polish sites
_CONSENT_SELECTORS = [
    "button#onetrust-accept-btn-handler",
    "[data-testid='cookie-accept-all']",
    "[data-testid='accept-consent']",
    "#accept-cookies",
    "button.cookie-accept",
    "button:text('Akceptuję wszystkie')",
    "button:text('Akceptuję')",
    "button:text('Zgadzam się')",
    "button:text('Zaakceptuj')",
    "button:text('Accept all')",
    "button:text('Accept All')",
]


class ScraperError(Exception):
    """Raised when a scraper encounters a non-retryable error."""


class BaseScraper(ABC):
    """Abstract base class for all car listing scrapers."""

    source_name: str = "unknown"
    base_url: str = ""
    use_browser: bool = False  # subclasses set True to use Playwright instead of httpx

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._pw: Any = None
        self._browser: Any = None
        self._browser_context: Any = None

    async def __aenter__(self) -> BaseScraper:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers=self._default_headers(),
            follow_redirects=True,
        )
        if self.use_browser:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            self._browser_context = await self._browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                locale="pl-PL",
                viewport={"width": 1920, "height": 1080},
                extra_http_headers={"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8"},
            )
            logger.debug("[%s] Playwright browser ready", self.source_name)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._browser_context:
            await self._browser_context.close()
            self._browser_context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None

    def _default_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    async def _fetch_page(self, url: str, params: dict | None = None) -> str:
        """Fetch URL — Playwright if use_browser=True, else httpx with retries."""
        if self.use_browser:
            return await self._fetch_page_browser(url, params)
        return await self._fetch_page_http(url, params)

    @retry(
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _fetch_page_http(self, url: str, params: dict | None = None) -> str:
        """Fetch URL with httpx and tenacity retries."""
        if self._client is None:
            raise RuntimeError("Scraper must be used as async context manager")
        self._client.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (429, 503):
                logger.warning("[%s] Rate-limited (%s) for %s", self.source_name, status, url)
                raise httpx.NetworkError(f"Rate limit: {status}") from exc
            logger.error("[%s] HTTP %s for %s", self.source_name, status, url)
            raise
        response.raise_for_status()
        return response.text

    async def _fetch_page_browser(self, url: str, params: dict | None = None) -> str:
        """Fetch URL using Playwright (real browser — handles JS, GDPR banners, bot detection)."""
        from urllib.parse import urlencode

        if params:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(params)}"

        if self._browser_context is None:
            raise RuntimeError("Browser not started — use scraper as async context manager")

        page = await self._browser_context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Dismiss GDPR / cookie consent banners
            for sel in _CONSENT_SELECTORS:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=600):
                        await btn.click()
                        await page.wait_for_timeout(400)
                        break
                except Exception:  # noqa: BLE001
                    pass

            await page.wait_for_timeout(2000)
            return await page.content()
        finally:
            await page.close()

    async def _fetch_json(self, url: str, params: dict | None = None) -> Any:
        """Fetch a URL and return parsed JSON."""
        if self._client is None:
            raise RuntimeError("Scraper must be used as async context manager")
        self._client.headers["User-Agent"] = random.choice(USER_AGENTS)
        self._client.headers["Accept"] = "application/json"
        response = await self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    @abstractmethod
    async def scrape(self) -> list[CarListingCreate]:
        """Scrape listings and return them as CarListingCreate objects."""

    # ------------------------------------------------------------------
    # Shared parsing helpers
    # ------------------------------------------------------------------

    def _parse_price(self, raw: str) -> float:
        """Extract numeric price from a string like '45 900 zł' or '45900 PLN'."""
        if not raw:
            return 0.0
        cleaned = re.sub(r"[^\d,.]", "", raw.replace("\xa0", "").replace(" ", ""))
        cleaned = cleaned.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            logger.debug("Could not parse price: %r", raw)
            return 0.0

    def _parse_mileage(self, raw: str) -> int:
        """Extract mileage in km from a string like '87 500 km'."""
        if not raw:
            return 0
        digits = re.sub(r"[^\d]", "", raw)
        try:
            return int(digits)
        except ValueError:
            logger.debug("Could not parse mileage: %r", raw)
            return 0

    def _normalize_fuel(self, raw: str) -> str:
        raw_lower = (raw or "").lower()
        if "hybr" in raw_lower:
            return "hybrid"
        if "elekt" in raw_lower or "bev" in raw_lower:
            return "electric"
        if "diesel" in raw_lower or "olej" in raw_lower:
            return "diesel"
        if "benzyn" in raw_lower or "petrol" in raw_lower or "gasoline" in raw_lower:
            return "petrol"
        return raw_lower or "unknown"

    def _normalize_transmission(self, raw: str) -> str:
        raw_lower = (raw or "").lower()
        if "automat" in raw_lower or "automatic" in raw_lower or raw_lower == "at":
            return "automatic"
        if "manual" in raw_lower or "mechan" in raw_lower or raw_lower == "mt":
            return "manual"
        return raw_lower or "unknown"

    def _normalize_body(self, raw: str) -> str:
        raw_lower = (raw or "").lower()
        mapping = {
            "suv": "suv", "sedan": "sedan", "hatchback": "hatchback",
            "kombi": "estate", "estate": "estate", "coupe": "coupe",
            "kabriolet": "convertible", "convertible": "convertible",
            "van": "van", "minivan": "van",
        }
        for key, value in mapping.items():
            if key in raw_lower:
                return value
        return raw_lower or "unknown"

    def _normalize_seller(self, raw: str) -> str:
        raw_lower = (raw or "").lower()
        if "dealer" in raw_lower or "firma" in raw_lower or "salon" in raw_lower:
            return "dealer"
        return "private"

    # ------------------------------------------------------------------
    # Next.js / JSON helpers
    # ------------------------------------------------------------------

    def _extract_next_data(self, soup: BeautifulSoup) -> dict | None:
        """Extract the __NEXT_DATA__ JSON blob from a Next.js page."""
        script = soup.find("script", {"id": "__NEXT_DATA__"})
        if not script or not script.string:
            return None
        try:
            return json.loads(script.string)
        except json.JSONDecodeError:
            return None

    def _find_ads_in_json(self, data: Any, depth: int = 0) -> list[dict]:
        """Recursively search a JSON tree for a list of ad-like objects."""
        if depth > 10:
            return []
        if isinstance(data, list):
            if data and self._looks_like_ads(data):
                return data
            for item in data:
                if isinstance(item, (dict, list)):
                    result = self._find_ads_in_json(item, depth + 1)
                    if result:
                        return result
            return []
        if isinstance(data, dict):
            for key in ("ads", "listings", "adverts", "edges", "nodes", "items", "results"):
                val = data.get(key)
                if isinstance(val, list) and val and self._looks_like_ads(val):
                    return val
            for val in data.values():
                if isinstance(val, (dict, list)):
                    result = self._find_ads_in_json(val, depth + 1)
                    if result:
                        return result
        return []

    def _looks_like_ads(self, lst: list) -> bool:
        """Heuristic: does this list look like a collection of car ads?"""
        if not lst or not isinstance(lst[0], dict):
            return False
        item = lst[0]
        if "node" in item and isinstance(item["node"], dict):
            item = item["node"]
        has_ref = "url" in item or "href" in item or "id" in item
        has_content = "title" in item or "name" in item or "price" in item
        return has_ref and has_content

    # ------------------------------------------------------------------
    # String / ID helpers
    # ------------------------------------------------------------------

    def _clean_str(self, text: str) -> str:
        return " ".join(text.split()) if text else ""

    def _parse_year(self, text: str) -> int:
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else 2020

    def _slugify_to_id(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:12]
