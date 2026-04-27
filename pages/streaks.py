# ruff: noqa: E402
"""Page Streaks & Volatilité.

- Plus longues séries de victoires/défaites
- Distribution des longueurs de séries
- Plot séquentiel coloré + annotations des streaks notables
- Volatilité ROI rolling (30j)
- Drawdowns et recovery
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import prepare_bets_data
from utils import fmt_eur, fmt_num


st.set_page_config(
    layout="wide", page_icon="logo_TeNNet.png", page_title="Streaks & Volatilité"
)
st.title("🔥 Streaks & Volatilité")
st.caption("Hot streaks, cold streaks, drawdowns, et stabilité du ROI.")

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
try:
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
except Exception:
    pass
df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
df["Gains net"] = pd.to_numeric(df["Gains net"], errors="coerce").fillna(0.0)
df["Mise"] = pd.to_numeric(df["Mise"], errors="coerce").fillna(0.0)
df["win"] = (df["Gains net"] > 0).astype(int)


# --- Compute runs of wins / losses ---
def _runs(values: np.ndarray):
    """Yield (value, start_idx, length) for each run."""
    if len(values) == 0:
        return
    cur = values[0]
    start = 0
    for i in range(1, len(values)):
        if values[i] != cur:
            yield (cur, start, i - start)
            cur = values[i]
            start = i
    yield (cur, start, len(values) - start)


runs = list(_runs(df["win"].to_numpy()))
win_runs = [r for r in runs if r[0] == 1]
loss_runs = [r for r in runs if r[0] == 0]

longest_win = max((r[2] for r in win_runs), default=0)
longest_loss = max((r[2] for r in loss_runs), default=0)


def _run_to_dates(run):
    s, length = run[1], run[2]
    e = s + length - 1
    return df["Date"].iloc[s], df["Date"].iloc[e]


lw_run = max(win_runs, key=lambda r: r[2]) if win_runs else None
ll_run = max(loss_runs, key=lambda r: r[2]) if loss_runs else None

m1, m2, m3, m4 = st.columns(4)
m1.metric("Plus longue série de wins", f"{longest_win}")
m2.metric("Plus longue série de losses", f"{longest_loss}")
if lw_run is not None:
    s, e = _run_to_dates(lw_run)
    m3.metric("Période hot streak", f"{s.date()} → {e.date()}")
if ll_run is not None:
    s, e = _run_to_dates(ll_run)
    m4.metric("Période cold streak", f"{s.date()} → {e.date()}")

st.divider()

# --- Sequential plot colored by win/loss ---
st.markdown("### 📍 Séquence des paris")
df_seq = df.copy()
df_seq["_idx"] = np.arange(len(df_seq))
fig = go.Figure()
fig.add_trace(
    go.Bar(
        x=df_seq["_idx"],
        y=df_seq["Gains net"],
        marker_color=["#32b296" if v > 0 else "#e04e4e" for v in df_seq["Gains net"]],
        customdata=np.stack(
            [df_seq["Date"].astype(str), df_seq["Mise"], df_seq["Cote"]], axis=-1
        ),
        hovertemplate="Pari #%{x}<br>%{customdata[0]}<br>Mise : %{customdata[1]:.0f}€<br>Cote : %{customdata[2]:.2f}<br>Gain : %{y:+.0f}€<extra></extra>",
        showlegend=False,
    )
)
# Annotate notable streaks
notable = [r for r in runs if r[2] >= 5]
notable.sort(key=lambda r: r[2], reverse=True)
for r in notable[:6]:
    val, s, length = r
    e = s + length - 1
    fig.add_vrect(
        x0=s - 0.5,
        x1=e + 0.5,
        fillcolor=("#32b296" if val == 1 else "#e04e4e"),
        opacity=0.08,
        line_width=0,
        annotation_text=f"{length}{'W' if val == 1 else 'L'}",
        annotation_position="top",
        annotation=dict(font=dict(color="#9ca3af", size=10)),
    )
fig.add_hline(y=0, line_color="#4b5563", line_dash="dash")
fig.update_layout(
    height=380,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#d1d4dc"),
    margin=dict(t=30, b=40, l=60, r=20),
)
fig.update_xaxes(title_text="Pari #", gridcolor="rgba(100,100,120,0.15)")
fig.update_yaxes(title_text="Gain net (€)", gridcolor="rgba(100,100,120,0.15)")
st.plotly_chart(fig, width="stretch")


# --- Distribution des longueurs de séries ---
st.markdown("### 📊 Distribution des longueurs de séries")
c1, c2 = st.columns(2)
for col, run_list, title, color in [
    (c1, win_runs, "Wins", "#32b296"),
    (c2, loss_runs, "Losses", "#e04e4e"),
]:
    with col:
        if not run_list:
            st.info(f"Aucune série de {title}.")
            continue
        lengths = [r[2] for r in run_list]
        hist = pd.Series(lengths).value_counts().sort_index()
        fig = go.Figure(
            go.Bar(
                x=hist.index.astype(str),
                y=hist.values,
                marker_color=color,
                hovertemplate=f"Série de %{{x}} {title}<br>Occurrences : %{{y}}<extra></extra>",
            )
        )
        fig.update_layout(
            height=300,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            margin=dict(t=30, b=30, l=60, r=20),
            title=dict(
                text=f"Séries de {title} consécutifs",
                font=dict(color="#9ca3af", size=14),
                x=0.5,
            ),
        )
        fig.update_xaxes(title_text="Longueur", gridcolor="rgba(100,100,120,0.15)")
        fig.update_yaxes(title_text="Occurrences", gridcolor="rgba(100,100,120,0.15)")
        st.plotly_chart(fig, width="stretch")


# --- Drawdown analysis ---
st.divider()
st.markdown("### 📉 Drawdown")
df["_cum"] = df["Gains net"].cumsum()
df["_peak"] = df["_cum"].cummax()
df["_dd"] = df["_cum"] - df["_peak"]

max_dd = df["_dd"].min()
max_dd_idx = int(df["_dd"].idxmin()) if len(df) else 0
peak_idx = int(df.loc[:max_dd_idx, "_peak"].idxmax()) if max_dd_idx > 0 else 0
# recovery: when did _cum recover to _peak[max_dd_idx]
target = df["_peak"].iloc[max_dd_idx]
recov = df.loc[max_dd_idx:, "_cum"]
recov_idx = recov[recov >= target].index.min() if not recov.empty else None

mc1, mc2, mc3 = st.columns(3)
mc1.metric("Drawdown max", fmt_eur(max_dd))
if max_dd_idx and peak_idx is not None:
    days_to_dd = (df["Date"].iloc[max_dd_idx] - df["Date"].iloc[peak_idx]).days
    mc2.metric("Durée descente", f"{days_to_dd} j")
if recov_idx is not None and not pd.isna(recov_idx):
    days_to_recov = (df["Date"].iloc[int(recov_idx)] - df["Date"].iloc[max_dd_idx]).days
    mc3.metric("Durée recovery", f"{days_to_recov} j")
else:
    mc3.metric("Durée recovery", "—", help="Pas encore récupéré")

fig_dd = go.Figure()
fig_dd.add_trace(
    go.Scatter(
        x=df["Date"],
        y=df["_dd"],
        mode="lines",
        fill="tozeroy",
        line=dict(color="#e04e4e"),
        fillcolor="rgba(224,78,78,0.2)",
        name="Drawdown",
        hovertemplate="%{x}<br>DD : %{y:+.0f}€<extra></extra>",
    )
)
fig_dd.update_layout(
    height=320,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#d1d4dc"),
    margin=dict(t=30, b=40, l=60, r=20),
)
fig_dd.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
fig_dd.update_yaxes(title_text="Drawdown (€)", gridcolor="rgba(100,100,120,0.15)")
st.plotly_chart(fig_dd, width="stretch")


# --- Volatility rolling ---
st.divider()
st.markdown("### 📈 Volatilité (ROI rolling)")
window = st.slider("Fenêtre (paris)", 10, 200, 30, 5)
df_v = df.copy()
df_v["roi_unit"] = np.where(df_v["Mise"] > 0, df_v["Gains net"] / df_v["Mise"], 0.0)
df_v["_roll_mean"] = (
    df_v["roi_unit"]
    .rolling(window=int(window), min_periods=max(5, int(window) // 3))
    .mean()
    * 100
)
df_v["_roll_std"] = (
    df_v["roi_unit"]
    .rolling(window=int(window), min_periods=max(5, int(window) // 3))
    .std()
    * 100
)

fig_v = go.Figure()
fig_v.add_trace(
    go.Scatter(
        x=df_v["Date"],
        y=df_v["_roll_mean"],
        name=f"ROI rolling ({window})",
        mode="lines",
        line=dict(color="#3b82f6", width=2),
        hovertemplate="%{x}<br>ROI : %{y:+.1f}%<extra></extra>",
    )
)
fig_v.add_trace(
    go.Scatter(
        x=df_v["Date"],
        y=df_v["_roll_std"],
        name=f"Volatilité (σ ROI ×100, {window})",
        mode="lines",
        line=dict(color="#fbbf24", width=2, dash="dot"),
        hovertemplate="%{x}<br>σ : %{y:.1f}<extra></extra>",
    )
)
fig_v.add_hline(y=0, line_color="#4b5563", line_dash="dash")
fig_v.update_layout(
    height=380,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#d1d4dc"),
    margin=dict(t=30, b=40, l=60, r=20),
    legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
)
fig_v.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
fig_v.update_yaxes(title_text="%", gridcolor="rgba(100,100,120,0.15)")
st.plotly_chart(fig_v, width="stretch")
