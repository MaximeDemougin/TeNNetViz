# ruff: noqa: E402
"""Page Bankroll : simulation Monte Carlo des prochains paris."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from data import prepare_bets_data
from utils import fmt_eur


st.set_page_config(layout="wide", page_icon="logo_TeNNet.png", page_title="Bankroll")
st.title("💰 Bankroll")
st.caption("Simulation Monte Carlo des prochains paris.")

if not st.session_state.get("logged_in", False):
    st.info("Veuillez vous connecter.")
    st.stop()

bankroll = st.session_state.get("bankroll_cached") or 0
bets_data = st.session_state.get("bets_data_cached")
if bets_data is None:
    bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=True)

bk = st.number_input(
    "Bankroll (€)",
    min_value=0,
    value=int(bankroll or 1000),
    step=50,
    help="Capital de départ utilisé pour la simulation. Pré-rempli avec ta bankroll actuelle.",
)

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
    h["Cote"] = pd.to_numeric(h.get("Cote"), errors="coerce")
    h["Prédiction"] = pd.to_numeric(h.get("Prédiction"), errors="coerce")
    h = h[h["Mise"] > 0]

    # Stratégie de mise
    st.markdown("#### Stratégie de mise")
    stake_mode = st.radio(
        "Mode",
        ["Fixe (% bankroll)", "Range aléatoire (% bankroll)", "Kelly fractionnel"],
        horizontal=True,
        key="stake_mode",
        help=(
            "• **Fixe** : même % de la bankroll à chaque pari.\n"
            "• **Range aléatoire** : % tiré uniformément entre min et max à chaque pari.\n"
            "• **Kelly fractionnel** : mise = fraction Kelly basée sur (cote, prédiction) du pari tiré."
        ),
    )

    sm1, sm2 = st.columns(2)
    if stake_mode == "Fixe (% bankroll)":
        with sm1:
            stake_pct = st.slider(
                "Mise (% bankroll)",
                0.1,
                20.0,
                1.0,
                0.1,
                format="%.1f%%",
                help="Pourcentage de la bankroll misé à chaque pari.",
            )
        stake_range = None
        kelly_frac = None
    elif stake_mode == "Range aléatoire (% bankroll)":
        with sm1:
            stake_range = st.slider(
                "Range mise (% bankroll)",
                0.1,
                20.0,
                (0.5, 1.5),
                0.1,
                format="%.1f%%",
                help="Borne inférieure et supérieure du % de bankroll. Tirage uniforme à chaque pari.",
            )
        stake_pct = None
        kelly_frac = None
    else:  # Kelly
        with sm1:
            kelly_frac = st.slider(
                "Fraction Kelly",
                0.05,
                1.0,
                0.25,
                0.05,
                help="Fraction du Kelly optimal. 0.25 = quart-Kelly (recommandé, plus sûr). 1.0 = full Kelly (volatil).",
            )
        with sm2:
            kelly_cap = st.slider(
                "Plafond mise (% bankroll)",
                0.1,
                20.0,
                1.0,
                0.1,
                format="%.1f%%",
                help="Plafond max appliqué à la mise Kelly (en % de la bankroll). Évite des mises explosives sur edges élevés.",
            )
        stake_pct = None
        stake_range = None

    # Bornes absolues mise (en €)
    cap_lo, cap_hi = st.columns(2)
    with cap_lo:
        stake_min_eur = st.number_input(
            "Mise min (€)",
            min_value=0.0,
            value=7.0,
            step=1.0,
            help="Plancher absolu : si la mise calculée est inférieure, elle est relevée à cette valeur.",
        )
    with cap_hi:
        stake_max_eur = st.number_input(
            "Mise max (€)",
            min_value=0.0,
            value=500.0,
            step=1.0,
            help="Plafond absolu (0 = pas de plafond).",
        )

    st.markdown("#### Paramètres simulation")
    cc1, cc2, cc3, cc4 = st.columns(4)
    with cc1:
        n_sim = st.slider(
            "Trajectoires",
            50,
            2000,
            500,
            50,
            help="Nombre de simulations indépendantes lancées en parallèle. Plus = résultats plus stables, mais calcul plus long.",
        )
    with cc2:
        n_bets = st.slider(
            "Paris à simuler",
            50,
            1000,
            200,
            50,
            help="Nombre de paris consécutifs simulés sur chaque trajectoire (horizon de la simulation).",
        )
    with cc3:
        ruin_threshold = st.slider(
            "Seuil ruine (% bankroll)",
            0,
            100,
            80,
            5,
            help="Pourcentage de perte par rapport à la bankroll initiale au-dessous duquel la trajectoire est considérée comme ruinée.",
        )
    with cc4:
        seed = st.number_input(
            "Seed",
            value=42,
            help="Graine aléatoire. Même seed + mêmes paramètres = résultats reproductibles.",
        )

    # Label + actions
    st.markdown("#### Lancer")
    run_name = st.text_input(
        "Nom du scénario",
        value=f"Scénario {len(st.session_state.get('mc_runs', [])) + 1}",
        help="Permet de garder plusieurs simulations pour comparer.",
    )
    btn_col, clr_col = st.columns([3, 1])
    with btn_col:
        run_clicked = st.button(
            "▶️ Lancer la simulation", type="primary", width="stretch"
        )
    with clr_col:
        if st.button("🗑️ Réinitialiser", width="stretch"):
            st.session_state["mc_runs"] = []
            st.rerun()

    if "mc_runs" not in st.session_state:
        st.session_state["mc_runs"] = []

    if run_clicked:
        rng = np.random.default_rng(int(seed))
        unit_returns = (h["Gains net"] / h["Mise"]).to_numpy()

        # Pour Kelly : on tire un pari (cote, pred) en même temps que le résultat
        h_valid = h.dropna(subset=["Cote", "Prédiction"])
        h_valid = h_valid[(h_valid["Cote"] > 1) & (h_valid["Prédiction"] > 1)]
        cotes = h_valid["Cote"].to_numpy() if not h_valid.empty else np.array([])
        preds = h_valid["Prédiction"].to_numpy() if not h_valid.empty else np.array([])
        kelly_returns = (
            (h_valid["Gains net"] / h_valid["Mise"]).to_numpy()
            if not h_valid.empty
            else np.array([])
        )

        if len(unit_returns) == 0:
            st.warning("Pas de données.")
        elif stake_mode == "Kelly fractionnel" and len(cotes) == 0:
            st.warning("Pas de paris avec Cote / Prédiction valides pour Kelly.")
        else:
            traj = np.zeros((int(n_sim), int(n_bets) + 1))
            traj[:, 0] = float(bk)
            ruined = np.zeros(int(n_sim), dtype=bool)
            for i in range(int(n_sim)):
                br = float(bk)
                for t in range(int(n_bets)):
                    if stake_mode == "Kelly fractionnel":
                        idx = rng.integers(0, len(cotes))
                        odds = float(cotes[idx])
                        p = 1.0 / float(preds[idx])
                        b = odds - 1.0
                        f_full = max(0.0, (b * p - (1 - p)) / b) if b > 0 else 0.0
                        f_used = min(f_full * float(kelly_frac), kelly_cap / 100.0)
                        stake = br * f_used
                        r = float(kelly_returns[idx])
                    else:
                        if stake_mode == "Fixe (% bankroll)":
                            pct = float(stake_pct) / 100.0
                        else:
                            lo, hi = stake_range
                            pct = float(rng.uniform(lo, hi)) / 100.0
                        stake = br * pct
                        r = float(rng.choice(unit_returns))
                    # Application des bornes absolues
                    if stake_min_eur > 0:
                        stake = max(stake, float(stake_min_eur))
                    if stake_max_eur > 0:
                        stake = min(stake, float(stake_max_eur))
                    # Ne jamais miser plus que la bankroll restante
                    stake = max(0.0, min(stake, br))
                    br = br + stake * r
                    traj[i, t + 1] = br
                    if br <= float(bk) * (1 - ruin_threshold / 100):
                        ruined[i] = True

            ruin_pct = 100.0 * ruined.mean()
            final = traj[:, -1]
            running_max = np.maximum.accumulate(traj, axis=1)
            max_dd = ((running_max - traj) / np.maximum(running_max, 1e-9)).max(
                axis=1
            ) * 100

            # Synthèse paramètres pour la légende
            if stake_mode == "Fixe (% bankroll)":
                params_label = f"Fixe {stake_pct:.1f}%"
            elif stake_mode == "Range aléatoire (% bankroll)":
                lo_, hi_ = stake_range
                params_label = f"Range {lo_:.1f}–{hi_:.1f}%"
            else:
                params_label = f"Kelly ×{kelly_frac:.2f} (cap {kelly_cap:.1f}%)"
            if stake_min_eur > 0 or stake_max_eur > 0:
                params_label += f" [{stake_min_eur:.0f}€–{stake_max_eur:.0f}€]"

            # Stocker le run
            st.session_state["mc_runs"].append(
                {
                    "name": run_name,
                    "params": params_label,
                    "bk": float(bk),
                    "n_bets": int(n_bets),
                    "p5": np.percentile(traj, 5, axis=0),
                    "p50": np.percentile(traj, 50, axis=0),
                    "p95": np.percentile(traj, 95, axis=0),
                    "final_median": float(np.median(final)),
                    "final_p5": float(np.percentile(final, 5)),
                    "final_p95": float(np.percentile(final, 95)),
                    "ruin_pct": float(ruin_pct),
                    "ruin_threshold": int(ruin_threshold),
                    "max_dd_median": float(np.median(max_dd)),
                    # Chemins échantillonnés pour le tracé "spaghetti" du dernier run
                    "sample_paths": traj[
                        rng.choice(int(n_sim), size=min(120, int(n_sim)), replace=False)
                    ],
                }
            )

    # ------------------------------------------------------------------
    # Affichage : récap de tous les runs stockés
    # ------------------------------------------------------------------
    runs = st.session_state.get("mc_runs", [])
    if runs:
        st.markdown("#### 📊 Résultats")

        # Sélection des courbes à afficher + suppression individuelle
        all_names = [r["name"] for r in runs]
        sel_col, del_col, btn_col = st.columns([3, 2, 1])
        with sel_col:
            visible_names = st.multiselect(
                "Scénarios affichés",
                options=all_names,
                default=all_names,
                help="Décoche pour masquer une courbe sans la supprimer.",
            )
        with del_col:
            to_delete = st.selectbox("Supprimer", options=["—"] + all_names, index=0)
        with btn_col:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("🗑️", width="stretch", disabled=(to_delete == "—")):
                st.session_state["mc_runs"] = [
                    r for r in runs if r["name"] != to_delete
                ]
                st.rerun()

        visible_runs = [r for r in runs if r["name"] in visible_names]

        # Tableau récap
        recap = pd.DataFrame(
            [
                {
                    "Scénario": r["name"],
                    "Paramètres": r["params"],
                    "Médian final": fmt_eur(r["final_median"]),
                    "p5 → p95": f"{fmt_eur(r['final_p5'])} → {fmt_eur(r['final_p95'])}",
                    f"Ruine ({r['ruin_threshold']}%)": f"{r['ruin_pct']:.1f}%",
                    "DD médian": f"{r['max_dd_median']:.1f}%",
                }
                for r in runs
            ]
        )
        st.dataframe(recap, width="stretch", hide_index=True)

        if not visible_runs:
            st.info(
                "Aucun scénario sélectionné — coche au moins un scénario à afficher."
            )
        else:
            # Graphe de comparaison : médiane + bande p5-p95 par run
            palette = [
                "#3b82f6",
                "#fbbf24",
                "#32b296",
                "#e04e4e",
                "#a855f7",
                "#ec4899",
                "#06b6d4",
                "#f97316",
            ]
            fig = go.Figure()

            # Si un seul run visible : afficher aussi le spaghetti
            if len(visible_runs) == 1:
                r = visible_runs[0]
                for path in r["sample_paths"]:
                    fig.add_trace(
                        go.Scatter(
                            x=np.arange(len(path)),
                            y=path,
                            mode="lines",
                            line=dict(color="rgba(59,130,246,0.08)", width=1),
                            showlegend=False,
                            hoverinfo="skip",
                        )
                    )

            for r in visible_runs:
                # couleur stable basée sur l'index original du run
                idx = next(i for i, rr in enumerate(runs) if rr["name"] == r["name"])
                color = palette[idx % len(palette)]
                x = np.arange(len(r["p50"]))
                # Bande p5-p95
                fig.add_trace(
                    go.Scatter(
                        x=np.concatenate([x, x[::-1]]),
                        y=np.concatenate([r["p95"], r["p5"][::-1]]),
                        fill="toself",
                        fillcolor=f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.12)",
                        line=dict(color="rgba(0,0,0,0)"),
                        showlegend=False,
                        hoverinfo="skip",
                        name=f"{r['name']} band",
                    )
                )
                # Médiane
                fig.add_trace(
                    go.Scatter(
                        x=x,
                        y=r["p50"],
                        mode="lines",
                        line=dict(color=color, width=2),
                        name=f"{r['name']} — {r['params']}",
                        hovertemplate=f"{r['name']}<br>Pari %{{x}} : %{{y:.0f}}€<extra></extra>",
                    )
                )

            # Bankroll initial
            fig.add_hline(
                y=visible_runs[-1]["bk"],
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
