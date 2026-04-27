"""Centralized configuration constants for TeNNetViz.

Values can be overridden via environment variables for deployment.
"""

import os

# --- Database schemas ---
BDD_TENNIS = os.getenv("TENNETVIZ_BDD_TENNIS", "TeNNet")
BDD_USERS = os.getenv("TENNETVIZ_BDD_USERS", "FootNet")

# --- Betting prediction filters (used in future_matchs) ---
MAX_PRED_BETABLE = float(os.getenv("TENNETVIZ_MAX_PRED", "4"))
MIN_PRED_BETABLE = float(os.getenv("TENNETVIZ_MIN_PRED", "1.1"))

# --- Bookmaker margin adjustment ---
# real_odds = (1 / (odds - 1)) * BOOKMAKER_MARGIN_FACTOR + 1
# 0.97 corresponds to ~3% vigorish removal.
BOOKMAKER_MARGIN_FACTOR = float(os.getenv("TENNETVIZ_BOOKMAKER_MARGIN", "0.97"))

# --- Cache TTLs (seconds) ---
INPLAY_BADGE_TTL = int(os.getenv("TENNETVIZ_INPLAY_BADGE_TTL", "60"))
DATA_CACHE_TTL = int(os.getenv("TENNETVIZ_DATA_CACHE_TTL", "300"))
# Granular TTLs (defaults derived from DATA_CACHE_TTL when unset)
DATA_CACHE_TTL_FINISHED = int(
    os.getenv("TENNETVIZ_DATA_CACHE_TTL_FINISHED", str(DATA_CACHE_TTL * 2))
)
DATA_CACHE_TTL_INPLAY = int(
    os.getenv("TENNETVIZ_DATA_CACHE_TTL_INPLAY", str(max(30, DATA_CACHE_TTL // 10)))
)
DATA_CACHE_TTL_FUTURE = int(
    os.getenv("TENNETVIZ_DATA_CACHE_TTL_FUTURE", str(DATA_CACHE_TTL))
)

# --- Alerts thresholds ---
ALERT_WINRATE_MIN = float(os.getenv("TENNETVIZ_ALERT_WINRATE_MIN", "48.0"))
ALERT_DRAWDOWN_MAX_PCT = float(os.getenv("TENNETVIZ_ALERT_DRAWDOWN_MAX_PCT", "15.0"))
ALERT_RECENT_BETS_WINDOW = int(os.getenv("TENNETVIZ_ALERT_RECENT_WINDOW", "30"))
ALERT_AVG_COTE_MAX = float(os.getenv("TENNETVIZ_ALERT_AVG_COTE_MAX", "2.5"))
ALERT_HOT_PICK_EV_MIN = float(os.getenv("TENNETVIZ_ALERT_HOT_PICK_EV_MIN", "5.0"))
