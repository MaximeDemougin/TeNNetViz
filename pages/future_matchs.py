# ruff: noqa: E402
"""Page Matchs à venir — refonte simplifiée."""

import streamlit as st
import pandas as pd
from datetime import timedelta

from data import load_future_matchs
from pages.components.charts import sort_competitions
from pages.components.features_dialog import show_features_dialog
from utils import csv_download_button


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
MIN_PRED_BETABLE = 1.1
MAX_PRED_BETABLE = 4.0
MIN_MARGE = 2.0  # EV (%) minimum pour qu'un pari soit "rentable"

COMP_COLORS = {
    "atp": "#10b981",
    "wta": "#ec4899",
    "doubles": "#8b5cf6",
    "challenger": "#6366f1",
}


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
        return "#a855f7"  # violet : edge fort
    if ev > MIN_MARGE:
        return "#32b296"  # vert : rentable
    if ev > 0:
        return "#fbbf24"  # ambre : marge faible
    return "#e04e4e"  # rouge : pas de valeur


def _build_links(row: pd.Series) -> tuple[str, str]:
    q = f"{row.get('Match', '')} {row.get('Joueur', '')}".strip().replace(" ", "+")
    odds_url = row.get("Lien") or f"https://www.oddsportal.com/search/?q={q}"
    flash_id = row.get("ID_MATCH") or ""
    flash_url = (
        f"https://www.flashscore.com/match/{flash_id}"
        if flash_id
        else f"https://www.flashscore.com/search/?q={q}"
    )
    return odds_url, flash_url


