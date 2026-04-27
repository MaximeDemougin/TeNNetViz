# ruff: noqa: E402
"""Page Matchs à venir — cartes par match avec EV des deux côtés."""

import streamlit as st
import pandas as pd
from datetime import timedelta

from data import load_future_matchs
from pages.components.charts import sort_competitions
from pages.components.features_dialog import (
    _format_exact_ts,
    show_features_dialog,
)
from utils import csv_download_button


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
MIN_PRED_BETABLE = 1.1
MAX_PRED_BETABLE = 4.0
MIN_MARGE = 2.0  # EV (%) minimum pour qu un pari soit "rentable"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def _get_future_matchs():
    return load_future_matchs()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ev_pct(odds: float, pred: float) -> float:
    if not odds or not pred or pred <= 0:
        return 0.0
    return (odds / pred - 1.0) * 100.0


def _is_betable(ev: float, pred: float) -> bool:
    return ev > MIN_MARGE and (MIN_PRED_BETABLE <= pred <= MAX_PRED_BETABLE)


def _ev_color(ev: float) -> str:
    if ev > 10:
        return "#a855f7"
    if ev > MIN_MARGE:
        return "#32b296"
    if ev > 0:
        return "#fbbf24"
    return "#e04e4e"


def _build_match_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par match avec les donnees W et L."""
    cols_lower = {c.lower(): c for c in df.columns}
    id_tennet_col = cols_lower.get("id_tennet")
    odds_maj_col = cols_lower.get("odds_maj") or cols_lower.get("maj")
    rows = []
    for _, r in df.iterrows():
        winner_name = str(r.get("winner_name") or "")
        loser_name = str(r.get("loser_name") or "")
        match_label = f"{winner_name} - {loser_name}"

        raw_tennet = r.get(id_tennet_col) if id_tennet_col else None
        if raw_tennet is None or (isinstance(raw_tennet, float) and pd.isna(raw_tennet)):
            id_tennet_val = None
        else:
            try:
                id_tennet_val = int(raw_tennet)
            except (TypeError, ValueError):
                id_tennet_val = raw_tennet

        w_pred = float(pd.to_numeric(r.get("winner_pred"), errors="coerce") or 0)
        l_pred = float(pd.to_numeric(r.get("loser_pred"), errors="coerce") or 0)
        w_odds = float(pd.to_numeric(r.get("max_odds1"), errors="coerce") or 0)
        l_odds = float(pd.to_numeric(r.get("max_odds2"), errors="coerce") or 0)
        w_ev = _ev_pct(w_odds, w_pred)
        l_ev = _ev_pct(l_odds, l_pred)

        odds_maj_val = r.get(odds_maj_col) if odds_maj_col else None

        rows.append({
            "ID_MATCH": r.get("ID_MATCH"),
            "ID_TENNET": id_tennet_val,
            "Match": match_label,
            "W_name": winner_name,
            "L_name": loser_name,
            "W_pred": round(w_pred, 3),
            "L_pred": round(l_pred, 3),
            "W_odds": round(w_odds, 3),
            "L_odds": round(l_odds, 3),
            "W_ev": round(w_ev, 1),
            "L_ev": round(l_ev, 1),
            "W_betable": _is_betable(w_ev, w_pred),
            "L_betable": _is_betable(l_ev, l_pred),
            "Best_EV": round(max(w_ev, l_ev), 1),
            "Any_betable": _is_betable(w_ev, w_pred) or _is_betable(l_ev, l_pred),
            "Lien": r.get("odds_lien", ""),
            "Tournoi": str(r.get("tourney_name") or ""),
            "Competition": str(r.get("compet") or "").title(),
            "Surface": str(r.get("surface") or ""),
            "Round": str(r.get("round") or ""),
            "Date": r.get("tourney_date"),
            "odds_maj": odds_maj_val,
        })
    out = pd.DataFrame(rows)
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out["Heure"] = out["Date"].dt.strftime("%H:%M").fillna("")
    return out.sort_values(["Date", "Match"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
_CARD_CSS = """
<style>
.fm-card {
    background: linear-gradient(160deg, rgba(18,20,28,0.98), rgba(26,28,38,0.96));
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 14px 16px;
    margin-bottom: 14px;
    transition: all 0.2s ease;
    font-family: 'Segoe UI', sans-serif;
}
.fm-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 32px rgba(0,0,0,0.55);
    border-color: rgba(100,120,200,0.25);
}
.fm-card--betable {
    border-color: rgba(50,178,150,0.35) !important;
    box-shadow: 0 0 12px rgba(50,178,150,0.06) inset;
}
.fm-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    gap: 8px;
}
.fm-tournoi {
    color: #94a3b8; font-size: 11px; flex: 1;
    min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.fm-badges { display: flex; gap: 4px; flex-shrink: 0; }
.fm-badge {
    padding: 2px 7px; border-radius: 5px; font-size: 10px;
    background: rgba(255,255,255,0.06); color: #94a3b8;
}
.fm-time { color: #e2e8f0; font-size: 13px; font-weight: 700; flex-shrink: 0; }
.fm-sides { display: flex; gap: 8px; align-items: stretch; }
.fm-side {
    flex: 1; padding: 10px 11px; border-radius: 9px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    min-width: 0;
}
.fm-side--betable {
    background: rgba(50,178,150,0.08);
    border-color: rgba(50,178,150,0.25);
}
.fm-side-name {
    font-weight: 700; font-size: 12px; color: #f1f5f9;
    margin-bottom: 7px; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
}
.fm-side-stats { display: flex; gap: 4px; flex-wrap: wrap; align-items: center; }
.fm-chip {
    background: rgba(255,255,255,0.06); color: #94a3b8;
    padding: 2px 7px; border-radius: 5px; font-size: 10px;
}
.fm-ev {
    padding: 3px 9px; border-radius: 999px;
    font-weight: 700; font-size: 10px; color: #fff;
}
.fm-vs-divider {
    display: flex; align-items: center;
    color: #334155; font-size: 11px; font-weight: 700;
    padding: 0 2px; flex-shrink: 0;
}
.fm-footer {
    display: flex; gap: 6px; margin-top: 11px;
    align-items: center; flex-wrap: wrap;
}
.fm-btn {
    text-decoration: none !important;
    padding: 4px 12px; border-radius: 6px;
    font-size: 11px; font-weight: 600; color: #fff !important;
}
.fm-btn-flash { background: #e11d48; }
.fm-btn-odds  { background: #0891b2; }
.fm-maj { color: #475569; font-size: 10px; margin-left: auto; white-space: nowrap; }
</style>
"""


def _render_match_card(r: pd.Series) -> str:
    ev_w = float(r["W_ev"])
    ev_l = float(r["L_ev"])
    ev_w_bg = _ev_color(ev_w)
    ev_l_bg = _ev_color(ev_l)
    w_cls = " fm-side--betable" if r["W_betable"] else ""
    l_cls = " fm-side--betable" if r["L_betable"] else ""
    card_cls = " fm-card--betable" if r["Any_betable"] else ""

    flash_id = r.get("ID_MATCH") or ""
    flash_url = f"https://www.flashscore.com/match/{flash_id}" if flash_id else "#"
    odds_url = r.get("Lien") or "#"

    surface_badge = f"<span class='fm-badge'>{r['Surface']}</span>" if r.get("Surface") else ""
    round_badge = f"<span class='fm-badge'>{r['Round']}</span>" if r.get("Round") else ""

    maj_text = _format_exact_ts(r.get("odds_maj"))
    maj_html = f"<span class='fm-maj'>&#128338; {maj_text}</span>" if maj_text else ""

    w_name = str(r["W_name"])
    l_name = str(r["L_name"])

    return f"""
<div class='fm-card{card_cls}'>
  <div class='fm-header'>
    <span class='fm-tournoi'>&#127967; {r['Tournoi']}</span>
    <div class='fm-badges'>{surface_badge}{round_badge}</div>
    <span class='fm-time'>&#9200; {r['Heure']}</span>
  </div>
  <div class='fm-sides'>
    <div class='fm-side{w_cls}'>
      <div class='fm-side-name'>{w_name}</div>
      <div class='fm-side-stats'>
        <span class='fm-chip'>Pred {r['W_pred']:.2f}</span>
        <span class='fm-chip'>Cote {r['W_odds']:.2f}</span>
        <span class='fm-ev' style='background:{ev_w_bg};'>EV {ev_w:+.1f}%</span>
      </div>
    </div>
    <div class='fm-vs-divider'>VS</div>
    <div class='fm-side{l_cls}'>
      <div class='fm-side-name'>{l_name}</div>
      <div class='fm-side-stats'>
        <span class='fm-chip'>Pred {r['L_pred']:.2f}</span>
        <span class='fm-chip'>Cote {r['L_odds']:.2f}</span>
        <span class='fm-ev' style='background:{ev_l_bg};'>EV {ev_l:+.1f}%</span>
      </div>
    </div>
  </div>
  <div class='fm-footer'>
    <a class='fm-btn fm-btn-flash' href='{flash_url}' target='_blank'>Flashscore</a>
    <a class='fm-btn fm-btn-odds'  href='{odds_url}'  target='_blank'>Cotes</a>
    {maj_html}
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Matchs a venir", layout="wide")
st.markdown("# Matchs a venir")
st.caption(
    f"Toutes les predictions disponibles. "
    f"Cartes vertes = EV > {MIN_MARGE:.0f}% avec cote entre {MIN_PRED_BETABLE} et {MAX_PRED_BETABLE}."
)

try:
    df = _get_future_matchs()
except Exception as e:
    st.error(f"Erreur lors du chargement des matchs : {e}")
    st.stop()

if df is None or df.empty:
    st.info("Aucun match a venir.")
    st.stop()

df = df.copy()
df["tourney_name"] = df["tourney_name"].astype(str)
df["compet"] = df["compet"].astype(str).str.title()
df["tourney_date"] = pd.to_datetime(df["tourney_date"], errors="coerce")

out = _build_match_rows(df)

# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------
comp_options = sort_competitions(out["Competition"].dropna().unique().tolist())

f1, f2, f3 = st.columns([2, 2, 2])
with f1:
    selected_comps = st.multiselect(
        "Competitions", options=comp_options, default=comp_options
    )
with f2:
    only_betable = st.toggle(
        "Opportunites uniquement",
        value=False,
        help="Afficher seulement les matchs avec au moins un cote rentable.",
    )
with f3:
    min_ev = st.slider(
        "EV minimum (meilleur cote, %)",
        min_value=-20.0,
        max_value=30.0,
        value=-20.0,
        step=1.0,
    )

if out["Date"].notna().any():
    min_dt = out["Date"].min().to_pydatetime()
    max_dt = out["Date"].max().to_pydatetime()
    if min_dt < max_dt:
        date_range = st.slider(
            "Plage date / heure",
            min_value=min_dt,
            max_value=max_dt,
            value=(min_dt, max_dt),
            format="DD/MM/YYYY HH:mm",
            step=timedelta(minutes=30),
        )
        out = out[
            (out["Date"] >= pd.to_datetime(date_range[0]))
            & (out["Date"] <= pd.to_datetime(date_range[1]))
        ]

if selected_comps:
    out = out[out["Competition"].isin(selected_comps)]
out = out[out["Best_EV"] >= float(min_ev)]
view = out[out["Any_betable"]] if only_betable else out

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
nb_matchs = len(view)
nb_opps = int(view["Any_betable"].sum())
ev_mean = float(view.loc[view["Any_betable"], "Best_EV"].mean()) if nb_opps else 0.0
ev_max = float(view["Best_EV"].max()) if not view.empty else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Matchs", f"{nb_matchs}")
k2.metric("Avec opportunite", f"{nb_opps}")
k3.metric("EV moyen (opps)", f"{ev_mean:+.1f}%")
k4.metric("EV max", f"{ev_max:+.1f}%")

st.divider()

if view.empty:
    st.info("Aucun match ne correspond aux filtres.")
    st.stop()

# ---------------------------------------------------------------------------
# Vue principale : tabs par competition -> expanders par tournoi -> grille 3 cols
# ---------------------------------------------------------------------------
st.markdown(_CARD_CSS, unsafe_allow_html=True)

comps_present = sort_competitions(view["Competition"].dropna().unique().tolist())
tabs = st.tabs([f"{c} ({(view['Competition'] == c).sum()})" for c in comps_present])

for tab, comp in zip(tabs, comps_present):
    with tab:
        sub = view[view["Competition"] == comp].sort_values(
            ["Date", "Best_EV"], ascending=[True, False]
        )
        tournament_order = (
            sub.groupby("Tournoi")["Date"].min().sort_values().index.tolist()
        )
        for tournoi in tournament_order:
            t_rows = sub[sub["Tournoi"] == tournoi]
            nb = len(t_rows)
            nb_opp = int(t_rows["Any_betable"].sum())
            opp_label = f" - {nb_opp} opp" if nb_opp else ""
            with st.expander(
                f"Tournoi {tournoi} - {nb} match{'s' if nb > 1 else ''}{opp_label}",
                expanded=(len(tournament_order) <= 3),
            ):
                rows_list = list(t_rows.iterrows())
                cols = st.columns(3)
                for i, (_, r) in enumerate(rows_list):
                    with cols[i % 3]:
                        st.markdown(_render_match_card(r), unsafe_allow_html=True)
                        is_doubles = str(r["Competition"]).lower() == "doubles"
                        feat_key = r["ID_MATCH"] if is_doubles else r.get("ID_TENNET")
                        btn_key = f"feat_{r['ID_MATCH']}_{i}"
                        if st.button(
                            "Features",
                            key=btn_key,
                            width="stretch",
                            disabled=(
                                feat_key is None
                                or (isinstance(feat_key, float) and pd.isna(feat_key))
                            ),
                        ):
                            show_features_dialog(
                                feat_key,
                                r["Competition"],
                                r["Match"],
                                id_match=r["ID_MATCH"],
                            )

# ---------------------------------------------------------------------------
# Tableau detaille + export
# ---------------------------------------------------------------------------
with st.expander("Tableau detaille", expanded=False):
    export_cols = [
        "Competition", "Tournoi", "Date", "Heure", "Match",
        "W_name", "W_pred", "W_odds", "W_ev",
        "L_name", "L_pred", "L_odds", "L_ev",
        "Best_EV", "Any_betable", "Surface", "Round",
    ]
    table = view[[c for c in export_cols if c in view.columns]].copy()
    col_config = {
        "W_pred": st.column_config.NumberColumn("Pred W", format="%.2f"),
        "L_pred": st.column_config.NumberColumn("Pred L", format="%.2f"),
        "W_odds": st.column_config.NumberColumn("Cote W", format="%.2f"),
        "L_odds": st.column_config.NumberColumn("Cote L", format="%.2f"),
        "W_ev": st.column_config.NumberColumn("EV W%", format="%+.1f"),
        "L_ev": st.column_config.NumberColumn("EV L%", format="%+.1f"),
        "Best_EV": st.column_config.NumberColumn("Best EV%", format="%+.1f"),
        "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY"),
    }
    st.dataframe(table, width="stretch", hide_index=True, column_config=col_config)
    csv_download_button(
        table,
        label="Exporter CSV",
        filename="future_matchs.csv",
        key="fm_csv",
    )
