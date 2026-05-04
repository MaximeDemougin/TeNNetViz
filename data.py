# ruff: noqa: E402
import streamlit as st
import pandas as pd
import numpy as np
import re
import logging

import sys
import os


def _resolve_project_path() -> str:
    try:
        project_path = st.session_state.get("project_path")
    except Exception:
        project_path = None

    if project_path:
        return project_path

    return os.path.dirname(os.path.abspath(__file__))


project_path = _resolve_project_path()

try:
    st.session_state["project_path"] = project_path
except Exception:
    pass

if project_path not in sys.path:
    sys.path.append(project_path)

from db_utils.db_utils import read_sql_query
from config import (
    BDD_TENNIS as BDD,
    MAX_PRED_BETABLE,
    MIN_PRED_BETABLE,
    BOOKMAKER_MARGIN_FACTOR,
    DATA_CACHE_TTL,
    DATA_CACHE_TTL_FINISHED,
    DATA_CACHE_TTL_INPLAY,
    DATA_CACHE_TTL_FUTURE,
)  # noqa: F401

logger = logging.getLogger(__name__)


def _score_is_void(score):
    set_re = re.compile(r"^(?P<a>\d+)-(?P<b>\d+)(?:\(\d+\))?$")
    try:
        if not isinstance(score, str) or score.strip() == "":
            return True
        # normalize tokens and keep original tokens for set parsing
        raw_tokens = score.strip().split()
        tokens_upper = [t.upper().strip(".,") for t in raw_tokens]

        # detect retirement/abandon markers (common variants)
        retire_markers = (
            "RET",
            "RETIRE",
            "RETIREE",
            "RET.",
            "ABD",
            "ABANDON",
            "RETIREMENT",
        )
        is_retirement = any(
            any(marker in t for marker in retire_markers) for t in tokens_upper
        )

        # keep tokens that look like set scores (contain digits and a dash)
        set_tokens = [t.rstrip(",") for t in raw_tokens if re.search(r"\d+-\d+", t)]

        # if there are no set tokens, consider void unless retirement explicitly present with at least one numeric token
        if not set_tokens:
            return not is_retirement

        # helper to check if a set looks completed
        def _set_completed(t):
            m = set_re.match(t)
            if not m:
                return False
            a = int(m.group("a"))
            b = int(m.group("b"))
            return a >= 6 or b >= 6 or "(" in t

        # If the match ended with a retirement/abandon, only consider it valid if there is at least one completed set
        if is_retirement:
            any_completed = any(_set_completed(t) for t in set_tokens)
            return not any_completed

        # Otherwise, ensure every reported set looks completed (>=6 or includes tiebreak)
        for t in set_tokens:
            if not _set_completed(t):
                return True
        return False
    except Exception:
        logger.exception("_score_is_void: failed to parse score %r", score)
        return True


def load_bankroll(user_id: int):
    """
    Loads the bankroll for a given user from the database.
    """
    user_id = int(user_id) if user_id is not None else 0
    bankroll = _load_bankroll_cached(user_id)
    st.session_state["bankroll"] = bankroll
    return bankroll


@st.cache_data(ttl=DATA_CACHE_TTL_FINISHED, show_spinner=False)
def _load_bankroll_cached(user_id: int) -> int:
    query_bankroll = "SELECT bankroll FROM FootNet.Users WHERE ID_USER = :user_id"
    bankroll_data = read_sql_query(BDD, query_bankroll, params={"user_id": user_id})
    if not bankroll_data.empty:
        return int(bankroll_data["bankroll"].values[0])
    return 0


def load_bets(user_id: int):
    """
    Loads the bets_data for a given user from the database.
    """
    return _load_bets_cached(int(user_id) if user_id is not None else 0)


@st.cache_data(ttl=DATA_CACHE_TTL_FINISHED, show_spinner=False)
def _load_bets_cached(user_id: int):
    query_bets = """SELECT b.*,
                            tourney_name,
                            tourney_level,
                            winner_name,
                            loser_name,
                            round,
                            surface,
                            match_settled,
                            score,
                            tourney_date,
                            pred_w_used as winner_pred,
                            pred_l_used as loser_pred,
                            is_ratio_odds_W,
                            is_ratio_odds_L,
                            'doubles' = TRUE as doubles,
                            'atp' as compet,
                            m.ID_TENNET
                                    FROM Bet b join men_matchs m on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE match_settled in (1,2) and score != 'W/O' and status = 1 and b.ID_USER = :user_id
                    UNION
                        SELECT b.*,
                            tourney_name,
                            tourney_level,
                            winner_name,
                            loser_name,
                            round,
                            surface,
                            match_settled,
                            score,
                            tourney_date,
                            pred_w_used as winner_pred,
                            pred_l_used as loser_pred,
                            is_ratio_odds_W,
                            is_ratio_odds_L,
                            'doubles' = TRUE as doubles,
                            'wta' as compet,
                            m.ID_TENNET
                                    FROM  Bet b join women_matchs m on (b.ID_MATCH = m.ID_MATCH)
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE  match_settled in (1,2) and score != 'W/O' and status = 1 and b.ID_USER = :user_id
                    UNION
                        SELECT b.*, 
                                tourney_name,
                                tourney_level,
                                concat(winner_name1,'/',winner_name2) as winner_name,
                                concat(loser_name1,'/',loser_name2)  as loser_name,
                                round,
                                surface,
                                match_settled, 
                                score,
                                tourney_date, 
                                pred_w_used as winner_pred,
                                pred_l_used as loser_pred,
                                is_ratio_odds_W,
                                is_ratio_odds_L,
                                'doubles' = FALSE as doubles  ,
                                'doubles' as compet,
                                NULL as ID_TENNET
                                    FROM Bet b join double_matchs m  on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE match_settled in (1,2) and score != 'W/O' and status = 1 and b.ID_USER = :user_id"""
    bets_data = read_sql_query(BDD, query_bets, params={"user_id": user_id})
    bets_data.sort_values(by="tourney_date", ascending=True, inplace=True)
    bets_data.reset_index(drop=True, inplace=True)
    return bets_data


