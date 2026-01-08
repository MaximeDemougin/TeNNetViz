# ruff: noqa: E402
import streamlit as st
import pandas as pd
import numpy as np

import sys

sys.path.append(st.session_state["project_path"])
from db_utils.db_utils import read_sql_query

BDD = "TeNNet"


def load_bankroll(user_id: int):
    """
    Loads the bankroll for a given user from the database.
    """
    query_bankroll = f"""SELECT bankroll FROM FootNet.Users WHERE ID_USER = {user_id}"""
    bankroll_data = read_sql_query(BDD, query_bankroll)
    if not bankroll_data.empty:
        st.session_state["bankroll"] = int(bankroll_data["bankroll"].values[0])
    else:
        st.session_state["bankroll"] = 0
    return st.session_state["bankroll"]


def load_bets(user_id: int):
    """
    Loads the bets_data for a given user from the database.
    """
    query_bets = """SELECT b.*,
                            tourney_name,
                            tourney_level,
                            winner_name,
                            loser_name,
                            round,
                            surface,
                            match_settled,
                            tourney_date,
                            winner_pred,
                            loser_pred,
                            'doubles' = TRUE as doubles,
                            'atp' as compet
                                    FROM Bet b join men_matchs m on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE match_settled in (1,2) and score != 'W/O'
                    UNION
                        SELECT b.*,
                            tourney_name,
                            tourney_level,
                            winner_name,
                            loser_name,
                            round,
                            surface,
                            match_settled,
                            tourney_date,
                            winner_pred,
                            loser_pred,
                            'doubles' = TRUE as doubles,
                            'wta' as compet
                                    FROM  Bet b join women_matchs m on (b.ID_MATCH = m.ID_MATCH)
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE  match_settled in (1,2) and score != 'W/O'
                    UNION
                        SELECT b.*, 
                                tourney_name,
                                tourney_level,
                                concat(winner_name1,'/',winner_name2) as winner_name,
                                concat(loser_name1,'/',loser_name2)  as loser_name,
                                round,
                                surface,
                                match_settled, 
                                tourney_date, 
                                winner_pred,
                                loser_pred,
                                'doubles' = FALSE as doubles  ,
                                'doubles' as compet
                                    FROM Bet b join double_matchs m  on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE match_settled in (1,2) and score != 'W/O'"""
    bets_data = read_sql_query(BDD, query_bets)
    bets_data = bets_data[
        (bets_data["ID_USER"] == user_id) & (bets_data["tourney_date"] >= "2026-01-01")
    ]
    bets_data.sort_values(by="tourney_date", ascending=True, inplace=True)
    bets_data.reset_index(drop=True, inplace=True)
    return bets_data