def _build_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par joueur (winner + loser) avec EV calculé."""
    # Recherche insensible à la casse pour ID_TENNET (selon driver SQL)
    cols_lower = {c.lower(): c for c in df.columns}
    id_tennet_col = cols_lower.get("id_tennet")
    rows = []
    for _, r in df.iterrows():
        match_label = f"{r.get('winner_name', '')} - {r.get('loser_name', '')}"
        raw_tennet = r.get(id_tennet_col) if id_tennet_col else None
        # Forcer en int si possible (le NULL du UNION doubles fait passer la colonne en float)
        if raw_tennet is None or (
            isinstance(raw_tennet, float) and pd.isna(raw_tennet)
        ):
            id_tennet_val = None
        else:
            try:
                id_tennet_val = int(raw_tennet)
            except (TypeError, ValueError):
                id_tennet_val = raw_tennet
        for side in ("winner", "loser"):
            pred = pd.to_numeric(r.get(f"{side}_pred"), errors="coerce")
            odds = pd.to_numeric(
                r.get("max_odds1" if side == "winner" else "max_odds2"),
                errors="coerce",
            )
            pred = float(pred) if pd.notna(pred) else 0.0
            odds = float(odds) if pd.notna(odds) else 0.0
            ev = _ev_pct(odds, pred)
            rows.append(
                {
                    "ID_MATCH": r.get("ID_MATCH"),
                    "ID_TENNET": id_tennet_val,
                    "Match": match_label,
                    "Joueur": r.get(f"{side}_name", ""),
                    "Prédiction": round(pred, 3),
                    "Cote": round(odds, 3),
                    "EV_pct": round(ev, 1),
                    "Parier ?": _is_betable(ev, pred),
                    "Lien": r.get("odds_lien", ""),
                    "Tournoi": r.get("tourney_name", ""),
                    "Compétition": (r.get("compet") or "").title(),
                    "Surface": r.get("surface", ""),
                    "Round": r.get("round", ""),
                    "Date": r.get("tourney_date"),
                }
            )
    out = pd.DataFrame(rows)
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out["Heure"] = out["Date"].dt.strftime("%H:%M").fillna("")
    return out.sort_values(["Date", "Match"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# CSS (cards)
# ---------------------------------------------------------------------------
_CARD_CSS = """
<style>
.fm-card {
    background: linear-gradient(180deg, rgba(20,22,28,0.95), rgba(28,30,36,0.9));
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.fm-card:hover {
    transform: translateY(-2px);
    border-color: rgba(50,178,150,0.35);
    box-shadow: 0 8px 22px rgba(0,0,0,0.45);
}
.fm-card-head {
    display:flex; justify-content:space-between; align-items:baseline; gap:10px;
}
.fm-player { font-weight:700; color:#ffffff; font-size:14px; }
.fm-vs { color:#9ca3af; font-size:12px; }
.fm-time { color:#cbd5e1; font-size:12px; font-weight:600; white-space:nowrap; }
.fm-meta { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
.fm-chip {
    background: rgba(255,255,255,0.05);
    color:#d1d4dc;
    padding:3px 8px;
    border-radius:6px;
    font-size:11px;
}
.fm-ev {
    padding:3px 9px;
    border-radius:999px;
    font-weight:700;
    font-size:11px;
    color:#ffffff;
}
.fm-actions { display:flex; gap:6px; margin-top:10px; }
.fm-btn {
    flex:1;
    text-align:center;
    text-decoration:none;
    padding:5px 8px;
    border-radius:6px;
    font-size:11px;
    font-weight:700;
    color:#fff;
}
.fm-btn-flash { background:#ff2d55; }
.fm-btn-odds  { background:#0ea5a0; }
</style>
"""


def _render_card(r: pd.Series) -> str:
    odds_url, flash_url = _build_links(r)
    ev = float(r["EV_pct"])
    ev_bg = _ev_color(ev)
    surface_chip = (
        f"<span class='fm-chip'>{r['Surface']}</span>" if r.get("Surface") else ""
    )
    round_chip = f"<span class='fm-chip'>{r['Round']}</span>" if r.get("Round") else ""

    # Chip clé features (ID_TENNET pour simples, ID_MATCH pour doubles)
    is_doubles = str(r.get("Compétition", "")).lower() == "doubles"
    key_label = "ID_MATCH" if is_doubles else "ID_TENNET"
    key_val = r.get("ID_MATCH") if is_doubles else r.get("ID_TENNET")
    if key_val is None or (isinstance(key_val, float) and pd.isna(key_val)):
        key_chip = f"<span class='fm-chip' style='color:#e04e4e;'>{key_label}: ∅</span>"
    else:
        try:
            key_val_disp = int(key_val)
        except (TypeError, ValueError):
            key_val_disp = key_val
        key_chip = f"<span class='fm-chip'>{key_label}: {key_val_disp}</span>"

    return f"""
<div class='fm-card'>
  <div class='fm-card-head'>
    <div>
      <div class='fm-player'>{r["Joueur"]}</div>
      <div class='fm-vs'>{r["Match"]}</div>
    </div>
    <div class='fm-time'>{r["Heure"]}</div>
  </div>
  <div class='fm-meta'>
    <span class='fm-chip'>Pred {r["Prédiction"]:.2f}</span>
    <span class='fm-chip'>Cote {r["Cote"]:.2f}</span>
    <span class='fm-ev' style='background:{ev_bg};'>EV {ev:+.1f}%</span>
    {surface_chip}
    {round_chip}
    {key_chip}
  </div>
  <div class='fm-actions'>
    <a class='fm-btn fm-btn-flash' href='{flash_url}' target='_blank'>Flashscore</a>
    <a class='fm-btn fm-btn-odds'  href='{odds_url}'  target='_blank'>Cotes</a>
  </div>
</div>
"""


# ---------------------------------------------------------------------------
# Dialog : features du match (composant partagé)
# ---------------------------------------------------------------------------
_show_features_dialog = show_features_dialog


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Matchs à venir", layout="wide")
st.markdown("# 🔮 Matchs à venir")
st.caption(
    "Prédictions et opportunités de paris à partir des cotes maximales disponibles. "
    f"Critères : EV > {MIN_MARGE:.0f}% et cote entre {MIN_PRED_BETABLE} et {MAX_PRED_BETABLE}."
)

try:
    df = _get_future_matchs()
except Exception as e:
    st.error(f"Erreur lors du chargement des matchs : {e}")
    st.stop()

if df is None or df.empty:
    st.info("Aucun match à venir.")
    st.stop()

df = df.copy()
df["tourney_name"] = df["tourney_name"].astype(str)
df["compet"] = df["compet"].astype(str).str.title()
df["tourney_date"] = pd.to_datetime(df["tourney_date"], errors="coerce")

# Debug : vérifie quelles colonnes sont retournées par la requête
with st.expander("🛠 Debug colonnes (cache requête)", expanded=False):
    st.write("Colonnes retournées :", list(df.columns))
    if st.button("♻️ Vider le cache et recharger"):
        st.cache_data.clear()
        st.rerun()

out = _build_rows(df)

# ---------------------------------------------------------------------------
# Filtres (inline en haut)
# ---------------------------------------------------------------------------
comp_options = sort_competitions(out["Compétition"].dropna().unique().tolist())

f1, f2, f3 = st.columns([2, 2, 2])
with f1:
    selected_comps = st.multiselect(
        "Compétitions", options=comp_options, default=comp_options
    )
with f2:
    only_betable = st.toggle(
        "Opportunités uniquement",
        value=True,
        help="Afficher seulement les paris jugés rentables (Parier ?).",
    )
with f3:
    min_ev = st.slider(
        "EV minimum (%)", min_value=-10.0, max_value=30.0, value=0.0, step=0.5
    )

# Plage de dates si possible
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
    out = out[out["Compétition"].isin(selected_comps)]
out = out[out["EV_pct"] >= float(min_ev)]
view = out[out["Parier ?"]] if only_betable else out

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
nb_matchs = out["Match"].nunique()
nb_opps = int(out["Parier ?"].sum())
ev_mean = float(out.loc[out["Parier ?"], "EV_pct"].mean()) if nb_opps else 0.0
ev_max = float(out["EV_pct"].max()) if not out.empty else 0.0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Matchs", f"{nb_matchs}")
k2.metric("Opportunités", f"{nb_opps}")
k3.metric("EV moyen (opps)", f"{ev_mean:+.1f}%")
k4.metric("EV max", f"{ev_max:+.1f}%")

st.divider()

if view.empty:
    st.info("Aucun match ne correspond aux filtres.")
    st.stop()

# ---------------------------------------------------------------------------
# Vue principale : tabs par compétition, regroupé par tournoi
# ---------------------------------------------------------------------------
st.markdown(_CARD_CSS, unsafe_allow_html=True)

comps_present = sort_competitions(view["Compétition"].dropna().unique().tolist())
tabs = st.tabs([f"{c} ({(view['Compétition'] == c).sum()})" for c in comps_present])

for tab, comp in zip(tabs, comps_present):
    with tab:
        sub = view[view["Compétition"] == comp]
        # Tri tournois par première date
        tournament_order = (
            sub.groupby("Tournoi")["Date"].min().sort_values().index.tolist()
        )
        for tournoi in tournament_order:
            t_rows = sub[sub["Tournoi"] == tournoi].sort_values(
                ["Date", "EV_pct"], ascending=[True, False]
            )
            with st.expander(
                f"🏟 {tournoi} — {len(t_rows)} pari{'s' if len(t_rows) > 1 else ''}",
                expanded=(len(tournament_order) <= 3),
            ):
                # Affichage en grille 3 colonnes : carte HTML + bouton Features
                rows_list = list(t_rows.iterrows())
                cols = st.columns(3)
                for i, (_, r) in enumerate(rows_list):
                    with cols[i % 3]:
                        st.markdown(_render_card(r), unsafe_allow_html=True)
                        # Clé features : ID_TENNET pour simples, ID_MATCH pour doubles
                        is_doubles = str(r["Compétition"]).lower() == "doubles"
                        feat_key = r["ID_MATCH"] if is_doubles else r.get("ID_TENNET")
                        btn_key = f"feat_{r['ID_MATCH']}_{r['Joueur']}_{i}"
                        if st.button(
                            "📊 Voir les features",
                            key=btn_key,
                            width="stretch",
                            disabled=(feat_key is None or pd.isna(feat_key)),
                        ):
                            _show_features_dialog(
                                feat_key,
                                r["Compétition"],
                                r["Match"],
                                id_match=r["ID_MATCH"],
                            )

# ---------------------------------------------------------------------------
# Tableau complet + export
# ---------------------------------------------------------------------------
with st.expander("📋 Tableau détaillé", expanded=False):
    cols = [
        "Compétition",
        "Tournoi",
        "Date",
        "Heure",
        "Match",
        "Joueur",
        "Prédiction",
        "Cote",
        "EV_pct",
        "Parier ?",
        "Surface",
        "Round",
    ]
    table = view[cols].copy()
    col_config = {
        "Prédiction": st.column_config.NumberColumn("Prédiction", format="%.2f"),
        "Cote": st.column_config.NumberColumn("Cote", format="%.2f"),
        "EV_pct": st.column_config.NumberColumn("EV %", format="%+.1f"),
        "Date": st.column_config.DatetimeColumn("Date", format="DD/MM/YYYY"),
    }
    st.dataframe(table, width="stretch", hide_index=True, column_config=col_config)
    csv_download_button(
        table,
        label="📥 Exporter CSV",
        filename="future_matchs.csv",
        key="fm_csv",
    )