def prepare_bets_data(user_id: int, finished: bool = True):
    """
    Groups bets_data by player beted and calculates total amount beted and won/lost.
    """
    return _prepare_bets_data_cached(
        int(user_id) if user_id is not None else 0, bool(finished)
    )


@st.cache_data(ttl=DATA_CACHE_TTL_INPLAY, show_spinner=False)
def _prepare_bets_data_cached(user_id: int, finished: bool):

    if finished:
        bets_data = load_bets(user_id)
    else:
        bets_data = load_inplay_bets(user_id)

    # Defensive: if no data returned, provide an empty dataframe with expected schema
    if bets_data is None or bets_data.empty:
        cols = [
            "ID_MATCH",
            "Match",
            "Date",
            "Compétition",
            "Level",
            "Round",
            "Surface",
            "Mise",
            "Cote",
            "Prédiction",
            "Gains net",
            "Marge attendue",
            "Cumulative Gains",
        ]
        empty_df = pd.DataFrame(columns=cols)
        # Ensure numeric columns exist with float dtype
        for num_col in [
            "Mise",
            "Cote",
            "Prédiction",
            "Gains net",
            "Marge attendue",
            "Cumulative Gains",
        ]:
            empty_df[num_col] = empty_df.get(num_col, pd.Series(dtype=float)).astype(
                float
            )
        return empty_df

    bets_data["Match"] = bets_data["winner_name"] + " - " + bets_data["loser_name"]
    # real_odds applies a bookmaker margin adjustment (vig removal)
    bets_data["real_odds"] = (1 / (bets_data["odds"] - 1)) * BOOKMAKER_MARGIN_FACTOR + 1

    if finished:
        bets_data["cote_pred"] = np.where(
            (bets_data["match_settled"] == 1) & (bets_data["bet"] == 1)
            | (bets_data["match_settled"] == 2) & (bets_data["bet"] == 0),
            bets_data["winner_pred"],
            bets_data["loser_pred"],
        )
        bets_data["player_bet"] = np.where(
            (bets_data["match_settled"] == 1) & (bets_data["bet"] == 1)
            | (bets_data["match_settled"] == 2) & (bets_data["bet"] == 0),
            bets_data["winner_name"],
            bets_data["loser_name"],
        )
        bets_data["win"] = np.where(
            (bets_data["match_settled"] == 1) & (bets_data["bet"] == 1)
            | (bets_data["match_settled"] == 2) & (bets_data["bet"] == 0),
            1,
            0,
        )
        bets_data["net_gain"] = np.where(
            bets_data["win"] == 1,
            bets_data["real_odds"] * bets_data["stake"] - bets_data["stake"],
            -bets_data["stake"],
        )
        bets_data["net_unit"] = bets_data["net_gain"] / bets_data["stake"]
        bets_data["is_ratio_odds"] = np.where(
            (bets_data["match_settled"] == 1) & (bets_data["bet"] == 1)
            | (bets_data["match_settled"] == 2) & (bets_data["bet"] == 0),
            bets_data["is_ratio_odds_W"],
            bets_data["is_ratio_odds_L"],
        )
    else:
        bets_data["cote_pred"] = np.where(
            bets_data["bet"] == 1, bets_data["winner_pred"], bets_data["loser_pred"]
        )
        bets_data["player_bet"] = np.where(
            bets_data["bet"] == 1, bets_data["winner_name"], bets_data["loser_name"]
        )
        bets_data["net_gain"] = 0.0
        bets_data["net_unit"] = 0.0
        bets_data["score"] = ""
        bets_data["is_ratio_odds"] = np.where(
            bets_data["bet"] == 1,
            bets_data["is_ratio_odds_W"],
            bets_data["is_ratio_odds_L"],
        )
    bets_data["marge_unit"] = bets_data["real_odds"] / bets_data["cote_pred"] - 1
    bets_data["marge"] = bets_data["marge_unit"] * bets_data["stake"]
    prepared_bets = bets_data[
        [
            "ID_MATCH",
            "Match",
            "tourney_date",
            "tourney_name",
            "compet",
            "surface",
            "tourney_level",
            "score",
            "player_bet",
            "stake",
            "round",
            "real_odds",
            "cote_pred",
            "net_gain",
            "marge",
            "is_ratio_odds",
            "ID_TENNET",
        ]
        + (["odds_maj"] if "odds_maj" in bets_data.columns else [])
    ].copy()
    prepared_bets["compet"] = prepared_bets["compet"].str.title()

    # Extract time (Horaire) from tourney_date for display in match table
    try:
        prepared_bets["tourney_date"] = pd.to_datetime(
            prepared_bets["tourney_date"], errors="coerce"
        )
        prepared_bets["Horaire"] = prepared_bets["tourney_date"].dt.strftime("%H:%M")
    except Exception:
        logger.exception("Failed to parse tourney_date / Horaire")
        prepared_bets["Horaire"] = ""

    # Map surface names to French and normalize capitalization
    try:
        prepared_bets["surface"] = prepared_bets["surface"].astype(str).str.title()
        surface_map = {
            "Hard": "Dur",
            "Grass": "Gazon",
            "Clay": "Terre battue",
        }
        prepared_bets["surface"] = prepared_bets["surface"].map(
            lambda v: surface_map.get(v, v)
        )
    except Exception:
        logger.exception("Failed to map surface names")

    # Map round codes to French labels
    try:
        round_map = {
            "F": "Finale",
            "SF": "Demi-finale",
            "QF": "Quart de finale",
            "R16": "8emes de finale",
            "R32": "16emes de finale",
            "R64": "32emes de finale",
            "R128": "64emes de finale",
            "RR": "Round Robin",
        }
        # Normalize and map; keep original value if not found
        prepared_bets["round"] = prepared_bets["round"].astype(str).str.upper()
        prepared_bets["round"] = prepared_bets["round"].map(
            lambda r: round_map.get(r, r)
        )
    except Exception:
        logger.exception("Failed to map round names")

    # Map tourney level codes to descriptive labels
    try:
        level_map = {
            "C": "Challenger",
            "A": "ATP 250/500",
            "G": "Grand Chelem",
            "M": "Masters 1000",
            "I": "WTA 250",
            "P": "WTA 500",
            "PM": "WTA 1000",
        }
        prepared_bets["tourney_level"] = (
            prepared_bets["tourney_level"].astype(str).str.upper()
        )
        prepared_bets["tourney_level"] = prepared_bets["tourney_level"].map(
            lambda lvl: level_map.get(lvl, lvl)
        )
    except Exception as e:
        logger.exception("Error mapping tourney level names: %s", e)

    prepared_bets["real_odds"] = prepared_bets["real_odds"].round(3)
    prepared_bets["cote_pred"] = prepared_bets["cote_pred"].round(3)
    prepared_bets["marge"] = prepared_bets["marge"].round(2)
    prepared_bets["stake"] = prepared_bets["stake"].round(2)
    prepared_bets["net_gain"] = prepared_bets["net_gain"].round(2)

    # Add combined tournament type (compet x level) to allow grouping by this category
    try:
        prepared_bets["tourney_type"] = (
            prepared_bets["compet"].astype(str)
            + " - "
            + prepared_bets["tourney_level"].astype(str)
        )
    except Exception:
        logger.exception("Failed to compute tourney_type")
        prepared_bets["tourney_type"] = ""

    prepared_bets.rename(
        columns={
            "tourney_date": "Date",
            "tourney_name": "Tournoi",
            "tourney_level": "Level",
            "compet": "Compétition",
            "surface": "Surface",
            "stake": "Mise",
            "round": "Round",
            "score": "Score",
            "real_odds": "Cote",
            "cote_pred": "Prédiction",
            "net_gain": "Gains net",
            "marge": "Marge attendue",
            "tourney_type": "Type de tournoi",
            "is_ratio_odds": "Ratio Odds",
        },
        inplace=True,
    )

    # Map is_ratio_odds boolean to readable labels
    prepared_bets["Ratio Odds"] = (
        prepared_bets["Ratio Odds"]
        .map({1: "Oui", 0: "Non", True: "Oui", False: "Non"})
        .fillna("Non")
    )

    # Flag matches with incomplete sets (voided) — they should not count in results.

    if finished:
        prepared_bets["voided"] = prepared_bets["Score"].apply(_score_is_void)
        # Exclude voided matches from the grouped results
        valid_bets = prepared_bets[~prepared_bets["voided"]].copy()
    else:
        valid_bets = prepared_bets.copy()

    # Define a function to calculate weighted average for Cote
    def weighted_avg(group):
        """Calculate weighted average of Cote using Mise as weights"""
        weights = group["Mise"]
        if weights.sum() == 0:
            # If all weights are zero, return simple mean
            return group["Cote"].mean()
        return np.average(group["Cote"], weights=weights)

    try:
        # First aggregate without the weighted Cote
        grouped_bets = (
            valid_bets.groupby(["ID_MATCH", "Match", "player_bet"])
            .agg(
                {
                    "Date": "first",
                    "Compétition": "first",
                    "Tournoi": "first",
                    "Level": "first",
                    "Round": "first",
                    "Surface": "first",
                    "Score": "first",
                    "Type de tournoi": "first",
                    "Ratio Odds": "first",
                    "ID_TENNET": "first",
                    "Mise": "sum",
                    "Prédiction": "mean",
                    "Gains net": "sum",
                    "Marge attendue": "sum",
                    **(
                        {"odds_maj": "first"}
                        if "odds_maj" in valid_bets.columns
                        else {}
                    ),
                }
            )
            .reset_index()
        )

        # Calculate weighted Cote separately using apply
        cote_weighted = (
            valid_bets.groupby(["ID_MATCH", "Match", "player_bet"])
            .apply(weighted_avg, include_groups=False)
            .reset_index(name="Cote")
        )

        # Merge the weighted Cote back
        grouped_bets = grouped_bets.merge(
            cote_weighted, on=["ID_MATCH", "Match", "player_bet"], how="left"
        )

    except Exception as e:
        logger.exception("Error during grouping bets: %s", e)
        raise
    # print(f"Prepared grouped bets with {len(grouped_bets)} entries.")
    grouped_bets["Cote"] = grouped_bets["Cote"].round(3)
    grouped_bets["Prédiction"] = grouped_bets["Prédiction"].round(3)
    grouped_bets["Marge attendue"] = grouped_bets["Marge attendue"].round(2)
    grouped_bets.sort_values(by="Date", ascending=True, inplace=True)
    grouped_bets.reset_index(drop=True, inplace=True)
    grouped_bets["Cumulative Gains"] = grouped_bets["Gains net"].cumsum()
    # print(grouped_bets.dtypes)
    # print(grouped_bets)

    return grouped_bets


