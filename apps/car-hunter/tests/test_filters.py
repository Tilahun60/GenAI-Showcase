"""Tests for the requirements filter engine."""
from __future__ import annotations

from src.filters.requirements import Requirements, RequirementsFilter


def test_default_listing_passes(chr_listing):
    flt = RequirementsFilter(Requirements())
    assert flt.matches(chr_listing) is True


def test_rejects_over_price(make_listing):
    flt = RequirementsFilter(Requirements(max_price_pln=60_000))
    assert flt.matches(make_listing(price_pln=75_000)) is False


def test_rejects_zero_or_negative_price(make_listing):
    flt = RequirementsFilter(Requirements())
    assert flt.matches(make_listing(price_pln=0)) is False


def test_rejects_too_old(make_listing):
    flt = RequirementsFilter(Requirements(min_year=2020))
    assert flt.matches(make_listing(year=2018)) is False


def test_rejects_manual_transmission(make_listing):
    flt = RequirementsFilter(Requirements())
    assert flt.matches(make_listing(transmission="manual")) is False


def test_rejects_non_hybrid(make_listing):
    flt = RequirementsFilter(Requirements())
    assert flt.matches(make_listing(fuel_type="diesel")) is False


def test_rejects_over_mileage(make_listing):
    flt = RequirementsFilter(Requirements(max_mileage_km=150_000))
    assert flt.matches(make_listing(mileage_km=200_000)) is False


def test_rejects_accident_history(make_listing):
    flt = RequirementsFilter(Requirements(exclude_accident_history=True))
    assert flt.matches(make_listing(accident_history=True)) is False


def test_allows_unknown_accident_history(make_listing):
    # None (unknown) should not be rejected — only explicit True is
    flt = RequirementsFilter(Requirements(exclude_accident_history=True))
    assert flt.matches(make_listing(accident_history=None)) is True


def test_rejects_disallowed_seller(make_listing):
    flt = RequirementsFilter(Requirements(allowed_seller_types=["dealer"]))
    assert flt.matches(make_listing(seller_type="private")) is False


def test_filter_batch_partitions(make_listing):
    flt = RequirementsFilter(Requirements())
    good = make_listing(price_pln=50_000)
    bad = make_listing(price_pln=99_000)
    result = flt.filter_batch([good, bad, good])
    assert len(result) == 2
    assert all(item.price_pln == 50_000 for item in result)
