"""Tests for the weighted reliability scorer."""
from __future__ import annotations

from src.scoring.reliability import WEIGHTS, ReliabilityScorer


def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0


def test_total_is_weighted_sum_of_components(chr_listing):
    score = ReliabilityScorer().score(chr_listing, market_avg=62_800)
    manual = (
        score.reliability_score * WEIGHTS["reliability"]
        + score.maintenance_score * WEIGHTS["maintenance"]
        + score.mileage_score * WEIGHTS["mileage"]
        + score.service_history_score * WEIGHTS["service_history"]
        + score.price_value_score * WEIGHTS["price_value"]
        + score.resale_score * WEIGHTS["resale"]
    )
    assert round(manual, 2) == score.total_score


def test_score_within_bounds(chr_listing):
    score = ReliabilityScorer().score(chr_listing)
    assert 0.0 <= score.total_score <= 10.0


def test_listing_id_optional_before_insert(chr_listing):
    # Scoring happens before DB insert, so listing_id must be allowed to be None
    score = ReliabilityScorer().score(chr_listing)
    assert score.listing_id is None


def test_known_model_beats_unknown(make_listing):
    scorer = ReliabilityScorer()
    toyota = scorer.score(make_listing(make="toyota", model="c-hr"))
    unknown = scorer.score(make_listing(make="ssangyong", model="korando"))
    assert toyota.reliability_score > unknown.reliability_score


def test_lower_mileage_scores_higher(make_listing):
    scorer = ReliabilityScorer()
    low = scorer.score(make_listing(mileage_km=10_000))
    high = scorer.score(make_listing(mileage_km=140_000))
    assert low.mileage_score > high.mileage_score


def test_below_market_price_flagged_good_value(chr_listing):
    score = ReliabilityScorer().score(chr_listing, market_avg=70_000)
    # 58,900 is ~16% below 70,000 -> negative deviation, strong price score
    assert score.price_deviation_pct < 0
    assert score.price_value_score >= 8.0


def test_suspiciously_cheap_flagged(make_listing):
    # Price < 70% of market avg should be flagged suspicious
    score = ReliabilityScorer().score(make_listing(price_pln=35_000), market_avg=62_800)
    assert score.is_suspicious is True


def test_fair_price_not_suspicious(chr_listing):
    score = ReliabilityScorer().score(chr_listing, market_avg=62_800)
    assert score.is_suspicious is False


def test_rank_listings_sorted_desc(make_listing):
    scorer = ReliabilityScorer()
    good = make_listing(make="toyota", model="rav4", mileage_km=20_000)
    poor = make_listing(make="renault", model="captur", mileage_km=140_000)
    ranked = scorer.rank_listings([poor, good])
    assert ranked[0].total_score >= ranked[1].total_score
