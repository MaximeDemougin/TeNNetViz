# ruff: noqa: E402
"""Page Alertes : monitoring léger.

Cartes de statut (OK / WARN / ALERT) + hot picks du jour.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from data import load_future_matchs, prepare_bets_data
from utils import fmt_eur, fmt_num
from config import (
    ALERT_AVG_COTE_MAX,
    ALERT_DRAWDOWN_MAX_PCT,
    ALERT_HOT_PICK_EV_MIN,
    ALERT_RECENT_BETS_WINDOW,
    ALERT_WINRATE_MIN,
    MAX_PRED_BETABLE,
    MIN_PRED_BETABLE,
)


st.set_page_config(
    layout="wide", page_icon="logo_TeNNet.png", page_title="Alertes TeNNet"
)
st.title("🚨 Alertes & Monitoring")
st.caption("Statut rapide de ton activité et opportunités du moment.")

if not st.session_state.get("logged_in", False):
    st.info("Veuillez vous connecter.")
    st.stop()

bankroll = st.session_state.get("bankroll_cached") or 0
bets_data = st.session_state.get("bets_data_cached")
if bets_data is None:
    bets_data = prepare_bets_data(st.session_state["ID_USER"], finished=True)


def _alert_card(level: str, title: str, msg: str):
    """level: ok / warn / alert"""
    colors = {
        "ok": ("#32b296", "✅"),
        "warn": ("#fbbf24", "⚠️"),
        "alert": ("#e04e4e", "🚨"),
    }
    color, icon = colors.get(level, ("#9ca3af", "ℹ️"))
    st.markdown(
        f"""
        <div style='background:linear-gradient(135deg,rgba(30,30,35,0.95),rgba(20,20,25,0.98));
                    border-left:4px solid {color};border-radius:10px;
                    padding:14px 16px;margin-bottom:10px;
                    box-shadow:0 2px 6px rgba(0,0,0,0.3);'>
          <div style='font-size:15px;font-weight:700;color:#e0e0e0;'>{icon} {title}</div>
          <div style='font-size:13px;color:#9ca3af;margin-top:6px;'>{msg}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Computation des règles
# ---------------------------------------------------------------------------
alerts: list[tuple[str, str, str]] = []  # (level, title, message)

if bets_data is not None and not bets_data.empty:
    df = bets_data.copy()
    try:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    except Exception:
        pass
    df = df.dropna(subset=["Date"]).sort_values("Date")
    df["Mise"] = pd.to_numeric(df["Mise"], errors="coerce").fillna(0.0)
    df["Gains net"] = pd.to_numeric(df["Gains net"], errors="coerce").fillna(0.0)
    df["Cote"] = pd.to_numeric(df["Cote"], errors="coerce")

    # Recent winrate
    recent = df.tail(int(ALERT_RECENT_BETS_WINDOW))
    if len(recent) >= 5:
        wr = (recent["Gains net"] > 0).mean() * 100
        if wr < ALERT_WINRATE_MIN:
            alerts.append(
                (
                    "alert",
                    f"Winrate récent faible ({wr:.1f}%)",
                    f"Sur les {len(recent)} derniers paris, tu es sous le seuil de {ALERT_WINRATE_MIN:.0f}%.",
                )
            )
        else:
            alerts.append(
                (
                    "ok",
                    f"Winrate récent OK ({wr:.1f}%)",
                    f"Au-dessus du seuil de {ALERT_WINRATE_MIN:.0f}% sur les {len(recent)} derniers paris.",
                )
            )

    # Drawdown vs bankroll
    if bankroll and bankroll > 0:
        df["_cum"] = df["Gains net"].cumsum()
        df["_peak"] = df["_cum"].cummax()
        df["_dd"] = df["_cum"] - df["_peak"]
        max_dd = df["_dd"].min()
        dd_pct = abs(max_dd) / float(bankroll) * 100
        if dd_pct > ALERT_DRAWDOWN_MAX_PCT:
            alerts.append(
                (
                    "alert",
                    f"Drawdown max élevé ({dd_pct:.1f}% bankroll)",
                    f"Drawdown : {fmt_eur(max_dd)} sur bankroll de {fmt_eur(bankroll)}.",
                )
            )
        else:
            alerts.append(
                (
                    "ok",
                    f"Drawdown sous contrôle ({dd_pct:.1f}%)",
                    f"Sous le seuil de {ALERT_DRAWDOWN_MAX_PCT:.0f}%.",
                )
            )

    # Cote moyenne sur fenêtre récente
    if len(recent) >= 5:
        avg_cote = recent["Cote"].mean()
        if avg_cote and avg_cote > ALERT_AVG_COTE_MAX:
            alerts.append(
                (
                    "warn",
                    f"Cote moyenne récente élevée ({avg_cote:.2f})",
                    f"Au-dessus du seuil de {ALERT_AVG_COTE_MAX:.2f}. Variance accrue.",
                )
            )

    # Cold streak
    last_results = (df["Gains net"] > 0).astype(int).tolist()
    cold = 0
    for r in reversed(last_results):
        if r == 0:
            cold += 1
        else:
            break
    if cold >= 5:
        alerts.append(
            (
                "alert",
                f"Cold streak en cours ({cold}L)",
                "Au moins 5 défaites consécutives.",
            )
        )
    elif cold >= 3:
        alerts.append(
            ("warn", f"Mauvaise passe ({cold}L)", "3 défaites consécutives ou plus.")
        )

    # Hot streak
    hot = 0
    for r in reversed(last_results):
        if r == 1:
            hot += 1
        else:
            break
    if hot >= 5:
        alerts.append(
            ("ok", f"Hot streak ({hot}W)", "Au moins 5 victoires consécutives 🔥")
        )

    # ROI 30 derniers
    if recent["Mise"].sum() > 0:
        roi_recent = recent["Gains net"].sum() / recent["Mise"].sum() * 100
        if roi_recent > 10:
            alerts.append(
                ("ok", f"ROI récent fort (+{roi_recent:.1f}%)", "Beau momentum.")
            )
        elif roi_recent < -5:
            alerts.append(
                ("warn", f"ROI récent négatif ({roi_recent:+.1f}%)", "À surveiller.")
            )