def prepare_bets_data(user_id: int, finished: bool = True):
    """
    Groups bets_data by player beted and calculates total amount beted and won/lost.
    """

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
        ]
        empty_df = pd.DataFrame(columns=cols)
        # Ensure numeric columns exist with float dtype
        for num_col in ["Mise", "Cote", "Prédiction", "Gains net", "Marge attendue"]:
            empty_df[num_col] = empty_df.get(num_col, pd.Series(dtype=float)).astype(
                float
            )
        # Add cumulative column expected by prep_candle_data
        empty_df["Cumulative Gains"] = empty_df["Gains net"].cumsum()
        return empty_df

    bets_data["Match"] = bets_data["winner_name"] + " - " + bets_data["loser_name"]
    bets_data["real_odds"] = (1 / (bets_data["odds"] - 1)) * 0.97 + 1

    if finished:
        bets_data["cote_pred"] = np.where(
            (bets_data["match_settled"] == 1) & (bets_data["bet"] == 1)
            | (bets_data["match_settled"] == 2) & (bets_data["bet"] == 0),
            bets_data["winner_pred"],
            bets_data["loser_pred"],
        )
        bets_data["player_bet"] = np.where(
            bets_data["bet"] == 1, bets_data["winner_name"], bets_data["loser_name"]
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
    else:
        bets_data["cote_pred"] = np.where(
            bets_data["bet"] == 1, bets_data["winner_pred"], bets_data["loser_pred"]
        )
        bets_data["player_bet"] = np.where(
            bets_data["bet"] == 1, bets_data["winner_name"], bets_data["loser_name"]
        )
        bets_data["net_gain"] = 0.0
        bets_data["net_unit"] = 0.0
    bets_data["marge_unit"] = bets_data["real_odds"] / bets_data["cote_pred"] - 1
    bets_data["marge"] = bets_data["marge_unit"] * bets_data["stake"]
    prepared_bets = bets_data[
        [
            "ID_MATCH",
            "Match",
            "tourney_date",
            "compet",
            "surface",
            "tourney_level",
            "player_bet",
            "stake",
            "round",
            "real_odds",
            "cote_pred",
            "net_gain",
            "marge",
        ]
    ].copy()
    prepared_bets["compet"] = prepared_bets["compet"].str.title()

    # Extract time (Horaire) from tourney_date for display in match table
    try:
        prepared_bets["tourney_date"] = pd.to_datetime(
            prepared_bets["tourney_date"], errors="coerce"
        )
        prepared_bets["Horaire"] = prepared_bets["tourney_date"].dt.strftime("%H:%M")
    except Exception:
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
        pass

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
        pass

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
    except Exception:
        pass

    prepared_bets["real_odds"] = prepared_bets["real_odds"].round(3)
    prepared_bets["cote_pred"] = prepared_bets["cote_pred"].round(3)
    prepared_bets["marge"] = prepared_bets["marge"].round(2)
    prepared_bets["stake"] = prepared_bets["stake"].round(2)
    prepared_bets["net_gain"] = prepared_bets["net_gain"].round(2)
    prepared_bets.rename(
        columns={
            "tourney_date": "Date",
            "tourney_level": "Level",
            "compet": "Compétition",
            "surface": "Surface",
            "stake": "Mise",
            "round": "Round",
            "real_odds": "Cote",
            "cote_pred": "Prédiction",
            "net_gain": "Gains net",
            "marge": "Marge attendue",
        },
        inplace=True,
    )
    grouped_bets = (
        prepared_bets.groupby(["ID_MATCH", "Match", "player_bet"])
        .agg(
            {
                "Date": "first",
                "Compétition": "first",
                "Level": "first",
                "Round": "first",
                "Surface": "first",
                "Mise": "sum",
                "Cote": lambda x: np.average(
                    x, weights=prepared_bets.loc[x.index, "Mise"]
                ),
                "Prédiction": "mean",
                "Gains net": "sum",
                "Marge attendue": "sum",
            }
        )
        .reset_index()
    )
    grouped_bets["Cote"] = grouped_bets["Cote"].round(3)
    grouped_bets["Prédiction"] = grouped_bets["Prédiction"].round(3)
    grouped_bets["Marge attendue"] = grouped_bets["Marge attendue"].round(2)
    grouped_bets.sort_values(by="Date", ascending=True, inplace=True)
    grouped_bets.reset_index(drop=True, inplace=True)
    grouped_bets["Cumulative Gains"] = grouped_bets["Gains net"].cumsum()

    return grouped_bets


def prep_candle_data(user_id: int):
    """
    Prepares data for candlestick chart visualization grouped by day
    and uses cumulative net gains.
    """
    bets_data = prepare_bets_data(user_id)
    bets_data["Date"] = pd.to_datetime(bets_data["Date"]).dt.date

    candle_data = (
        bets_data.groupby("Date")
        .agg(
            open=("Cumulative Gains", "first"),
            high=("Cumulative Gains", "max"),
            low=("Cumulative Gains", "min"),
            close=("Cumulative Gains", "last"),
        )
        .reset_index()
    )

    # rename columns
    candle_data.rename(columns={"Date": "time"}, inplace=True)

    # round values
    for col in ["open", "high", "low", "close"]:
        candle_data[col] = candle_data[col].round(2)

    # convert time to string format YYYY-MM-DD
    candle_data["time"] = candle_data["time"].astype(str)

    # directly return JSON string
    candle_data_list = candle_data.to_dict(orient="records")
    return candle_data_list


def load_inplay_bets(user_id: int):
    """
    Loads the bets_data for a given user from the database.
    """
    query_bets = """SELECT b.*,
                            tourney_name,
                            tourney_level,
                            winner_name,
                            loser_name,
                            round,
                            surface,
                            match_settled,
                            tourney_date,
                            winner_pred,
                            loser_pred,
                            'doubles' = TRUE as doubles,
                            'atp' as compet
                                    FROM Bet b join men_matchs m on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE not match_settled in (1,2)
                    UNION
                        SELECT b.*,
                            tourney_name,
                            tourney_level,
                            winner_name,
                            loser_name,
                            round,
                            surface,
                            match_settled,
                            tourney_date,
                            winner_pred,
                            loser_pred,
                            'doubles' = TRUE as doubles,
                            'wta' as compet
                                    FROM  Bet b join women_matchs m on (b.ID_MATCH = m.ID_MATCH)
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE  not match_settled in (1,2)
                    UNION
                        SELECT b.*, 
                                tourney_name,
                                tourney_level,
                                concat(winner_name1,'/',winner_name2) as winner_name,
                                concat(loser_name1,'/',loser_name2)  as loser_name,
                                round,
                                surface,
                                match_settled, 
                                tourney_date, 
                                winner_pred,
                                loser_pred,
                                'doubles' = FALSE as doubles  ,
                                'doubles' as compet
                                    FROM Bet b join double_matchs m  on (b.ID_MATCH = m.ID_MATCH) 
                                        right join predictions p on (m.ID_MATCH = p.ID_MATCH)
                                        WHERE not match_settled in (1,2)"""
    bets_data = read_sql_query(BDD, query_bets)
    bets_data = bets_data[(bets_data["ID_USER"] == user_id)]
    bets_data.sort_values(by="tourney_date", ascending=True, inplace=True)
    bets_data.reset_index(drop=True, inplace=True)
    return bets_data
