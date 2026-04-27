# ruff: noqa: E402
"""Page Calibration : qualité du modèle de prédiction.

Compare la cote prédite (= 1/proba implicite du modèle) à la réalité observée :
- winrate prédit (par bucket) vs winrate observé
- ROI cumulé réel vs attendu (par bucket de cote)
- Calibration éclatée par surface / round / level / compétition
- Métriques : Brier score, Log loss, ECE (expected calibration error)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import prepare_bets_data
from utils import csv_download_button, fmt_eur, fmt_num


st.set_page_config(
    layout="wide", page_icon="logo_TeNNet.png", page_title="Calibration TeNNet"
)
st.title("🎯 Calibration des prédictions")
st.caption(
    "Le modèle est-il fiable ? Compare la probabilité prédite à la réalité observée."
)

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
df["Cote"] = pd.to_numeric(df["Cote"], errors="coerce")
df["Prédiction"] = pd.to_numeric(df["Prédiction"], errors="coerce")
df["Mise"] = pd.to_numeric(df["Mise"], errors="coerce").fillna(0.0)
df["Gains net"] = pd.to_numeric(df["Gains net"], errors="coerce").fillna(0.0)
df["Marge attendue"] = pd.to_numeric(df["Marge attendue"], errors="coerce").fillna(0.0)
df = df.dropna(subset=["Cote", "Prédiction"])
df = df[(df["Cote"] > 1.0) & (df["Prédiction"] > 1.0)]
if df.empty:
    st.info("Pas assez de données valides.")
    st.stop()

df["win"] = (df["Gains net"] > 0).astype(int)
# proba implicite du modèle = 1 / pred (le modèle utilise une cote prédite ≈ 1/p)
df["p_pred"] = 1.0 / df["Prédiction"]
df["p_market"] = 1.0 / df["Cote"]


# --- Sidebar filters ---
with st.sidebar:
    st.markdown("### Filtres")
    surfaces = (
        sorted(df["Surface"].dropna().unique().tolist())
        if "Surface" in df.columns
        else []
    )
    sel_surf = st.multiselect("Surface", surfaces, default=surfaces)
    comps = (
        sorted(df["Compétition"].dropna().unique().tolist())
        if "Compétition" in df.columns
        else []
    )
    sel_comp = st.multiselect("Compétition", comps, default=comps)
    rounds = (
        sorted(df["Round"].dropna().unique().tolist()) if "Round" in df.columns else []
    )
    sel_round = st.multiselect("Round", rounds, default=rounds)
    n_bins = st.slider("Nombre de bins", 4, 12, 8)
    min_n = st.number_input("Min paris par bin", 3, 200, 5)

if sel_surf and "Surface" in df.columns:
    df = df[df["Surface"].isin(sel_surf)]
if sel_comp and "Compétition" in df.columns:
    df = df[df["Compétition"].isin(sel_comp)]
if sel_round and "Round" in df.columns:
    df = df[df["Round"].isin(sel_round)]

if df.empty:
    st.info("Filtres trop restrictifs.")
    st.stop()


# ---------------------------------------------------------------------------
# Global metrics
# ---------------------------------------------------------------------------
def _brier(p: np.ndarray, y: np.ndarray) -> float:
    if len(p) == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def _log_loss(p: np.ndarray, y: np.ndarray) -> float:
    if len(p) == 0:
        return float("nan")
    eps = 1e-12
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _ece(p: np.ndarray, y: np.ndarray, n_bins: int = 10) -> float:
    if len(p) == 0:
        return float("nan")
    edges = np.linspace(0, 1, n_bins + 1)
    idx = np.digitize(p, edges) - 1
    idx = np.clip(idx, 0, n_bins - 1)
    total = len(p)
    err = 0.0
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() == 0:
            continue
        err += (mask.sum() / total) * abs(y[mask].mean() - p[mask].mean())
    return float(err)


p = df["p_pred"].to_numpy()
y = df["win"].to_numpy()
brier = _brier(p, y)
ll = _log_loss(p, y)
ece = _ece(p, y, n_bins=n_bins)

# Comparatif modèle vs marché
brier_mkt = _brier(df["p_market"].to_numpy(), y)
ll_mkt = _log_loss(df["p_market"].to_numpy(), y)

c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Brier (modèle)",
    f"{brier:.4f}",
    delta=f"{brier - brier_mkt:+.4f} vs marché",
    delta_color="inverse",
)
c2.metric(
    "Log loss (modèle)",
    f"{ll:.4f}",
    delta=f"{ll - ll_mkt:+.4f} vs marché",
    delta_color="inverse",
)
c3.metric("ECE", f"{ece:.4f}", help="Expected Calibration Error — plus bas = mieux")
c4.metric("Paris analysés", fmt_num(len(df)))

st.divider()


# ---------------------------------------------------------------------------
# Reliability diagram (winrate prédit vs observé)
# ---------------------------------------------------------------------------
st.markdown("### 📐 Reliability diagram")
st.caption(
    "Pour chaque bin de probabilité prédite, compare au winrate réellement observé. La diagonale = parfait."
)

# Equal-frequency bins via quantiles
try:
    df["_pbin"] = pd.qcut(df["p_pred"], q=n_bins, duplicates="drop")
except Exception:
    df["_pbin"] = pd.cut(df["p_pred"], bins=n_bins)

cal = (
    df.groupby("_pbin", observed=True)
    .agg(
        p_mean=("p_pred", "mean"),
        p_obs=("win", "mean"),
        n=("win", "size"),
        mises=("Mise", "sum"),
        gains=("Gains net", "sum"),
        marges=("Marge attendue", "sum"),
    )
    .reset_index()
)
cal = cal[cal["n"] >= int(min_n)].copy()

if cal.empty:
    st.info("Pas assez de paris par bin.")
else:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color="#6b7280", dash="dash"),
            name="Parfait",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=cal["p_mean"],
            y=cal["p_obs"],
            mode="markers+lines",
            marker=dict(
                size=np.clip(np.sqrt(cal["n"]) * 3, 8, 30),
                color="#3b82f6",
                line=dict(color="#fff", width=1),
            ),
            line=dict(color="#3b82f6"),
            name="Observé",
            customdata=np.stack([cal["n"], cal["gains"], cal["marges"]], axis=-1),
            hovertemplate=(
                "p prédit : %{x:.3f}<br>"
                "p observé : %{y:.3f}<br>"
                "n : %{customdata[0]}<br>"
                "Gains : %{customdata[1]:+.0f}€<br>"
                "Attendu : %{customdata[2]:+.0f}€"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=420,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        xaxis=dict(
            title="Probabilité prédite",
            range=[0, 1],
            gridcolor="rgba(100,100,120,0.15)",
        ),
        yaxis=dict(
            title="Winrate observé", range=[0, 1], gridcolor="rgba(100,100,120,0.15)"
        ),
        margin=dict(t=30, b=60, l=60, r=20),
    )
    st.plotly_chart(fig, width="stretch")


# ---------------------------------------------------------------------------
# ROI réel vs ROI attendu par bucket de cote
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 💸 ROI réel vs attendu par bucket de cote")
st.caption(
    "Permet de voir si les écarts (réel - attendu) sont systématiques sur certaines plages de cote."
)

cote_bins = [0, 1.5, 2.0, 2.5, 3.0, 5.0, 100.0]
cote_labels = ["<1.5", "1.5-2.0", "2.0-2.5", "2.5-3.0", "3.0-5.0", "≥5.0"]
df["_cbin"] = pd.cut(
    df["Cote"], bins=cote_bins, labels=cote_labels, include_lowest=True
)
g = (
    df.groupby("_cbin", observed=True)
    .agg(
        n=("Mise", "size"),
        mises=("Mise", "sum"),
        gains=("Gains net", "sum"),
        marges=("Marge attendue", "sum"),
        winrate=("win", "mean"),
    )
    .reset_index()
)
g = g[g["n"] >= int(min_n)].copy()
g["ROI"] = np.where(g["mises"] > 0, g["gains"] / g["mises"] * 100, 0.0)
g["ROI_attendu"] = np.where(g["mises"] > 0, g["marges"] / g["mises"] * 100, 0.0)
g["Edge"] = g["ROI"] - g["ROI_attendu"]
g["winrate_pct"] = g["winrate"] * 100

if g.empty:
    st.info("Pas assez de paris pour ce découpage.")
else:
    fig2 = go.Figure()
    fig2.add_trace(
        go.Bar(
            x=g["_cbin"].astype(str),
            y=g["ROI"],
            name="ROI réel",
            marker_color=["#32b296" if v >= 0 else "#e04e4e" for v in g["ROI"]],
            text=[f"{v:+.1f}%" for v in g["ROI"]],
            textposition="outside",
            customdata=np.stack([g["n"], g["mises"], g["winrate_pct"]], axis=-1),
            hovertemplate=(
                "Cote %{x}<br>ROI : <b>%{y:+.1f}%</b><br>n : %{customdata[0]}<br>"
                "Mises : %{customdata[1]:.0f}€<br>Winrate : %{customdata[2]:.1f}%"
                "<extra></extra>"
            ),
        )
    )
    fig2.add_trace(
        go.Scatter(
            x=g["_cbin"].astype(str),
            y=g["ROI_attendu"],
            name="ROI attendu",
            mode="lines+markers",
            line=dict(color="#3b82f6", dash="dot", width=2),
            marker=dict(size=8),
            hovertemplate="ROI attendu %{x} : %{y:+.1f}%<extra></extra>",
        )
    )
    fig2.add_hline(y=0, line_color="#4b5563", line_width=1, line_dash="dash")
    fig2.update_layout(
        height=400,
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#d1d4dc"),
        margin=dict(t=30, b=50, l=60, r=20),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        bargap=0.3,
    )
    fig2.update_xaxes(title_text="Bucket de cote", gridcolor="rgba(100,100,120,0.15)")
    fig2.update_yaxes(title_text="ROI (%)", gridcolor="rgba(100,100,120,0.15)")
    st.plotly_chart(fig2, width="stretch")


# ---------------------------------------------------------------------------
# Calibration par sous-population (small multiples)
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 🔬 Calibration par sous-population")

dim_choice = st.radio(
    "Découper par",
    options=["Surface", "Compétition", "Round", "Level"],
    horizontal=True,
)

if dim_choice in df.columns:
    sub_rows = []
    for val, sub in df.groupby(dim_choice, dropna=True):
        if len(sub) < int(min_n):
            continue
        ps = sub["p_pred"].to_numpy()
        ys = sub["win"].to_numpy()
        roi_real = (
            (sub["Gains net"].sum() / sub["Mise"].sum() * 100)
            if sub["Mise"].sum() > 0
            else 0.0
        )
        roi_att = (
            (sub["Marge attendue"].sum() / sub["Mise"].sum() * 100)
            if sub["Mise"].sum() > 0
            else 0.0
        )
        sub_rows.append(
            {
                dim_choice: val,
                "n": len(sub),
                "Mises": sub["Mise"].sum(),
                "Gains": sub["Gains net"].sum(),
                "ROI": roi_real,
                "ROI attendu": roi_att,
                "Edge": roi_real - roi_att,
                "Winrate prédit": ps.mean() * 100,
                "Winrate observé": ys.mean() * 100,
                "Brier": _brier(ps, ys),
                "Log loss": _log_loss(ps, ys),
                "ECE": _ece(ps, ys, n_bins=min(n_bins, max(3, len(sub) // 5))),
            }
        )
    sub_df = pd.DataFrame(sub_rows).sort_values("Edge", ascending=False)
    if sub_df.empty:
        st.info("Pas assez de données par sous-groupe.")
    else:
        styled = sub_df.style.format(
            {
                "Mises": lambda v: fmt_eur(v),
                "Gains": lambda v: fmt_eur(v, sign=True),
                "ROI": "{:+.1f}%",
                "ROI attendu": "{:+.1f}%",
                "Edge": "{:+.1f}%",
                "Winrate prédit": "{:.1f}%",
                "Winrate observé": "{:.1f}%",
                "Brier": "{:.4f}",
                "Log loss": "{:.4f}",
                "ECE": "{:.4f}",
            }
        ).map(
            lambda v: (
                "color: #32b296; font-weight:700;"
                if isinstance(v, (int, float)) and v > 0
                else "color: #e04e4e; font-weight:700;"
            ),
            subset=["Edge", "ROI"],
        )
        st.dataframe(styled, width="stretch", hide_index=True)
        csv_download_button(
            sub_df,
            label="📥 Exporter calibration",
            filename=f"calibration_{dim_choice}.csv",
            key="cal_csv",
        )