def load_inplay_bets(user_id: int):
    """
    Loads the bets_data for a given user from the database.
    """
    return _load_inplay_bets_cached(int(user_id) if user_id is not None else 0)


@st.cache_data(ttl=DATA_CACHE_TTL_INPLAY, show_spinner=False)
def _load_inplay_bets_cached(user_id: int):
    query_bets = """SELECT b.*,
                            m.tourney_name,
                            m.tourney_level,
                            m.winner_name,
                            m.loser_name,
                            m.round,
                            m.surface,
                            m.match_settled,
                            m.tourney_date,
                            p.pred_w_used as winner_pred,
                            p.pred_l_used as loser_pred,
                            p.is_ratio_odds_W,
                            p.is_ratio_odds_L,
                            'doubles' = TRUE as doubles,
                            'atp' as compet,
                            m.ID_TENNET,
                            o.maj as odds_maj
                                    FROM Bet b join men_matchs m on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        left join odds o on (b.ID_MATCH = o.id)
                                        WHERE not m.match_settled in (1,2) and b.ID_USER = :user_id
                    UNION
                        SELECT b.*,
                            m.tourney_name,
                            m.tourney_level,
                            m.winner_name,
                            m.loser_name,
                            m.round,
                            m.surface,
                            m.match_settled,
                            m.tourney_date,
                            p.pred_w_used as winner_pred,
                            p.pred_l_used as loser_pred,
                            p.is_ratio_odds_W,
                            p.is_ratio_odds_L,
                            'doubles' = TRUE as doubles,
                            'wta' as compet,
                            m.ID_TENNET,
                            o.maj as odds_maj
                                    FROM  Bet b join women_matchs m on (b.ID_MATCH = m.ID_MATCH)
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        left join odds o on (b.ID_MATCH = o.id)
                                        WHERE  not m.match_settled in (1,2) and b.ID_USER = :user_id
                    UNION
                        SELECT b.*, 
                                m.tourney_name,
                                m.tourney_level,
                                concat(m.winner_name1,'/',m.winner_name2) as winner_name,
                                concat(m.loser_name1,'/',m.loser_name2)  as loser_name,
                                m.round,
                                m.surface,
                                m.match_settled, 
                                m.tourney_date, 
                                p.pred_w_used as winner_pred,
                                p.pred_l_used as loser_pred,
                                p.is_ratio_odds_W,
                                p.is_ratio_odds_L,
                                'doubles' = FALSE as doubles  ,
                                'doubles' as compet,
                                NULL as ID_TENNET,
                                o.maj as odds_maj
                                    FROM Bet b join double_matchs m  on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        left join odds o on (b.ID_MATCH = o.id)
                                        WHERE not m.match_settled in (1,2) and b.ID_USER = :user_id"""
    bets_data = read_sql_query(BDD, query_bets, params={"user_id": user_id})
    bets_data.sort_values(by="tourney_date", ascending=True, inplace=True)
    bets_data.reset_index(drop=True, inplace=True)
    return bets_data


