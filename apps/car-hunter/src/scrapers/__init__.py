"""Car listing scrapers for various Polish used-car marketplaces."""
from .aaa_auto import AAAAutoScraper
from .base import BaseScraper
from .das_weltauto import DasWeltAutoScraper
from .olx import OLXScraper
from .otomoto import OtomotoScraper
from .spoticar import SpoticarScraper
from .toyota_pewne import ToyotaPewneScraper

__all__ = [
    "BaseScraper",
    "OtomotoScraper",
    "OLXScraper",
    "AAAAutoScraper",
    "SpoticarScraper",
    "ToyotaPewneScraper",
    "DasWeltAutoScraper",
]

ALL_SCRAPERS = [
    OtomotoScraper,
    OLXScraper,
    AAAAutoScraper,
    SpoticarScraper,
    ToyotaPewneScraper,
    DasWeltAutoScraper,
]
