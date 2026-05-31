"""Tests for market analysis (the non-DB pure-logic methods)."""
from __future__ import annotations

from src.scoring.market_analysis import (
    DEPRECIATION_RATES,
    SUSPICIOUS_PRICE_THRESHOLD,
    MarketAnalyzer,
)


def _analyzer() -> MarketAnalyzer:
    # The pure methods don't touch the session, so None is fine here.
    return MarketAnalyzer(session=None)  # type: ignore[arg-type]


def test_suspicious_threshold_is_70_percent():
    assert SUSPICIOUS_PRICE_THRESHOLD == 0.70


def test_is_suspiciously_cheap_true(make_listing):
    a = _analyzer()
    assert a.is_suspiciously_cheap(make_listing(price_pln=40_000), market_avg=62_800) is True


def test_is_suspiciously_cheap_false_for_fair_price(chr_listing):
    a = _analyzer()
    assert a.is_suspiciously_cheap(chr_listing, market_avg=62_800) is False


def test_toyota_depreciates_slower_than_european():
    assert DEPRECIATION_RATES["toyota"] < DEPRECIATION_RATES["peugeot"]


def test_resale_value_decreases_over_time(chr_listing):
    a = _analyzer()
    v1 = a.estimate_resale_value(chr_listing, years=1)
    v3 = a.estimate_resale_value(chr_listing, years=3)
    assert v3 < v1 < chr_listing.price_pln


def test_resale_value_matches_depreciation_model(make_listing):
    a = _analyzer()
    car = make_listing(make="toyota", price_pln=100_000)
    rate = DEPRECIATION_RATES["toyota"]
    expected = 100_000 * ((1 - rate) ** 3)
    assert round(a.estimate_resale_value(car, years=3), 2) == round(expected, 2)


def test_price_percentile_empty_returns_midpoint(chr_listing):
    a = _analyzer()
    assert a.get_price_percentile(chr_listing, []) == 50.0


def test_price_percentile_cheapest_is_low(make_listing):
    a = _analyzer()
    cheapest = make_listing(price_pln=40_000)
    others = [make_listing(price_pln=p) for p in (50_000, 60_000, 70_000, 80_000)]
    pct = a.get_price_percentile(cheapest, [cheapest, *others])
    assert pct <= 20.0


def test_compute_inline_avg_groups_by_make_model_year(make_listing):
    a = _analyzer()
    listings = [
        make_listing(make="toyota", model="c-hr", year=2021, price_pln=50_000),
        make_listing(make="toyota", model="c-hr", year=2021, price_pln=60_000),
        make_listing(make="kia", model="niro", year=2021, price_pln=70_000),
    ]
    avgs = a.compute_inline_avg(listings)
    assert avgs["toyota_c-hr_2021"] == 55_000
    assert avgs["kia_niro_2021"] == 70_000