def load_future_matchs():
    """
    Loads the future matchs from the database.
    """
    return _load_future_matchs_cached()


@st.cache_data(ttl=DATA_CACHE_TTL_INPLAY, show_spinner=False)
def load_future_matchs_missing_betfair(within_minutes: int = 60):
    """Future matches starting in the next ``within_minutes`` not present in
    ``betfair_links`` (joined on ``ID_MATCH``).

    Covers ATP, WTA and doubles. Returns a DataFrame; empty if none.
    """
    minutes = max(int(within_minutes), 0)
    query = """
        SELECT 'atp' AS compet,
               m.ID_MATCH, m.tourney_name, m.tourney_level, m.round,
               m.surface, m.tourney_date, m.winner_name, m.loser_name
        FROM men_matchs m
        LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
        WHERE m.match_settled = 0
          AND m.tourney_date BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL :minutes MINUTE)
          AND bl.ID_MATCH IS NULL
        UNION ALL
        SELECT 'wta' AS compet,
               m.ID_MATCH, m.tourney_name, m.tourney_level, m.round,
               m.surface, m.tourney_date, m.winner_name, m.loser_name
        FROM women_matchs m
        LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
        WHERE m.match_settled = 0
          AND m.tourney_date BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL :minutes MINUTE)
          AND bl.ID_MATCH IS NULL
        UNION ALL
        SELECT 'doubles' AS compet,
               m.ID_MATCH, m.tourney_name, m.tourney_level, m.round,
               m.surface, m.tourney_date,
               CONCAT(m.winner_name1, '/', m.winner_name2) AS winner_name,
               CONCAT(m.loser_name1, '/', m.loser_name2) AS loser_name
        FROM double_matchs m
        LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
        WHERE m.match_settled = 0
          AND m.tourney_date BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL :minutes MINUTE)
          AND bl.ID_MATCH IS NULL
    """
    try:
        df = read_sql_query(BDD, query, params={"minutes": minutes})
    except Exception:
        logger.exception("load_future_matchs_missing_betfair: failed")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()
    df["tourney_date"] = pd.to_datetime(df["tourney_date"], errors="coerce")
    df = df.sort_values("tourney_date").reset_index(drop=True)
    return df


