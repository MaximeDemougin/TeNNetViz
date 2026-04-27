# ruff: noqa: E402
"""Page Bankroll & Kelly : optimisation de la mise et gestion du risque.

- Calculateur Kelly (full / fractional) à partir d'une cote et d'une prédiction
- Comparaison historique mise réelle vs mise Kelly suggérée
- Simulation Monte Carlo des prochains paris (trajectoires + drawdown attendu)
- Probabilité de ruine
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import prepare_bets_data
from utils import fmt_eur, fmt_num


st.set_page_config(
    layout="wide", page_icon="logo_TeNNet.png", page_title="Bankroll & Kelly"
)
st.title("💰 Bankroll & Kelly")
st.caption("Optimise tes mises et quantifie le risque.")

if not st.session_state.get("logged_in", False):
    st.info("Veuillez vous connecter.")
    st.stop()

bankroll = st.session_state.get("bankroll_cached") or 0
bets_data = st.session_state.get("bets_data_cached")
if bets_data is None:
    bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=True)


def kelly_fraction(p: float, odds: float) -> float:
    """Kelly fraction = (b·p - q) / b avec b = odds - 1, q = 1 - p. Clamp à 0."""
    if odds <= 1.0 or not (0 <= p <= 1):
        return 0.0
    b = odds - 1.0
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)


# ---------------------------------------------------------------------------
# Calculateur Kelly interactif
# ---------------------------------------------------------------------------
st.markdown("### 🎯 Calculateur de mise optimale")

c1, c2, c3, c4 = st.columns(4)
with c1:
    bk = st.number_input(
        "Bankroll (€)", min_value=0, value=int(bankroll or 1000), step=50
    )
with c2:
    cote = st.number_input("Cote", min_value=1.01, value=2.00, step=0.01, format="%.2f")
with c3:
    pred = st.number_input(
        "Prédiction (cote prédite)",
        min_value=1.01,
        value=1.80,
        step=0.01,
        format="%.2f",
    )
with c4:
    kelly_frac = st.slider(
        "Fraction Kelly", 0.05, 1.0, 0.25, 0.05, help="0.25 = quart-Kelly (recommandé)"
    )

p = 1.0 / pred if pred > 1 else 0.0
edge = (cote / pred - 1) * 100 if pred > 1 else 0.0
f_full = kelly_fraction(p, cote)
f_used = f_full * kelly_frac
stake_full = bk * f_full
stake_used = bk * f_used
ev_unit = (cote * p - 1) if p > 0 else 0.0

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "EV par 1€ misé", fmt_eur(ev_unit, decimals=3, sign=True), help="(cote × p) - 1"
)
m2.metric("Edge (%)", f"{edge:+.2f}%", help="(cote / prédiction - 1)")
m3.metric("Kelly full", fmt_eur(stake_full), delta=f"{f_full*100:.2f}% bankroll")
m4.metric(
    f"Mise suggérée (×{kelly_frac:.2f})",
    fmt_eur(stake_used),
    delta=f"{f_used*100:.2f}% bankroll",
)

if f_full <= 0:
    st.warning("Edge insuffisant : le pari n'est pas rentable selon Kelly (mise = 0€).")

st.divider()

# ---------------------------------------------------------------------------
# Historique mise réelle vs mise Kelly
# ---------------------------------------------------------------------------
st.markdown("### 📊 Historique : mise réelle vs Kelly suggéré")

if bets_data is None or bets_data.empty:
    st.info("Aucun pari historique.")
else:
    h = bets_data.copy()
    h["Cote"] = pd.to_numeric(h["Cote"], errors="coerce")
    h["Prédiction"] = pd.to_numeric(h["Prédiction"], errors="coerce")
    h["Mise"] = pd.to_numeric(h["Mise"], errors="coerce").fillna(0.0)
    h = h.dropna(subset=["Cote", "Prédiction"])
    h = h[(h["Cote"] > 1) & (h["Prédiction"] > 1)]

    if h.empty:
        st.info("Pas de données valides.")
    else:
        h["p_pred"] = 1.0 / h["Prédiction"]
        h["kelly_full"] = h.apply(
            lambda r: kelly_fraction(r["p_pred"], r["Cote"]), axis=1
        )
        h["kelly_stake"] = h["kelly_full"] * float(bk) * float(kelly_frac)
        h["mise_pct_bk"] = (h["Mise"] / float(bk)) * 100 if bk else 0
        h["kelly_pct_bk"] = h["kelly_full"] * 100 * float(kelly_frac)

        avg_mise = h["Mise"].mean()
        avg_kelly = h["kelly_stake"].mean()
        ratio = (avg_mise / avg_kelly) if avg_kelly > 0 else float("nan")

        sa, sb, sc = st.columns(3)
        sa.metric("Mise moyenne réelle", fmt_eur(avg_mise))
        sb.metric(f"Kelly suggéré moyen (×{kelly_frac:.2f})", fmt_eur(avg_kelly))
        sc.metric(
            "Ratio réelle / Kelly",
            f"{ratio:.2f}×" if ratio == ratio else "—",
            help="<1 = sous-misé, >1 = sur-misé selon Kelly",
        )

        # Plot mise réelle vs kelly suggérée chronologique
        try:
            h["Date"] = pd.to_datetime(h["Date"], errors="coerce")
        except Exception:
            pass
        h_sorted = h.sort_values("Date")
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=h_sorted["Date"],
                y=h_sorted["Mise"],
                mode="markers",
                name="Mise réelle",
                marker=dict(color="#fbbf24", size=5, opacity=0.7),
                hovertemplate="Mise réelle : %{y:.0f}€<br>%{x}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=h_sorted["Date"],
                y=h_sorted["kelly_stake"],
                mode="markers",
                name=f"Kelly suggéré (×{kelly_frac:.2f})",
                marker=dict(color="#3b82f6", size=5, opacity=0.7),
                hovertemplate="Kelly : %{y:.0f}€<br>%{x}<extra></extra>",
            )
        )
        fig.update_layout(
            height=380,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#d1d4dc"),
            margin=dict(t=30, b=40, l=60, r=20),
            legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
        )
        fig.update_xaxes(gridcolor="rgba(100,100,120,0.15)")
        fig.update_yaxes(title_text="Mise (€)", gridcolor="rgba(100,100,120,0.15)")
        st.plotly_chart(fig, width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Simulation Monte Carlo
# ---------------------------------------------------------------------------
st.markdown("### 🎲 Simulation Monte Carlo")
st.caption(
    "Tirage aléatoire des prochains paris en piochant dans l'historique (bootstrap). "
    "Trace les trajectoires de bankroll et estime la probabilité de ruine."
)

if bets_data is None or bets_data.empty:
    st.info("Pas d'historique pour la simulation.")
else:
    h = bets_data.copy()
    h["Mise"] = pd.to_numeric(h["Mise"], errors="coerce").fillna(0.0)
    h["Gains net"] = pd.to_numeric(h["Gains net"], errors="coerce").fillna(0.0)
    h = h[h["Mise"] > 0]

    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        n_sim = st.slider("Trajectoires", 50, 2000, 500, 50)
    with cc2:
        n_bets = st.slider("Paris à simuler", 50, 1000, 200, 50)
    with cc3:
        ruin_threshold = st.slider("Seuil ruine (% bankroll)", 0, 80, 30, 5)
    with cc4:
        seed = st.number_input("Seed", value=42)

    if st.button("▶️ Lancer la simulation", type="primary"):
        rng = np.random.default_rng(int(seed))
        unit_returns = (h["Gains net"] / h["Mise"]).to_numpy()
        if len(unit_returns) == 0:
            st.warning("Pas de données.")
        else:
            # Bootstrap : à chaque step, mise = kelly_frac × Kelly sur un pari tiré au hasard,
            # mais simplification : reuse historical net_unit returns and mise relative à bankroll.
            avg_mise_pct = (
                (h["Mise"].sum() / float(bk) / max(1, len(h))) if bk else 0.05
            )
            avg_mise_pct = float(np.clip(avg_mise_pct, 0.005, 0.5))

            traj = np.zeros((int(n_sim), int(n_bets) + 1))
            traj[:, 0] = float(bk)
            ruined = np.zeros(int(n_sim), dtype=bool)
            for i in range(int(n_sim)):
                br = float(bk)
                for t in range(int(n_bets)):
                    r = rng.choice(unit_returns)
                    stake = br * avg_mise_pct
                    br = br + stake * r
                    traj[i, t + 1] = br
                    if br <= float(bk) * (1 - ruin_threshold / 100):
                        ruined[i] = True

            ruin_pct = 100.0 * ruined.mean()
            final = traj[:, -1]
            min_path = traj.min(axis=1)
            max_dd = (
                (traj.cummax(axis=1) - traj) / np.maximum(traj.cummax(axis=1), 1e-9)
            ).max(axis=1) * 100

            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Bankroll médian final", fmt_eur(np.median(final)))
            r2.metric(
                "p5 — p95",
                f"{fmt_eur(np.percentile(final,5))} → {fmt_eur(np.percentile(final,95))}",
            )
            r3.metric(f"Prob. ruine ({ruin_threshold}%)", f"{ruin_pct:.1f}%")
            r4.metric("Drawdown max médian", f"{np.median(max_dd):.1f}%")

            # Trace 100 chemins + percentiles
            fig = go.Figure()
            sample = rng.choice(int(n_sim), size=min(120, int(n_sim)), replace=False)
            for i in sample:
                fig.add_trace(
                    go.Scatter(
                        x=np.arange(int(n_bets) + 1),
                        y=traj[i],
                        mode="lines",
                        line=dict(color="rgba(59,130,246,0.08)", width=1),
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
            for q, color, name in [
                (0.05, "#e04e4e", "p5"),
                (0.5, "#fbbf24", "médiane"),
                (0.95, "#32b296", "p95"),
            ]:
                fig.add_trace(
                    go.Scatter(
                        x=np.arange(int(n_bets) + 1),
                        y=np.percentile(traj, q * 100, axis=0),
                        mode="lines",
                        line=dict(color=color, width=2),
                        name=name,
                    )
                )
            fig.add_hline(
                y=float(bk),
                line_color="#9ca3af",
                line_dash="dash",
                annotation_text="Bankroll initial",
                annotation_position="top right",
            )
            fig.update_layout(
                height=460,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#d1d4dc"),
                margin=dict(t=30, b=40, l=60, r=20),
                legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
            )
            fig.update_xaxes(title_text="Pari #", gridcolor="rgba(100,100,120,0.15)")
            fig.update_yaxes(
                title_text="Bankroll (€)", gridcolor="rgba(100,100,120,0.15)"
            )
            st.plotly_chart(fig, width="stretch")
