"""Tests for `_score_is_void` in data.py.

The function decides whether a tennis match score should be treated as voided
(incomplete / unfinished). Voided matches are excluded from aggregated metrics.
"""

from data import _score_is_void


class TestScoreIsVoid:
    def test_empty_or_none(self):
        assert _score_is_void("") is True
        assert _score_is_void(None) is True
        assert _score_is_void(123) is True

    def test_complete_two_set_match(self):
        assert _score_is_void("6-3 6-4") is False

    def test_complete_three_set_match(self):
        assert _score_is_void("6-3 4-6 7-5") is False

    def test_tiebreak_set_is_completed(self):
        # A 7-6(5) set is fine (tiebreak parens count as completed).
        assert _score_is_void("7-6(5) 6-4") is False

    def test_incomplete_set(self):
        # 3-2 is not a finished set (<6 games each, no tiebreak).
        assert _score_is_void("3-2") is True

    def test_retirement_with_completed_set_is_valid(self):
        assert _score_is_void("6-3 2-1 RET") is False

    def test_retirement_without_completed_set_is_void(self):
        assert _score_is_void("2-1 RET") is True

    def test_walkover_or_no_sets(self):
        assert _score_is_void("W/O") is True

    def test_lone_retirement_marker_current_behaviour(self):
        # A bare "RET" without any set tokens is currently treated as NOT void
        # (the function returns ``not is_retirement`` when no set tokens exist).
        # This is an edge case worth revisiting; this test pins current behaviour.
        assert _score_is_void("RET") is False
