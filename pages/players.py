# ruff: noqa: E402
"""Page Player Analytics : performance par joueur sur lequel on parie."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data import prepare_bets_data
from utils import csv_download_button, fmt_eur, fmt_num


st.set_page_config(
    layout="wide", page_icon="logo_TeNNet.png", page_title="Player Analytics"
)
st.title("👤 Player Analytics")
st.caption("Sur quels joueurs ai-je un edge ?")

if not st.session_state.get("logged_in", False):
    st.info("Veuillez vous connecter.")
    st.stop()

bets_data = st.session_state.get("bets_data_cached")
if bets_data is None:
    bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=True)

if bets_data is None or bets_data.empty:
    st.info("Aucune donnée disponible.")
    st.stop()

df = bets_data.copy()
if "player_bet" not in df.columns:
    st.error("Colonne 'player_bet' manquante.")
    st.stop()

df["Mise"] = pd.to_numeric(df["Mise"], errors="coerce").fillna(0.0)
df["Gains net"] = pd.to_numeric(df["Gains net"], errors="coerce").fillna(0.0)
df["Marge attendue"] = pd.to_numeric(df["Marge attendue"], errors="coerce").fillna(0.0)
df["Cote"] = pd.to_numeric(df["Cote"], errors="coerce")

with st.sidebar:
    st.markdown("### Filtres")
    min_n = st.slider("Min paris par joueur", 1, 50, 5)
    sort_by = st.selectbox(
        "Trier par", ["ROI %", "Gains", "Mises", "Nb paris", "Edge"], index=0
    )
    top_k = st.slider("Top / Bottom K", 5, 50, 10)

agg = (
    df.groupby("player_bet", dropna=True)
    .agg(
        n=("Mise", "size"),
        Mises=("Mise", "sum"),
        Gains=("Gains net", "sum"),
        Marges=("Marge attendue", "sum"),
        Wins=("Gains net", lambda x: int((x > 0).sum())),
        AvgCote=("Cote", "mean"),
    )
    .reset_index()
)
agg = agg[agg["n"] >= int(min_n)].copy()
if agg.empty:
    st.info("Filtres trop restrictifs.")
    st.stop()

agg["ROI %"] = np.where(agg["Mises"] > 0, agg["Gains"] / agg["Mises"] * 100, 0.0)
agg["ROI attendu %"] = np.where(
    agg["Mises"] > 0, agg["Marges"] / agg["Mises"] * 100, 0.0
)
agg["Edge"] = agg["ROI %"] - agg["ROI attendu %"]
agg["Winrate %"] = np.where(agg["n"] > 0, agg["Wins"] / agg["n"] * 100, 0.0)
agg = agg.rename(columns={"player_bet": "Joueur", "n": "Nb paris"})

sort_col_map = {
    "ROI %": "ROI %",
    "Gains": "Gains",
    "Mises": "Mises",
    "Nb paris": "Nb paris",
    "Edge": "Edge",
}
agg = agg.sort_values(sort_col_map[sort_by], ascending=False)

top = agg.head(top_k).copy()
bottom = agg.tail(top_k).sort_values(sort_col_map[sort_by], ascending=True).copy()

# --- Top / Bottom bars ---
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"#### 🏆 Top {top_k} ({sort_by})")
    fig = go.Figure(
        go.Bar(
            x=top[sort_col_map[sort_by]],
            y=top["Joueur"],
            orientation="h",
            marker_color=[
                "#32b296" if v >= 0 else "#e04e4e" for v in top[sort_col_map[sort_by]]
            ],
            text=[
                f"{v:+.1f}%" if "%" in sort_by else f"{v:+.0f}€"
                for v in top[sort_col_map[sort_by]]
            ],
            textposition="outside",
            customdata=np.stack(
                [top["Nb paris"], top["Mises"], top["Winrate %"]], axis=-1
            ),
            hovertemplate="%{y}<br>%{x}<br>n : %{customdata[0]}<br>Mises : %{customdata[1]:.0f}€<br>Winrate : %{customdata[2]:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(300, 30 * len(top)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=30, b=30, l=20, r=80),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, width="stretch")

with c2:
    st.markdown(f"#### 💀 Bottom {top_k} ({sort_by})")
    fig = go.Figure(
        go.Bar(
            x=bottom[sort_col_map[sort_by]],
            y=bottom["Joueur"],
            orientation="h",
            marker_color=[
                "#32b296" if v >= 0 else "#e04e4e"
                for v in bottom[sort_col_map[sort_by]]
            ],
            text=[
                f"{v:+.1f}%" if "%" in sort_by else f"{v:+.0f}€"
                for v in bottom[sort_col_map[sort_by]]
            ],
            textposition="outside",
            customdata=np.stack(
                [bottom["Nb paris"], bottom["Mises"], bottom["Winrate %"]], axis=-1
            ),
            hovertemplate="%{y}<br>%{x}<br>n : %{customdata[0]}<br>Mises : %{customdata[1]:.0f}€<br>Winrate : %{customdata[2]:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(300, 30 * len(bottom)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=30, b=30, l=20, r=80),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, width="stretch")

st.divider()

# --- Tableau complet ---
st.markdown("### 📋 Tous les joueurs")
styled = agg.style.format(
    {
        "Mises": lambda v: fmt_eur(v),
        "Gains": lambda v: fmt_eur(v, sign=True),
        "Marges": lambda v: fmt_eur(v, sign=True),
        "AvgCote": "{:.2f}",
        "ROI %": "{:+.1f}%",
        "ROI attendu %": "{:+.1f}%",
        "Edge": "{:+.1f}%",
        "Winrate %": "{:.1f}%",
    }
).map(
    lambda v: (
        "color: #32b296; font-weight:700;"
        if isinstance(v, (int, float)) and v > 0
        else "color: #e04e4e; font-weight:700;"
    ),
    subset=["ROI %", "Gains", "Edge"],
)
st.dataframe(styled, width="stretch", hide_index=True)
csv_download_button(
    agg, label="📥 Exporter CSV", filename="players.csv", key="players_csv"
)

st.divider()

# --- Drilldown sur un joueur ---
st.markdown("### 🔍 Détail d'un joueur")
players = agg["Joueur"].tolist()
sel = st.selectbox("Choisir un joueur", options=players, index=0 if players else None)

if sel:
    sub = df[df["player_bet"] == sel].copy()
    try:
        sub["Date"] = pd.to_datetime(sub["Date"], errors="coerce")
    except Exception:
        pass
    sub = sub.sort_values("Date")

    n = len(sub)
    mises = sub["Mise"].sum()
    gains = sub["Gains net"].sum()
    roi = (gains / mises * 100) if mises > 0 else 0
    winrate = (sub["Gains net"] > 0).mean() * 100 if n > 0 else 0

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Paris", fmt_num(n))
    m2.metric("Mises", fmt_eur(mises))
    m3.metric("Gains", fmt_eur(gains, sign=True))
    m4.metric("ROI", f"{roi:+.1f}%")
    m5.metric("Winrate", f"{winrate:.1f}%")

    # Cumulative gains
    sub["_cum"] = sub["Gains net"].cumsum()
    fig = go.Figure(
        go.Scatter(
            x=sub["Date"],
            y=sub["_cum"],
            mode="lines+markers",
            line=dict(color="#3b82f6"),
            marker=dict(size=4),
            fill="tozeroy",
            fillcolor="rgba(59,130,246,0.1)",
            hovertemplate="%{x}<br>Cumul : %{y:+.0f}€<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_color="#4b5563", line_dash="dash")
    fig.update_layout(
        height=320,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=30, b=30, l=60, r=20),
        title=dict(
            text=f"Cumul des gains — {sel}", font=dict(color="#9ca3af", size=14), x=0.5
        ),
    )
    fig.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
    fig.update_yaxes(title_text="Gains cumulés (€)", gridcolor="rgba(100,100,120,0.15)")
    st.plotly_chart(fig, width="stretch")

    # Surface specialization
    if "Surface" in sub.columns and sub["Surface"].notna().any():
        surf_agg = (
            sub.groupby("Surface")
            .agg(n=("Mise", "size"), Mises=("Mise", "sum"), Gains=("Gains net", "sum"))
            .reset_index()
        )
        surf_agg["ROI %"] = np.where(
            surf_agg["Mises"] > 0, surf_agg["Gains"] / surf_agg["Mises"] * 100, 0.0
        )
        fig2 = px.bar(
            surf_agg,
            x="Surface",
            y="ROI %",
            text=surf_agg["ROI %"].map(lambda v: f"{v:+.1f}%"),
            color=surf_agg["ROI %"].map(lambda v: "Pos" if v >= 0 else "Neg"),
            color_discrete_map={"Pos": "#32b296", "Neg": "#e04e4e"},
            custom_data=["n", "Mises", "Gains"],
        )
        fig2.update_traces(
            textposition="outside",
            hovertemplate="%{x}<br>ROI : %{y:+.1f}%<br>n : %{customdata[0]}<br>Mises : %{customdata[1]:.0f}€<br>Gains : %{customdata[2]:+.0f}€<extra></extra>",
        )
        fig2.update_layout(
            height=320,
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            margin=dict(t=30, b=30, l=60, r=20),
            title=dict(
                text=f"ROI par surface — {sel}",
                font=dict(color="#9ca3af", size=14),
                x=0.5,
            ),
        )
        fig2.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
        fig2.update_yaxes(gridcolor="rgba(100,100,120,0.15)")
        st.plotly_chart(fig2, width="stretch")
