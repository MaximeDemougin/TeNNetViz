"""Auto-insights panel.

Scans bets_data across multiple dimensions (Surface, Type de tournoi, Round,
Compétition, Cote bucket) and surfaces the segments with the strongest /
weakest ROI, gated by a minimum sample size.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import streamlit as st

from utils import fmt_eur


logger = logging.getLogger(__name__)


_DIMENSIONS = [
    ("Surface", "Surface"),
    ("Type de tournoi", "Type de tournoi"),
    ("Round", "Round"),
    ("Compétition", "Compétition"),
]


def _cote_bucket(c: float) -> str:
    if pd.isna(c):
        return None
    if c < 1.5:
        return "Cote < 1.5"
    if c < 2.0:
        return "Cote 1.5–2.0"
    if c < 2.5:
        return "Cote 2.0–2.5"
    if c < 3.5:
        return "Cote 2.5–3.5"
    return "Cote ≥ 3.5"


def _segment_stats(
    df: pd.DataFrame, dim_label: str, dim_col: str, min_n: int
) -> pd.DataFrame:
    if dim_col not in df.columns:
        return pd.DataFrame()
    g = (
        df.dropna(subset=[dim_col])
        .groupby(dim_col, dropna=True)
        .agg(
            n=("Mise", "size"),
            mises=("Mise", "sum"),
            gains=("Gains net", "sum"),
            marges=("Marge attendue", "sum"),
        )
        .reset_index()
    )
    if g.empty:
        return g
    g = g[g["n"] >= min_n].copy()
    if g.empty:
        return g
    g["ROI"] = np.where(g["mises"] > 0, g["gains"] / g["mises"] * 100.0, 0.0)
    g["ROI_attendu"] = np.where(g["mises"] > 0, g["marges"] / g["mises"] * 100.0, 0.0)
    g["Edge"] = g["ROI"] - g["ROI_attendu"]
    g["dim"] = dim_label
    g = g.rename(columns={dim_col: "value"})
    return g[["dim", "value", "n", "mises", "gains", "ROI", "ROI_attendu", "Edge"]]


def _build_insights(bets_data: pd.DataFrame, min_n: int = 10) -> pd.DataFrame:
    if bets_data is None or bets_data.empty:
        return pd.DataFrame()
    df = bets_data.copy()
    # Cote bucket synthetic dim
    if "Cote" in df.columns:
        df["_cote_bucket"] = pd.to_numeric(df["Cote"], errors="coerce").map(
            _cote_bucket
        )
    rows = []
    dims = list(_DIMENSIONS)
    if "_cote_bucket" in df.columns:
        dims.append(("Cote", "_cote_bucket"))
    for label, col in dims:
        try:
            stats = _segment_stats(df, label, col, min_n=min_n)
            if not stats.empty:
                rows.append(stats)
        except Exception:
            logger.exception("insights: segment failed for %s", col)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _card_html(row: pd.Series, kind: str) -> str:
    color = "#32b296" if kind == "best" else "#e04e4e"
    accent = "rgba(50,178,150,0.15)" if kind == "best" else "rgba(224,78,78,0.15)"
    arrow = "▲" if kind == "best" else "▼"
    sign = "+" if row["ROI"] >= 0 else ""
    edge_sign = "+" if row["Edge"] >= 0 else ""
    return f"""
    <div style="
        background: linear-gradient(135deg, rgba(30,30,35,0.95) 0%, rgba(20,20,25,0.98) 100%);
        border: 1px solid {accent};
        border-left: 3px solid {color};
        border-radius: 10px;
        padding: 12px 14px;
        margin-bottom: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    ">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
            <div style="font-size:0.78rem; color:#9ca3af; text-transform:uppercase; letter-spacing:0.04em;">
                {row['dim']}
            </div>
            <div style="font-size:0.72rem; color:#9ca3af;">
                n={int(row['n'])}
            </div>
        </div>
        <div style="font-size:1.0rem; color:#e5e7eb; font-weight:600; margin:4px 0 6px 0;">
            {row['value']}
        </div>
        <div style="display:flex; justify-content:space-between; align-items:baseline;">
            <div style="font-size:1.4rem; color:{color}; font-weight:700;">
                {arrow} {sign}{row['ROI']:.1f}%
            </div>
            <div style="font-size:0.75rem; color:#9ca3af;">
                Edge {edge_sign}{row['Edge']:.1f}pt
            </div>
        </div>
        <div style="font-size:0.72rem; color:#6b7280; margin-top:4px;">
            Mises {fmt_eur(row['mises'])} · Gains {fmt_eur(row['gains'], sign=True)}
        </div>
    </div>
    """


def render_insights_panel(bets_data: pd.DataFrame, min_n: int = 10, top_k: int = 3):
    """Render best / worst segment cards. Stays silent if no data qualifies."""
    insights = _build_insights(bets_data, min_n=min_n)
    if insights.empty:
        st.info(
            f"Pas assez de paris pour générer des insights (≥ {min_n} par segment)."
        )
        return

    best = insights.sort_values("ROI", ascending=False).head(top_k)
    worst = insights.sort_values("ROI", ascending=True).head(top_k)

    # Drop overlap: if any worst row is also in best (small dataset), keep best.
    worst = worst[~worst.index.isin(best.index)]

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown(
            "<div style='font-size:0.95rem; color:#32b296; font-weight:600; margin-bottom:6px;'>"
            "🟢 Tes points forts</div>",
            unsafe_allow_html=True,
        )
        if best.empty:
            st.caption("Rien à signaler.")
        else:
            for _, row in best.iterrows():
                st.markdown(_card_html(row, "best"), unsafe_allow_html=True)

    with col_r:
        st.markdown(
            "<div style='font-size:0.95rem; color:#e04e4e; font-weight:600; margin-bottom:6px;'>"
            "🔴 À surveiller</div>",
            unsafe_allow_html=True,
        )
        if worst.empty:
            st.caption("Rien à signaler.")
        else:
            for _, row in worst.iterrows():
                st.markdown(_card_html(row, "worst"), unsafe_allow_html=True)