@st.cache_data(ttl=DATA_CACHE_TTL_FUTURE, show_spinner=False)
def load_players_betfair_coverage(year: int = 2026):
    """For every singles player (ATP + WTA) appearing in matches of ``year``,
    return total matches vs matches found in ``betfair_links`` (joined on
    ``ID_MATCH``).

    Doubles are intentionally excluded (4 players per match, less actionable).
    """
    year = int(year)
    query = """
        SELECT compet, player,
               COUNT(*) AS total_matches,
               SUM(CASE WHEN bl_id IS NOT NULL THEN 1 ELSE 0 END) AS found_matches,
               SUM(CASE WHEN bl_id IS NULL THEN 1 ELSE 0 END) AS missing_matches
        FROM (
            SELECT 'atp' AS compet, m.winner_name AS player, m.ID_MATCH AS mid, bl.ID_MATCH AS bl_id
            FROM men_matchs m
            LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
            WHERE YEAR(m.tourney_date) = :year
            UNION ALL
            SELECT 'atp', m.loser_name, m.ID_MATCH, bl.ID_MATCH
            FROM men_matchs m
            LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
            WHERE YEAR(m.tourney_date) = :year
            UNION ALL
            SELECT 'wta', m.winner_name, m.ID_MATCH, bl.ID_MATCH
            FROM women_matchs m
            LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
            WHERE YEAR(m.tourney_date) = :year
            UNION ALL
            SELECT 'wta', m.loser_name, m.ID_MATCH, bl.ID_MATCH
            FROM women_matchs m
            LEFT JOIN Betfair_links bl ON m.ID_MATCH = bl.ID_MATCH
            WHERE YEAR(m.tourney_date) = :year
        ) p
        WHERE player IS NOT NULL AND player <> ''
        GROUP BY compet, player
    """
    try:
        df = read_sql_query(BDD, query, params={"year": year})
    except Exception:
        logger.exception("load_players_betfair_coverage: failed")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()
    for col in ("total_matches", "found_matches", "missing_matches"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["coverage_pct"] = np.where(
        df["total_matches"] > 0, df["found_matches"] / df["total_matches"] * 100, 0.0
    ).round(1)
    df["compet"] = df["compet"].astype(str).str.upper()
    return df.sort_values(
        ["found_matches", "total_matches"], ascending=[True, False]
    ).reset_index(drop=True)


_FEATURES_TABLE_BY_COMPET = {
    "atp": ("men_features", "ID_TENNET"),
    "men": ("men_features", "ID_TENNET"),
    "wta": ("women_features", "ID_TENNET"),
    "women": ("women_features", "ID_TENNET"),
    "doubles": ("double_features", "ID_MATCH"),
    "double": ("double_features", "ID_MATCH"),
}


def get_features_table_name(compet: str) -> str | None:
    entry = _FEATURES_TABLE_BY_COMPET.get(str(compet).strip().lower())
    if entry is None:
        return None
    table, _ = entry
    return table


@st.cache_data(ttl=300, show_spinner=False)
def load_odds_latest_maj_time():
    """Retourne MAX(odds.maj) le plus recent (timestamp ou None)."""
    try:
        df = read_sql_query(BDD, "SELECT MAX(maj) AS updated_at FROM odds")
    except Exception:
        logger.exception("load_odds_latest_maj_time: failed")
        return None

    if df is None or df.empty or "updated_at" not in df.columns:
        return None

    timestamp = pd.to_datetime(df["updated_at"].iloc[0], errors="coerce")
    return None if pd.isna(timestamp) else timestamp


def load_match_features(match_id, compet: str):
    """
    Charge les features calculées pour un match donné depuis
    men_features / women_features / doubles_features selon `compet`.
    - Simples (atp/wta) : jointure sur `ID_TENNET`.
    - Doubles : jointure sur `ID_MATCH`.
    Retourne un DataFrame (généralement 1 ligne) ou None si pas trouvé.
    """
    if match_id is None or not str(match_id).strip() or str(match_id).lower() == "nan":
        return None
    entry = _FEATURES_TABLE_BY_COMPET.get(str(compet).strip().lower())
    if entry is None:
        return None
    table, key_col = entry
    return _load_match_features_cached(str(match_id), table, key_col)


@st.cache_data(ttl=300, show_spinner=False)
def _load_match_features_cached(match_id: str, table: str, key_col: str):
    # `table` et `key_col` sont contrôlés par _FEATURES_TABLE_BY_COMPET → pas d'injection.
    query = f"SELECT * FROM {table} WHERE {key_col} = :match_id"
    try:
        return read_sql_query(BDD, query, params={"match_id": match_id})
    except Exception:
        logger.exception(
            "load_match_features: failed for table=%s key=%s id=%s",
            table,
            key_col,
            match_id,
        )
        return None


@st.cache_data(ttl=300, show_spinner=False)
def load_match_predictions(id_match):
    """
    Charge la ligne de la table `predictions` pour un ID_MATCH donné.
    Retourne un DataFrame (en général 1 ligne) ou None.
    """
    if (
        id_match is None
        or str(id_match).strip() == ""
        or str(id_match).lower() == "nan"
    ):
        return None
    try:
        return read_sql_query(
            BDD,
            "SELECT * FROM predictions WHERE ID_MATCH = :id_match",
            params={"id_match": str(id_match)},
        )
    except Exception:
        logger.exception("load_match_predictions: failed for ID_MATCH=%s", id_match)
        return None


@st.cache_data(ttl=300, show_spinner=False)
def load_match_odds(id_match):
    """
    Charge la ligne de la table `odds` pour un ID_MATCH donné.
    Retourne un DataFrame (en général 1 ligne) ou None.
    """
    if (
        id_match is None
        or str(id_match).strip() == ""
        or str(id_match).lower() == "nan"
    ):
        return None
    try:
        return read_sql_query(
            BDD,
            "SELECT * FROM odds WHERE id = :id_match",
            params={"id_match": str(id_match)},
        )
    except Exception:
        logger.exception("load_match_odds: failed for ID_MATCH=%s", id_match)
        return None


@st.cache_data(ttl=DATA_CACHE_TTL_FUTURE, show_spinner=False)
def _load_future_matchs_cached():
    query_matchs = """SELECT  m.tourney_name,
                            m.tourney_level,
                            m.winner_name,
                            m.loser_name,
                            m.round,
                            m.surface,
                            m.tourney_date,
                            p.pred_w_used as winner_pred,
                            p.pred_l_used as loser_pred,
                            'doubles' = TRUE as doubles,
                            'atp' as compet,
                             o.liens as odds_lien,
                             coalesce(
                                 case
                                     when wo.home_back is not null
                                          or wo.home_back_1 is not null
                                          or wo.home_back_2 is not null
                                     then greatest(
                                         coalesce(wo.home_back, 0),
                                         coalesce(wo.home_back_1, 0),
                                         coalesce(wo.home_back_2, 0)
                                     )
                                 end,
                                 o.MaxW
                             ) as max_odds1,
                             coalesce(
                                 case
                                     when wo.away_back is not null
                                          or wo.away_back_1 is not null
                                          or wo.away_back_2 is not null
                                     then greatest(
                                         coalesce(wo.away_back, 0),
                                         coalesce(wo.away_back_1, 0),
                                         coalesce(wo.away_back_2, 0)
                                     )
                                 end,
                                 o.MaxL
                             ) as max_odds2,
                                case
                                   when wo.home_back_2 is not null
                                       and coalesce(wo.home_back_2, -1) >= coalesce(wo.home_back_1, -1)
                                       and coalesce(wo.home_back_2, -1) >= coalesce(wo.home_back, -1)
                                   then 'WS_odds.home_back_2'
                                   when wo.home_back_1 is not null
                                       and coalesce(wo.home_back_1, -1) >= coalesce(wo.home_back_2, -1)
                                       and coalesce(wo.home_back_1, -1) >= coalesce(wo.home_back, -1)
                                   then 'WS_odds.home_back_1'
                                   when wo.home_back is not null
                                   then 'WS_odds.home_back'
                                   else 'odds.MaxW'
                                end as w_odds_source,
                                case
                                   when wo.away_back_2 is not null
                                       and coalesce(wo.away_back_2, -1) >= coalesce(wo.away_back_1, -1)
                                       and coalesce(wo.away_back_2, -1) >= coalesce(wo.away_back, -1)
                                   then 'WS_odds.away_back_2'
                                   when wo.away_back_1 is not null
                                       and coalesce(wo.away_back_1, -1) >= coalesce(wo.away_back_2, -1)
                                       and coalesce(wo.away_back_1, -1) >= coalesce(wo.away_back, -1)
                                   then 'WS_odds.away_back_1'
                                   when wo.away_back is not null
                                   then 'WS_odds.away_back'
                                   else 'odds.MaxL'
                                end as l_odds_source,
                             m.ID_MATCH,
                             m.ID_TENNET,
                             coalesce(wo.updated_at, o.maj) as odds_maj
                                    FROM men_matchs m 
                                    right join odds o on (m.ID_MATCH = o.id)
                                    left join WS_odds wo on (cast(m.ID_MATCH as char) = wo.ID_MATCH)
                                    right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE m.match_settled = 0
                    UNION
                        SELECT m.tourney_name,
                            m.tourney_level,
                            m.winner_name,
                            m.loser_name,
                            m.round,
                            m.surface,
                            m.tourney_date,
                            p.pred_w_used as winner_pred,
                            p.pred_l_used as loser_pred,
                            'doubles' = TRUE as doubles,
                            'wta' as compet,
                             o.liens as odds_lien,
                             coalesce(
                                 case
                                     when wo.home_back is not null
                                          or wo.home_back_1 is not null
                                          or wo.home_back_2 is not null
                                     then greatest(
                                         coalesce(wo.home_back, 0),
                                         coalesce(wo.home_back_1, 0),
                                         coalesce(wo.home_back_2, 0)
                                     )
                                 end,
                                 o.MaxW
                             ) as max_odds1,
                             coalesce(
                                 case
                                     when wo.away_back is not null
                                          or wo.away_back_1 is not null
                                          or wo.away_back_2 is not null
                                     then greatest(
                                         coalesce(wo.away_back, 0),
                                         coalesce(wo.away_back_1, 0),
                                         coalesce(wo.away_back_2, 0)
                                     )
                                 end,
                                 o.MaxL
                             ) as max_odds2,
                                case
                                   when wo.home_back_2 is not null
                                       and coalesce(wo.home_back_2, -1) >= coalesce(wo.home_back_1, -1)
                                       and coalesce(wo.home_back_2, -1) >= coalesce(wo.home_back, -1)
                                   then 'WS_odds.home_back_2'
                                   when wo.home_back_1 is not null
                                       and coalesce(wo.home_back_1, -1) >= coalesce(wo.home_back_2, -1)
                                       and coalesce(wo.home_back_1, -1) >= coalesce(wo.home_back, -1)
                                   then 'WS_odds.home_back_1'
                                   when wo.home_back is not null
                                   then 'WS_odds.home_back'
                                   else 'odds.MaxW'
                                end as w_odds_source,
                                case
                                   when wo.away_back_2 is not null
                                       and coalesce(wo.away_back_2, -1) >= coalesce(wo.away_back_1, -1)
                                       and coalesce(wo.away_back_2, -1) >= coalesce(wo.away_back, -1)
                                   then 'WS_odds.away_back_2'
                                   when wo.away_back_1 is not null
                                       and coalesce(wo.away_back_1, -1) >= coalesce(wo.away_back_2, -1)
                                       and coalesce(wo.away_back_1, -1) >= coalesce(wo.away_back, -1)
                                   then 'WS_odds.away_back_1'
                                   when wo.away_back is not null
                                   then 'WS_odds.away_back'
                                   else 'odds.MaxL'
                                end as l_odds_source,
                             m.ID_MATCH,
                             m.ID_TENNET,
                             coalesce(wo.updated_at, o.maj) as odds_maj
                                    FROM women_matchs m 
                                    right join odds o on (m.ID_MATCH = o.id)
                                    left join WS_odds wo on (cast(m.ID_MATCH as char) = wo.ID_MATCH)
                                    right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE m.match_settled = 0
                    UNION
                        SELECT  m.tourney_name,
                                m.tourney_level,
                                concat(m.winner_name1,'/',m.winner_name2) as winner_name,
                                concat(m.loser_name1,'/',m.loser_name2)  as loser_name,
                                m.round,
                                m.surface,
                                m.tourney_date, 
                                p.pred_w_used as winner_pred,
                                p.pred_l_used as loser_pred,
                                'doubles' = FALSE as doubles,
                                'doubles' as compet,
                                o.liens as odds_lien,
                                coalesce(
                                    case
                                        when wo.home_back is not null
                                             or wo.home_back_1 is not null
                                             or wo.home_back_2 is not null
                                        then greatest(
                                            coalesce(wo.home_back, 0),
                                            coalesce(wo.home_back_1, 0),
                                            coalesce(wo.home_back_2, 0)
                                        )
                                    end,
                                    o.MaxW
                                ) as max_odds1,
                                coalesce(
                                    case
                                        when wo.away_back is not null
                                             or wo.away_back_1 is not null
                                             or wo.away_back_2 is not null
                                        then greatest(
                                            coalesce(wo.away_back, 0),
                                            coalesce(wo.away_back_1, 0),
                                            coalesce(wo.away_back_2, 0)
                                        )
                                    end,
                                    o.MaxL
                                ) as max_odds2,
                                  case
                                     when wo.home_back_2 is not null
                                         and coalesce(wo.home_back_2, -1) >= coalesce(wo.home_back_1, -1)
                                         and coalesce(wo.home_back_2, -1) >= coalesce(wo.home_back, -1)
                                     then 'WS_odds.home_back_2'
                                     when wo.home_back_1 is not null
                                         and coalesce(wo.home_back_1, -1) >= coalesce(wo.home_back_2, -1)
                                         and coalesce(wo.home_back_1, -1) >= coalesce(wo.home_back, -1)
                                     then 'WS_odds.home_back_1'
                                     when wo.home_back is not null
                                     then 'WS_odds.home_back'
                                     else 'odds.MaxW'
                                  end as w_odds_source,
                                  case
                                     when wo.away_back_2 is not null
                                         and coalesce(wo.away_back_2, -1) >= coalesce(wo.away_back_1, -1)
                                         and coalesce(wo.away_back_2, -1) >= coalesce(wo.away_back, -1)
                                     then 'WS_odds.away_back_2'
                                     when wo.away_back_1 is not null
                                         and coalesce(wo.away_back_1, -1) >= coalesce(wo.away_back_2, -1)
                                         and coalesce(wo.away_back_1, -1) >= coalesce(wo.away_back, -1)
                                     then 'WS_odds.away_back_1'
                                     when wo.away_back is not null
                                     then 'WS_odds.away_back'
                                     else 'odds.MaxL'
                                  end as l_odds_source,
                             m.ID_MATCH,
                             NULL as ID_TENNET,
                             coalesce(wo.updated_at, o.maj) as odds_maj
                                    FROM double_matchs m
                                    right join odds o on (m.ID_MATCH = o.id)
                                    left join WS_odds wo on (cast(m.ID_MATCH as char) = wo.ID_MATCH)
                                    right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE m.match_settled = 0"""
    matchs_data = read_sql_query(BDD, query_matchs)
    matchs_data.sort_values(by="tourney_date", ascending=True, inplace=True)
    matchs_data.reset_index(drop=True, inplace=True)
    return matchs_data


def load_ws_odds_monitor():
    """Load WS_odds rows enriched with match metadata for monitoring."""
    return _load_ws_odds_monitor_cached()


@st.cache_data(ttl=60, show_spinner=False)
def _load_ws_odds_monitor_cached():
    query = """
        SELECT
            ws.id,
            ws.ID_MATCH,
            ws.ID_MARKET,
            ws.created_at,
            ws.updated_at,
            ws.status,
            ws.inplay,
            ws.n_updates,
            ws.winner_name as ws_winner_name,
            ws.loser_name as ws_loser_name,
            ws.home_back,
            ws.home_back_1,
            ws.home_back_2,
            ws.home_lay,
            ws.home_lay_1,
            ws.home_lay_2,
            ws.away_back,
            ws.away_back_1,
            ws.away_back_2,
            ws.away_lay,
            ws.away_lay_1,
            ws.away_lay_2,
            p.pred_w_used,
            p.pred_l_used,
            CASE
                WHEN m.ID_MATCH IS NOT NULL THEN 'atp'
                WHEN w.ID_MATCH IS NOT NULL THEN 'wta'
                WHEN d.ID_MATCH IS NOT NULL THEN 'doubles'
                ELSE 'unknown'
            END AS compet,
            coalesce(m.tourney_name, w.tourney_name, d.tourney_name) as tourney_name,
            coalesce(m.round, w.round, d.round) as round,
            coalesce(m.surface, w.surface, d.surface) as surface,
            coalesce(m.tourney_date, w.tourney_date, d.tourney_date) as tourney_date,
            coalesce(m.match_settled, w.match_settled, d.match_settled) as match_settled,
            coalesce(
                m.winner_name,
                w.winner_name,
                concat(d.winner_name1, '/', d.winner_name2),
                ws.winner_name
            ) as winner_name,
            coalesce(
                m.loser_name,
                w.loser_name,
                concat(d.loser_name1, '/', d.loser_name2),
                ws.loser_name
            ) as loser_name
        FROM WS_odds ws
        LEFT JOIN men_matchs m ON cast(m.ID_MATCH as char) = ws.ID_MATCH
        LEFT JOIN women_matchs w ON cast(w.ID_MATCH as char) = ws.ID_MATCH
        LEFT JOIN double_matchs d ON cast(d.ID_MATCH as char) = ws.ID_MATCH
        LEFT JOIN predictions p ON cast(p.ID_MATCH as char) = ws.ID_MATCH
    """

    df = read_sql_query(BDD, query)
    if df is None or df.empty:
        return pd.DataFrame()

    # Keep most recently updated rows first for monitoring.
    try:
        df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
        df = df.sort_values("updated_at", ascending=False)
    except Exception:
        logger.exception("load_ws_odds_monitor: failed to sort updated_at")
    return df.reset_index(drop=True)
