# ruff: noqa: E402
"""Page Alertes : monitoring léger.

Cartes de statut (OK / WARN / ALERT) + hot picks du jour.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from data import (
    load_future_matchs,
    load_future_matchs_missing_betfair,
    load_inplay_bets,
    prepare_bets_data,
)
from utils import fmt_eur, fmt_num
from config import (
    ALERT_AVG_COTE_MAX,
    ALERT_DRAWDOWN_MAX_PCT,
    ALERT_HOT_PICK_EV_MIN,
    ALERT_MATCH_STALE_HOURS,
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


def _find_update_timestamp(row: pd.Series):
    candidates = (
        "date_maj",
        "dt_maj",
        "updated_at",
        "update_at",
        "last_update",
        "last_updated",
        "created_at",
        "timestamp",
        "ts",
    )
    cols_lower = {str(col).lower(): col for col in row.index}

    for name in candidates:
        col = cols_lower.get(name)
        if col is None:
            continue
        ts = pd.to_datetime(row.get(col), errors="coerce")
        if pd.notna(ts):
            return col, pd.Timestamp(ts)

    for col in row.index:
        col_name = str(col).lower()
        if not any(
            token in col_name for token in ("maj", "update", "timestamp", "date")
        ):
            continue
        ts = pd.to_datetime(row.get(col), errors="coerce")
        if pd.notna(ts):
            return col, pd.Timestamp(ts)

    return None, None


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

inplay_bets = pd.DataFrame()
try:
    inplay_bets = load_inplay_bets(st.session_state["ID_USER"])
except Exception:
    inplay_bets = pd.DataFrame()

if inplay_bets is not None and not inplay_bets.empty:
    stale_count = 0
    overdue_count = 0
    inplay_eval = inplay_bets.copy()

    inplay_eval["tourney_date"] = pd.to_datetime(
        inplay_eval.get("tourney_date"), errors="coerce"
    )
    inplay_eval["match_settled"] = pd.to_numeric(
        inplay_eval.get("match_settled"), errors="coerce"
    )
    inplay_eval["Match"] = (
        inplay_eval.get("winner_name", "").astype(str)
        + " - "
        + inplay_eval.get("loser_name", "").astype(str)
    )
    inplay_eval["Compétition"] = inplay_eval.get("compet", "").astype(str).str.title()

    now = pd.Timestamp.now()

    def _row_update_ts(row):
        _, ts = _find_update_timestamp(row)
        return ts

    inplay_eval["_update_ts"] = inplay_eval.apply(_row_update_ts, axis=1)
    inplay_eval["_hours_since_update"] = (
        now - inplay_eval["_update_ts"]
    ).dt.total_seconds() / 3600
    inplay_eval["_hours_since_match"] = (
        now - inplay_eval["tourney_date"]
    ).dt.total_seconds() / 3600

    stale_mask = inplay_eval["_hours_since_update"].notna() & (
        inplay_eval["_hours_since_update"] >= float(ALERT_MATCH_STALE_HOURS)
    )
    overdue_mask = (
        inplay_eval["_hours_since_match"].notna()
        & (inplay_eval["_hours_since_match"] > 24)
        & (~inplay_eval["match_settled"].isin([1, 2]))
    )

    stale_count = int(stale_mask.sum())
    overdue_count = int(overdue_mask.sum())

    if stale_count > 0:
        alerts.append(
            (
                "warn",
                f"{stale_count} match(s) non mis a jour depuis longtemps",
                f"Mise a jour > {ALERT_MATCH_STALE_HOURS}h sur des matchs non settles.",
            )
        )
    if overdue_count > 0:
        alerts.append(
            (
                "alert",
                f"{overdue_count} match(s) > 24h toujours non settles",
                "Matchs dans le passe depuis plus de 24h avec match_settled != 1 ou 2.",
            )
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
# Matchs non mis a jour / non settles
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 🛠️ Matchs a surveiller")

if inplay_bets is None or inplay_bets.empty:
    st.info("Aucun match in-play/non settle a verifier.")
else:
    watch_df = inplay_bets.copy()
    watch_df["tourney_date"] = pd.to_datetime(
        watch_df.get("tourney_date"), errors="coerce"
    )
    watch_df["match_settled"] = pd.to_numeric(
        watch_df.get("match_settled"), errors="coerce"
    )
    watch_df["Match"] = (
        watch_df.get("winner_name", "").astype(str)
        + " - "
        + watch_df.get("loser_name", "").astype(str)
    )
    watch_df["Compétition"] = watch_df.get("compet", "").astype(str).str.title()

    now = pd.Timestamp.now()

    def _extract_update_ts(row):
        _, ts = _find_update_timestamp(row)
        return ts

    watch_df["_update_ts"] = watch_df.apply(_extract_update_ts, axis=1)
    watch_df["Heures depuis update"] = (
        now - watch_df["_update_ts"]
    ).dt.total_seconds() / 3600
    watch_df["Heures depuis match"] = (
        now - watch_df["tourney_date"]
    ).dt.total_seconds() / 3600

    stale_list = watch_df[
        watch_df["Heures depuis update"].notna()
        & (watch_df["Heures depuis update"] >= float(ALERT_MATCH_STALE_HOURS))
    ].copy()
    stale_list = stale_list.sort_values("Heures depuis update", ascending=False)

    st.markdown(
        f"#### ⏱️ Matchs non mis a jour depuis longtemps (>{ALERT_MATCH_STALE_HOURS}h)"
    )
    if stale_list.empty:
        st.success("Aucun match stale detecte.")
    else:
        stale_display = stale_list[
            [
                "tourney_date",
                "Compétition",
                "Match",
                "match_settled",
                "Heures depuis update",
            ]
        ].rename(
            columns={
                "tourney_date": "Date match",
                "match_settled": "match_settled",
            }
        )
        stale_display["Date match"] = stale_display["Date match"].dt.strftime(
            "%d/%m/%Y %H:%M"
        )
        stale_display["Heures depuis update"] = stale_display[
            "Heures depuis update"
        ].round(1)
        st.dataframe(stale_display, width="stretch", hide_index=True)

    overdue_list = watch_df[
        watch_df["Heures depuis match"].notna()
        & (watch_df["Heures depuis match"] > 24)
        & (~watch_df["match_settled"].isin([1, 2]))
    ].copy()
    overdue_list = overdue_list.sort_values("Heures depuis match", ascending=False)

    st.markdown("#### 🕒 Matchs > 24h dans le passe avec match_settled != 1 ou 2")
    if overdue_list.empty:
        st.success("Aucun match en retard de settlement (>24h).")
    else:
        overdue_display = overdue_list[
            [
                "tourney_date",
                "Compétition",
                "Match",
                "match_settled",
                "Heures depuis match",
            ]
        ].rename(
            columns={
                "tourney_date": "Date match",
                "match_settled": "match_settled",
            }
        )
        overdue_display["Date match"] = overdue_display["Date match"].dt.strftime(
            "%d/%m/%Y %H:%M"
        )
        overdue_display["Heures depuis match"] = overdue_display[
            "Heures depuis match"
        ].round(1)
        st.dataframe(overdue_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Matchs imminents non liés à Betfair
# ---------------------------------------------------------------------------
st.divider()
st.markdown("### 🔗 Matchs dans l'heure absents de `betfair_links`")

try:
    missing_bf = load_future_matchs_missing_betfair(within_minutes=60)
except Exception:
    missing_bf = pd.DataFrame()

if missing_bf is None or missing_bf.empty:
    st.success("Tous les matchs prévus dans l'heure sont liés à Betfair.")
else:
    display_bf = missing_bf.copy()
    display_bf["compet"] = display_bf["compet"].astype(str).str.upper()
    display_bf["Match"] = (
        display_bf["winner_name"].astype(str)
        + " - "
        + display_bf["loser_name"].astype(str)
    )
    # Du plus recent au plus ancien, comme tous les tableaux dates de
    # l'application. Le tri porte sur la DATE, avant sa mise en forme :
    # « 30/07/2026 » passe avant « 05/08/2026 » dans l'ordre alphabetique,
    # donc trier la colonne affichee donnerait un ordre faux. Il fallait
    # bien un tri : la requete est un `UNION ALL` de trois `SELECT` sans
    # `ORDER BY` (data.load_future_matchs_missing_betfair), l'ordre affiche
    # etait celui que la base voulait bien rendre. Une date absente part en
    # fin de liste, elle ne peut pas passer pour la plus recente.
    _date_bf = pd.to_datetime(display_bf["tourney_date"], errors="coerce")
    display_bf = display_bf.assign(_tri=_date_bf).sort_values(
        "_tri", ascending=False, kind="stable", na_position="last"
    )
    display_bf["Date"] = display_bf["_tri"].dt.strftime("%d/%m/%Y %H:%M")
    cols = [
        "Date",
        "compet",
        "tourney_name",
        "round",
        "surface",
        "Match",
        "ID_MATCH",
    ]
    display_bf = display_bf[[c for c in cols if c in display_bf.columns]].rename(
        columns={
            "compet": "Compet",
            "tourney_name": "Tournoi",
            "round": "Round",
            "surface": "Surface",
        }
    )
    st.dataframe(display_bf, width="stretch", hide_index=True)
    st.caption(f"{len(missing_bf)} match(s) sans lien Betfair dans la prochaine heure.")


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
