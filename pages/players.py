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
try:
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
except Exception:
    pass

with st.sidebar:
    st.markdown("### Filtres")
    min_n = st.slider("Min paris par joueur", 1, 50, 5)


# ---------------------------------------------------------------------------
# Aggregation par joueur
# ---------------------------------------------------------------------------
def aggregate(df_in: pd.DataFrame) -> pd.DataFrame:
    a = (
        df_in.groupby("player_bet", dropna=True)
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
    a["ROI %"] = np.where(a["Mises"] > 0, a["Gains"] / a["Mises"] * 100, 0.0)
    a["ROI attendu %"] = np.where(
        a["Mises"] > 0, a["Marges"] / a["Mises"] * 100, 0.0
    )
    a["Edge"] = a["ROI %"] - a["ROI attendu %"]
    a["Winrate %"] = np.where(a["n"] > 0, a["Wins"] / a["n"] * 100, 0.0)
    a = a.rename(columns={"player_bet": "Joueur", "n": "Nb paris"})
    return a


agg = aggregate(df)
agg = agg[agg["Nb paris"] >= int(min_n)].copy()
if agg.empty:
    st.info("Filtres trop restrictifs.")
    st.stop()

# ---------------------------------------------------------------------------
# Headline KPIs
# ---------------------------------------------------------------------------
st.markdown("### 🎯 Vue d'ensemble joueurs")

best_roi = agg.loc[agg["ROI %"].idxmax()]
worst_roi = agg.loc[agg["ROI %"].idxmin()]
top_gain = agg.loc[agg["Gains"].idxmax()]
profitable = int((agg["ROI %"] > 0).sum())

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Joueurs analysés", fmt_num(len(agg)))
k2.metric(
    "Profitables",
    f"{profitable} / {len(agg)}",
    delta=f"{profitable/len(agg)*100:.0f}%",
)
k3.metric(
    "👑 Meilleur ROI",
    str(best_roi["Joueur"]),
    delta=f"{best_roi['ROI %']:+.1f}% ({int(best_roi['Nb paris'])} paris)",
)
k4.metric(
    "💰 Top gains",
    str(top_gain["Joueur"]),
    delta=fmt_eur(top_gain["Gains"], sign=True),
)
k5.metric(
    "💀 Pire ROI",
    str(worst_roi["Joueur"]),
    delta=f"{worst_roi['ROI %']:+.1f}% ({int(worst_roi['Nb paris'])} paris)",
    delta_color="inverse",
)

st.divider()

# ---------------------------------------------------------------------------
# Scatter Volume × ROI (sweet spots)
# ---------------------------------------------------------------------------
st.markdown("### 🫧 Volume vs Performance")
st.caption(
    "Chaque bulle = un joueur. Taille = mises totales, couleur = Edge "
    "(ROI réel − ROI attendu). Les bulles vertes en haut à droite = sweet spots."
)

fig_sc = px.scatter(
    agg,
    x="Nb paris",
    y="ROI %",
    size="Mises",
    color="Edge",
    color_continuous_scale=[(0.0, "#e04e4e"), (0.5, "#9ca3af"), (1.0, "#32b296")],
    color_continuous_midpoint=0,
    hover_name="Joueur",
    custom_data=["Mises", "Gains", "Winrate %", "Edge", "AvgCote"],
    size_max=40,
)
fig_sc.update_traces(
    hovertemplate=(
        "<b>%{hovertext}</b><br>"
        "Paris : %{x}<br>"
        "ROI : %{y:+.2f}%<br>"
        "Mises : %{customdata[0]:.0f}€<br>"
        "Gains : %{customdata[1]:+.0f}€<br>"
        "Winrate : %{customdata[2]:.1f}%<br>"
        "Edge : %{customdata[3]:+.2f}%<br>"
        "Cote moy. : %{customdata[4]:.2f}<extra></extra>"
    ),
    marker=dict(line=dict(width=0.5, color="rgba(255,255,255,0.2)")),
)
fig_sc.add_hline(y=0, line_color="#4b5563", line_dash="dash")
fig_sc.update_layout(
    height=460,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#d1d4dc"),
    margin=dict(t=20, b=40, l=60, r=20),
)
fig_sc.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
fig_sc.update_yaxes(title_text="ROI (%)", gridcolor="rgba(100,100,120,0.15)")
st.plotly_chart(fig_sc, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Top K
# ---------------------------------------------------------------------------
def _bar(data: pd.DataFrame, title: str, sort_by: str) -> go.Figure:
    if sort_by == "Nb paris":
        x_vals = data["Nb paris"]
        text = [f"{int(v)}" for v in x_vals]
        colors = ["#3b82f6"] * len(data)
    else:  # Gains ou Perte → on affiche Gains (signé)
        x_vals = data["Gains"]
        text = [f"{v:+.0f}€" for v in x_vals]
        colors = ["#32b296" if v >= 0 else "#e04e4e" for v in x_vals]

    fig = go.Figure(
        go.Bar(
            x=x_vals,
            y=data["Joueur"],
            orientation="h",
            marker_color=colors,
            text=text,
            textposition="outside",
            customdata=np.stack(
                [data["Nb paris"], data["Mises"], data["Winrate %"], data["ROI %"]],
                axis=-1,
            ),
            hovertemplate=(
                "%{y}<br>%{x}<br>n : %{customdata[0]}"
                "<br>Mises : %{customdata[1]:.0f}€"
                "<br>Winrate : %{customdata[2]:.1f}%"
                "<br>ROI : %{customdata[3]:+.1f}%<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=max(300, 30 * len(data)),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=40, b=30, l=20, r=80),
        yaxis=dict(autorange="reversed"),
        title=dict(text=title, font=dict(color="#9ca3af", size=14)),
    )
    return fig


# Sélecteur de tri au-dessus du Top K
players_full = agg["Joueur"].tolist()
tsel1, tsel2 = st.columns([2, 2])
with tsel1:
    sort_by = st.selectbox(
        "Classement par", ["Nb paris", "Gains", "Perte"], index=0, key="sort_by"
    )
with tsel2:
    top_k = st.slider("Top K", 5, 50, 10, key="top_k")

# Tri d'agg selon le choix utilisateur
if sort_by == "Perte":
    agg = agg.sort_values("Gains", ascending=True)
elif sort_by == "Gains":
    agg = agg.sort_values("Gains", ascending=False)
else:
    agg = agg.sort_values("Nb paris", ascending=False)
top = agg.head(top_k).copy()

title_map = {
    "Nb paris": f"📊 Top {top_k} — Nombre de paris",
    "Gains": f"💰 Top {top_k} — Plus gros gains",
    "Perte": f"💀 Top {top_k} — Plus grosses pertes",
}
st.plotly_chart(_bar(top, title_map[sort_by], sort_by), width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Tableau complet (replié)
# ---------------------------------------------------------------------------
with st.expander("📋 Tableau complet de tous les joueurs", expanded=False):
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

# ---------------------------------------------------------------------------
# Drilldown / comparaison
# ---------------------------------------------------------------------------
st.markdown("### 🔍 Détail joueur")

dsel1, dsel2, dsel3 = st.columns([3, 3, 2])
with dsel1:
    sel_a = st.selectbox(
        "Joueur à analyser", options=players_full, index=0, key="pl_a"
    )
with dsel2:
    sel_b_choice = st.selectbox(
        "Comparer avec (optionnel)", options=["—"] + players_full, index=0, key="pl_b"
    )
with dsel3:
    rolling_w = st.slider("Fenêtre forme (paris)", 3, 30, 10, 1)
sel_b = None if sel_b_choice == "—" else sel_b_choice


def _player_subset(player: str) -> pd.DataFrame:
    sub = df[df["player_bet"] == player].copy()
    sub = sub.sort_values("Date")
    sub["_unit"] = np.where(sub["Mise"] > 0, sub["Gains net"] / sub["Mise"], 0.0)
    sub["_cum"] = sub["Gains net"].cumsum()
    minp = max(1, rolling_w // 2)
    sub["_roll_roi"] = (
        sub["_unit"].rolling(rolling_w, min_periods=minp).mean() * 100
    )
    return sub


def _player_kpis(sub: pd.DataFrame, label: str) -> None:
    n = len(sub)
    mises = sub["Mise"].sum()
    gains = sub["Gains net"].sum()
    roi = (gains / mises * 100) if mises > 0 else 0.0
    winrate = (sub["Gains net"] > 0).mean() * 100 if n > 0 else 0.0
    avg_cote = sub["Cote"].mean() if n > 0 else 0.0
    st.markdown(f"**{label}**")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Paris", fmt_num(n))
    m2.metric("Mises", fmt_eur(mises))
    m3.metric("Gains", fmt_eur(gains, sign=True))
    m4.metric("ROI", f"{roi:+.1f}%")
    m5.metric("Winrate / Cote moy.", f"{winrate:.0f}% / {avg_cote:.2f}")


sub_a = _player_subset(sel_a)
sub_b = _player_subset(sel_b) if sel_b else None

_player_kpis(sub_a, f"🎾 {sel_a}")
if sub_b is not None:
    _player_kpis(sub_b, f"🎾 {sel_b}")

# --- Cumul gains
fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=sub_a["Date"],
        y=sub_a["_cum"],
        mode="lines+markers",
        name=sel_a,
        line=dict(color="#3b82f6"),
        marker=dict(size=4),
        fill="tozeroy",
        fillcolor="rgba(59,130,246,0.10)",
        hovertemplate="%{x}<br>Cumul : %{y:+.0f}€<extra></extra>",
    )
)
if sub_b is not None and not sub_b.empty:
    fig.add_trace(
        go.Scatter(
            x=sub_b["Date"],
            y=sub_b["_cum"],
            mode="lines+markers",
            name=sel_b,
            line=dict(color="#fbbf24"),
            marker=dict(size=4),
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
    title=dict(text="Cumul des gains", font=dict(color="#9ca3af", size=14), x=0.5),
    legend=dict(orientation="h", y=1.12, x=0.5, xanchor="center"),
)
fig.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
fig.update_yaxes(title_text="Gains cumulés (€)", gridcolor="rgba(100,100,120,0.15)")
st.plotly_chart(fig, width="stretch")

# --- Forme glissante
fig_form = go.Figure()
fig_form.add_trace(
    go.Scatter(
        x=sub_a["Date"],
        y=sub_a["_roll_roi"],
        mode="lines",
        name=sel_a,
        line=dict(color="#3b82f6", width=2),
    )
)
if sub_b is not None and not sub_b.empty:
    fig_form.add_trace(
        go.Scatter(
            x=sub_b["Date"],
            y=sub_b["_roll_roi"],
            mode="lines",
            name=sel_b,
            line=dict(color="#fbbf24", width=2),
        )
    )
fig_form.add_hline(y=0, line_color="#4b5563", line_dash="dash")
fig_form.update_layout(
    height=280,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#d1d4dc"),
    margin=dict(t=30, b=30, l=60, r=20),
    title=dict(
        text=f"Forme : ROI glissant ({rolling_w} paris)",
        font=dict(color="#9ca3af", size=14),
        x=0.5,
    ),
    legend=dict(orientation="h", y=1.18, x=0.5, xanchor="center"),
)
fig_form.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
fig_form.update_yaxes(title_text="ROI glissant (%)", gridcolor="rgba(100,100,120,0.15)")
st.plotly_chart(fig_form, width="stretch")

# --- Splits en onglets : cote / round / surface
COTE_BINS = [1.0, 1.5, 1.8, 2.2, 3.0, 5.0, 100.0]
COTE_LABELS = ["≤1.50", "1.50-1.80", "1.80-2.20", "2.20-3.00", "3.00-5.00", ">5.00"]


def _breakdown(sub: pd.DataFrame, by: str) -> pd.DataFrame:
    if by == "_cote_bin":
        s = sub.copy()
        s["_cote_bin"] = pd.cut(s["Cote"], bins=COTE_BINS, labels=COTE_LABELS)
        s = s.dropna(subset=["_cote_bin"])
        group_key = "_cote_bin"
    else:
        if by not in sub.columns:
            return pd.DataFrame()
        s = sub
        group_key = by
    g = (
        s.groupby(group_key, observed=True, dropna=True)
        .agg(n=("Mise", "size"), Mises=("Mise", "sum"), Gains=("Gains net", "sum"))
        .reset_index()
    )
    g["ROI %"] = np.where(g["Mises"] > 0, g["Gains"] / g["Mises"] * 100, 0.0)
    g = g.rename(columns={group_key: "_x"})
    return g


def _grouped_chart(by: str, title: str, x_label: str) -> go.Figure | None:
    a = _breakdown(sub_a, by)
    if a.empty:
        return None
    a["Joueur"] = sel_a
    frames = [a]
    if sub_b is not None and not sub_b.empty:
        b = _breakdown(sub_b, by)
        if not b.empty:
            b["Joueur"] = sel_b
            frames.append(b)
    merged = pd.concat(frames, ignore_index=True)
    color_map = {sel_a: "#3b82f6"}
    if sel_b:
        color_map[sel_b] = "#fbbf24"
    fig_g = px.bar(
        merged,
        x="_x",
        y="ROI %",
        color="Joueur",
        barmode="group",
        text=merged["ROI %"].map(lambda v: f"{v:+.1f}%"),
        color_discrete_map=color_map,
        custom_data=["n", "Mises", "Gains"],
    )
    fig_g.update_traces(
        textposition="outside",
        hovertemplate=(
            "%{x}<br>ROI : %{y:+.1f}%<br>n : %{customdata[0]}"
            "<br>Mises : %{customdata[1]:.0f}€"
            "<br>Gains : %{customdata[2]:+.0f}€<extra></extra>"
        ),
    )
    fig_g.add_hline(y=0, line_color="#4b5563", line_dash="dash")
    fig_g.update_layout(
        height=360,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=40, b=30, l=60, r=20),
        title=dict(text=title, font=dict(color="#9ca3af", size=14), x=0.5),
        legend=dict(orientation="h", y=1.15, x=0.5, xanchor="center"),
        xaxis_title=x_label,
    )
    fig_g.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
    fig_g.update_yaxes(gridcolor="rgba(100,100,120,0.15)")
    return fig_g


tab_cote, tab_round, tab_surf = st.tabs(
    ["🎲 Par tranche de cote", "🥇 Par round", "🏟 Par surface"]
)
with tab_cote:
    f = _grouped_chart("_cote_bin", "ROI par tranche de cote", "Cote")
    if f is not None:
        st.plotly_chart(f, width="stretch")
    else:
        st.info("Pas de données.")
with tab_round:
    f = _grouped_chart("Round", "ROI par round", "Round")
    if f is not None:
        st.plotly_chart(f, width="stretch")
    else:
        st.info("Pas de données 'Round'.")
with tab_surf:
    f = _grouped_chart("Surface", "ROI par surface", "Surface")
    if f is not None:
        st.plotly_chart(f, width="stretch")
    else:
        st.info("Pas de données 'Surface'.")
