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
