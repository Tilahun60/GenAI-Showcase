"""Tests for the PMT-based leasing calculator."""
from __future__ import annotations

from src.leasing.calculator import LeasingCalculator, LeasingParams, _pmt


def test_pmt_formula_known_value():
    # 100,000 PLN at 1% monthly over 12 months -> ~8884.88/mo
    payment = _pmt(0.01, 12, 100_000)
    assert round(payment, 2) == 8884.88


def test_pmt_zero_interest_is_straight_division():
    assert _pmt(0.0, 10, 50_000) == 5_000


def test_down_payment_and_buyout_match_params(chr_listing):
    params = LeasingParams(down_payment_pct=0.20, buyout_pct=0.30)
    result = LeasingCalculator().calculate(chr_listing, params)
    assert result.down_payment_pln == round(58_900 * 0.20, 2)
    assert result.buyout_value_pln == round(58_900 * 0.30, 2)


def test_term_months_passthrough(chr_listing):
    result = LeasingCalculator().calculate(chr_listing, LeasingParams(term_months=48))
    assert result.term_months == 48


def test_total_cost_components(chr_listing):
    result = LeasingCalculator().calculate(chr_listing)
    expected_total = round(
        result.down_payment_pln
        + result.monthly_payment_pln * result.term_months
        + result.buyout_value_pln,
        2,
    )
    assert result.total_cost_pln == expected_total


def test_cost_per_year(chr_listing):
    result = LeasingCalculator().calculate(chr_listing, LeasingParams(term_months=48))
    assert result.cost_per_year_pln == round(result.total_cost_pln / 4, 2)


def test_maintenance_toyota_cheaper_than_default(make_listing):
    calc = LeasingCalculator()
    toyota = calc.estimate_maintenance_yearly("toyota")
    unknown = calc.estimate_maintenance_yearly("ssangyong")
    assert toyota < unknown


def test_listing_id_optional_before_insert(chr_listing):
    result = LeasingCalculator().calculate(chr_listing)
    assert result.listing_id is None