else:
    alerts.append(
        ("warn", "Pas d'historique de paris", "Aucun pari terminé pour analyser.")
    )

# Render alerts
if not alerts:
    _alert_card("ok", "Tout va bien", "Aucune alerte à signaler.")
else:
    # Order: alert first, then warn, then ok
    order = {"alert": 0, "warn": 1, "ok": 2}
    alerts.sort(key=lambda a: order.get(a[0], 99))
    for lvl, title, msg in alerts:
        _alert_card(lvl, title, msg)


# ---------------------------------------------------------------------------
# Hot picks du jour (depuis les futurs matchs)
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 🎯 Hot picks (EV ≥ {:.0f}%)".format(ALERT_HOT_PICK_EV_MIN))

try:
    fm = load_future_matchs()
except Exception:
    fm = pd.DataFrame()

if fm is None or fm.empty:
    st.info("Aucun match futur disponible.")
else:
    fm = fm.copy()
    fm["compet"] = fm["compet"].astype(str).str.title()
    rows = []
    for _, r in fm.iterrows():
        for side in ("winner", "loser"):
            try:
                pred = float(r.get(f"{side}_pred") or 0)
            except Exception:
                pred = 0
            try:
                odd = float(
                    r.get("max_odds1" if side == "winner" else "max_odds2") or 0
                )
            except Exception:
                odd = 0
            ev = (odd / pred - 1) * 100 if (odd and pred) else 0
            if ev >= ALERT_HOT_PICK_EV_MIN and (
                MIN_PRED_BETABLE <= pred <= MAX_PRED_BETABLE
            ):
                rows.append(
                    {
                        "Date": r.get("tourney_date"),
                        "Compétition": (r.get("compet") or "").title(),
                        "Tournoi": r.get("tourney_name"),
                        "Joueur": r.get(f"{side}_name"),
                        "Match": f"{r.get('winner_name', '')} - {r.get('loser_name', '')}",
                        "Cote": odd,
                        "Prédiction": pred,
                        "EV %": ev,
                    }
                )
    picks = pd.DataFrame(rows)
    if picks.empty:
        st.info("Aucun pick avec EV suffisant pour le moment.")
    else:
        picks = picks.sort_values("EV %", ascending=False)
        try:
            picks["Date"] = pd.to_datetime(picks["Date"], errors="coerce")
        except Exception:
            pass
        styled = picks.style.format(
            {
                "Cote": "{:.3f}",
                "Prédiction": "{:.3f}",
                "EV %": "{:+.1f}%",
            }
        ).map(
            lambda v: (
                "color: #6a0dad; font-weight: 700;"
                if isinstance(v, (int, float)) and v > 10
                else "color: #32b296; font-weight: 700;"
            ),
            subset=["EV %"],
        )
        st.dataframe(styled, width="stretch", hide_index=True)
        st.caption(f"{len(picks)} pick(s) — triés par EV décroissante.")
