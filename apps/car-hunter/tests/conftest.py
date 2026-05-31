"""Shared pytest fixtures for Car Hunter tests."""
from __future__ import annotations

import pytest

from src.models.schemas import CarListingCreate


@pytest.fixture
def chr_listing() -> CarListingCreate:
    """A realistic Toyota C-HR Hybrid 2021 listing (the README example)."""
    return CarListingCreate(
        source="otomoto",
        external_id="ID6GpXaB",
        url="https://www.otomoto.pl/osobowe/oferta/toyota-c-hr-ID6GpXaB.html",
        title="Toyota C-HR 2.0 Hybrid 2021",
        make="toyota",
        model="c-hr",
        year=2021,
        price_pln=58_900,
        mileage_km=112_000,
        fuel_type="hybrid",
        transmission="automatic",
        body_type="suv",
        accident_history=False,
        seller_type="dealer",
        location="Warszawa",
        raw_data={},
    )


@pytest.fixture
def make_listing():
    """Factory to build a listing overriding any field."""
    base = dict(
        source="otomoto",
        external_id="X1",
        url="https://example.com/x",
        title="Test Car",
        make="toyota",
        model="c-hr",
        year=2022,
        price_pln=50_000,
        mileage_km=40_000,
        fuel_type="hybrid",
        transmission="automatic",
        body_type="suv",
        accident_history=False,
        seller_type="dealer",
        location="Kraków",
        raw_data={},
    )

    def _factory(**overrides) -> CarListingCreate:
        return CarListingCreate(**{**base, **overrides})

    return _factory
