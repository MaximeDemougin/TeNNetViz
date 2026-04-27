"""Tests for the centralized config constants."""

import config


def test_default_constants():
    assert config.BDD_TENNIS == "TeNNet"
    assert config.BDD_USERS == "FootNet"
    assert config.MAX_PRED_BETABLE == 4.0
    assert config.MIN_PRED_BETABLE == 1.1
    assert config.BOOKMAKER_MARGIN_FACTOR == 0.97
    assert config.INPLAY_BADGE_TTL == 60
    assert config.DATA_CACHE_TTL == 300
