# ruff: noqa: E402
"""Monitoring dedicated page for WS_odds snapshots."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import MAX_PRED_BETABLE, MIN_PRED_BETABLE
from data import load_ws_odds_monitor
from pages.components.charts import sort_competitions
from utils import csv_download_button, now_paris

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # fallback si la dépendance n'est pas installée
    st_autorefresh = None


ORBITX_MARKET_URL_TEMPLATE = (
    "https://www.orbitxch.com/customer/sport/2/market/{market_id}"
)


st.set_page_config(
    layout="wide",
    page_icon="logo_TeNNet.png",
    page_title="Monitoring WS_odds",
)
st.title("Monitoring WS_odds")
st.caption(
    "Vue de monitoring des cotes reelles WS (home/away back-lay), "
    "avec contexte match et tri par derniere mise a jour."
)

if not st.session_state.get("logged_in", False):
    st.info("Veuillez vous connecter.")
    st.stop()


REFRESH_INTERVAL_MS = 60_000
if st_autorefresh is not None:
    st_autorefresh(interval=REFRESH_INTERVAL_MS, key="ws_odds_monitor_autorefresh")

with st.sidebar:
    if st.button(
        "Rafraîchir les données",
        use_container_width=True,
        key="refresh_ws_odds_monitor",
    ):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()
    st.caption(f"Dernière mise à jour : {now_paris().strftime('%H:%M:%S')}")

    st.divider()
    st.markdown("### Vue graphique")
    layout_choice = st.radio(
        "Layout",
        options=["▤ 1 colonne", "▥ 2 colonnes", "▦ 3 colonnes"],
        index=1,
        key="ws_layout_choice",
        label_visibility="collapsed",
    )

LAYOUT_TO_COLS = {
    "▤ 1 colonne": 1,
    "▥ 2 colonnes": 2,
    "▦ 3 colonnes": 3,
}


def _get_ws_data() -> pd.DataFrame:
    return load_ws_odds_monitor()


def _as_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _fmt_odd(v) -> str:
    if pd.isna(v):
        return "-"
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "-"


def _fmt_size(v) -> str:
    if v is None or pd.isna(v):
        return ""
    try:
        f = float(v)
    except Exception:
        return ""
    if f <= 0:
        return ""
    if f >= 1000:
        return f"{f / 1000:.1f}k"
    return f"{f:.0f}"


def _cell(cls: str, odd, size) -> str:
    return (
        f"<strong class='{cls}'>"
        f"<span class='ws-odd'>{_fmt_odd(odd)}</span>"
        f"<span class='ws-size'>{_fmt_size(size)}</span>"
        f"</strong>"
    )


def _fmt_ts(v) -> str:
    ts = pd.to_datetime(v, errors="coerce")
    if pd.isna(ts):
        return "-"
    return ts.strftime("%d/%m %H:%M:%S")


def _orbitx_url(market_id) -> str | None:
    mid = str(market_id).strip() if market_id is not None else ""
    if not mid:
        return None
    return ORBITX_MARKET_URL_TEMPLATE.format(market_id=mid)


MIN_MARGE = 2.0


def _ev_pct(odds: float, pred: float) -> float:
    if not odds or not pred or pred <= 0:
        return 0.0
    # Lay-only EV: profitable when lay odds are below predicted fair odds.
    return (pred / odds - 1.0) * 100.0


def _is_betable(ev: float, pred: float) -> bool:
    return ev > MIN_MARGE and (MIN_PRED_BETABLE <= pred <= MAX_PRED_BETABLE)


def _market_card_html(row: pd.Series) -> str:
    inplay_badge = "INPLAY" if bool(row.get("is_inplay_effective", False)) else "PRE"
    match_label = str(row.get("match_label") or "-")
    tournament = str(row.get("tourney_name") or "-")
    status = str(row.get("status") or "-")
    compet = str(row.get("compet") or "-")
    kickoff = str(row.get("kickoff_hhmm") or "-")
    home_name = str(row.get("winner_name") or "Joueur1")
    away_name = str(row.get("loser_name") or "Joueur2")
    orbitx_url = _orbitx_url(row.get("ID_MARKET"))
    pred_w = row.get("pred_w_used")
    pred_l = row.get("pred_l_used")
    ev_w = row.get("w_ev")
    ev_l = row.get("l_ev")
    led_match = bool(row.get("match_betable", False))
    w_lay_cls = (
        "v-best-lay rentable" if bool(row.get("w_betable", False)) else "v-best-lay"
    )
    l_lay_cls = (
        "v-best-lay rentable" if bool(row.get("l_betable", False)) else "v-best-lay"
    )

    pred_line = (
        f"Pred W {_fmt_odd(pred_w)} | Pred L {_fmt_odd(pred_l)} | "
        f"EV Lay W {float(ev_w):+.1f}% | EV Lay L {float(ev_l):+.1f}%"
        if pd.notna(pred_w) and pd.notna(pred_l)
        else "Predictions indisponibles"
    )

    return f"""
<div class='ws-card'>
    <div class='ws-head'>
        <div class='ws-left'>
            <div class='ws-match'>{match_label}</div>
            <div class='ws-meta'>{tournament} | {compet} | {status} | Début {kickoff}</div>
            <div class='ws-meta'>{pred_line}</div>
        </div>
        <div class='ws-right'>
            <span class='ws-pill {"ws-pill-inplay" if inplay_badge == "INPLAY" else "ws-pill-pre"}'>{inplay_badge}</span>
            <span class='ws-pill {"ws-led-on" if led_match else "ws-led-off"}'>{"BET" if led_match else "NO BET"}</span>
            <span class='ws-link'>{f"<a href='{orbitx_url}' target='_blank' rel='noopener noreferrer'>OrbitX</a>" if orbitx_url else ""}</span>
            <span class='ws-time'>Maj {_fmt_ts(row.get("updated_at"))}</span>
        </div>
    </div>
    <div class='ws-book'>
        <div class='ws-grid-head'>
            <span class='p-col'>Joueur</span>
            <span>B2</span>
            <span>B1</span>
            <span>BB</span>
            <span>LB</span>
            <span>L1</span>
            <span>L2</span>
        </div>
        <div class='ws-grid-row'>
            <span class='p-col'>{home_name}</span>
            {_cell("v-back", row.get("home_back_2"), row.get("home_back_2_size"))}
            {_cell("v-back", row.get("home_back_1"), row.get("home_back_1_size"))}
            {_cell("v-best-back", row.get("best_home_back"), row.get("best_home_back_size"))}
            {_cell(w_lay_cls, row.get("best_home_lay"), row.get("best_home_lay_size"))}
            {_cell("v-lay", row.get("home_lay_1"), row.get("home_lay_1_size"))}
            {_cell("v-lay", row.get("home_lay_2"), row.get("home_lay_2_size"))}
        </div>
        <div class='ws-grid-row'>
            <span class='p-col'>{away_name}</span>
            {_cell("v-back", row.get("away_back_2"), row.get("away_back_2_size"))}
            {_cell("v-back", row.get("away_back_1"), row.get("away_back_1_size"))}
            {_cell("v-best-back", row.get("best_away_back"), row.get("best_away_back_size"))}
            {_cell(l_lay_cls, row.get("best_away_lay"), row.get("best_away_lay_size"))}
            {_cell("v-lay", row.get("away_lay_1"), row.get("away_lay_1_size"))}
            {_cell("v-lay", row.get("away_lay_2"), row.get("away_lay_2_size"))}
        </div>
        <div class='ws-best'>Spread H {_fmt_odd(row.get("home_spread"))} | Spread A {_fmt_odd(row.get("away_spread"))}</div>
    </div>
</div>
"""


_WS_CSS = """
<style>
.ws-card {
    border: 1px solid rgba(255,255,255,0.08);
    background: linear-gradient(160deg, rgba(17,20,28,0.96), rgba(28,32,44,0.93));
    border-radius: 14px;
    padding: 12px;
    margin-bottom: 10px;
}
.ws-head {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: center;
    margin-bottom: 10px;
}
.ws-match {
    font-weight: 700;
    color: #f1f5f9;
}
.ws-meta {
    color: #94a3b8;
    font-size: 11px;
}
.ws-right {
    display: flex;
    gap: 8px;
    align-items: center;
}
.ws-pill {
    border-radius: 999px;
    font-size: 10px;
    padding: 2px 8px;
    background: rgba(255,255,255,0.09);
    color: #cbd5e1;
}
.ws-pill-inplay {
    background: rgba(253, 224, 71, 0.9);
    color: #3f2f00;
    border: 1px solid rgba(253, 224, 71, 0.95);
}
.ws-pill-pre {
    background: rgba(255,255,255,0.09);
    color: #cbd5e1;
}
.ws-led-on {
    background: rgba(46, 204, 113, 0.2);
    color: #8ef2b5;
    border: 1px solid rgba(46, 204, 113, 0.45);
}
.ws-led-off {
    background: rgba(239, 68, 68, 0.18);
    color: #f7b4b4;
    border: 1px solid rgba(239, 68, 68, 0.45);
}
.ws-time {
    color: #cbd5e1;
    font-size: 11px;
}
.ws-link a {
    color: #93c5fd;
    font-size: 11px;
    text-decoration: none;
    font-weight: 700;
}
.ws-link a:hover {
    text-decoration: underline;
}
.ws-book {
    display: block;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    padding: 9px;
}
.ws-grid-head,
.ws-grid-row {
    display: grid;
    grid-template-columns: 1.8fr repeat(6, 1fr);
    gap: 6px;
    align-items: center;
    margin-bottom: 6px;
}
.ws-grid-head span {
    font-size: 11px;
    color: #94a3b8;
    font-weight: 700;
    text-align: center;
}
.ws-grid-row .p-col {
    font-size: 12px;
    color: #e2e8f0;
    text-align: left;
    font-weight: 700;
    padding-left: 2px;
}
.ws-grid-row strong {
    text-align: center;
    font-size: 14px;
    border-radius: 6px;
    padding: 6px 4px;
    display: flex;
    flex-direction: column;
    align-items: center;
    line-height: 1.08;
}
.ws-grid-row strong .ws-odd {
    font-size: 14px;
    font-weight: 700;
}
.ws-grid-row strong .ws-size {
    font-size: 10px;
    font-weight: 500;
    opacity: 0.8;
    margin-top: 1px;
}
.v-back {
    background: transparent;
    color: #e2e8f0;
    border: 1px solid rgba(120, 195, 255, 0.35);
    box-shadow: inset 0 0 0 1px rgba(120, 195, 255, 0.08);
}
.v-lay {
    background: transparent;
    color: #e2e8f0;
    border: 1px solid rgba(255, 168, 192, 0.35);
    box-shadow: inset 0 0 0 1px rgba(255, 168, 192, 0.08);
}
.v-best-back {
    background: rgba(67, 153, 239, 0.95);
    color: #07233f;
    box-shadow: inset 0 0 0 1px rgba(7, 35, 63, 0.25);
}
.v-best-lay {
    background: rgba(236, 114, 152, 0.95);
    color: #3b0c1d;
    box-shadow: inset 0 0 0 1px rgba(59, 12, 29, 0.25);
}
.v-best-lay.rentable {
    border: 2px solid #22c55e;
    box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.35), inset 0 0 0 1px rgba(59, 12, 29, 0.25);
}
.ws-best {
    margin-top: 2px;
    color: #94a3b8;
    font-size: 11px;
}
@media (max-width: 900px) {
    .ws-grid-head,
    .ws-grid-row {
        grid-template-columns: 1.8fr repeat(3, 1fr);
    }
}
</style>
"""


with st.spinner("Chargement WS_odds..."):
    df = _get_ws_data()

if df is None or df.empty:
    st.warning("Aucune ligne disponible dans WS_odds.")
    st.stop()

df = df.copy()
# Exclure les matchs terminés (match_settled vrai)
if "match_settled" in df.columns:
    settled = pd.to_numeric(df["match_settled"], errors="coerce").fillna(0)
    df = df[settled == 0].copy()
if df.empty:
    st.info("Aucun match en cours ou à venir.")
    st.stop()
df["updated_at"] = pd.to_datetime(df.get("updated_at"), errors="coerce")
df["tourney_date"] = pd.to_datetime(df.get("tourney_date"), errors="coerce")
now_ts = pd.Timestamp(now_paris())
inplay_raw = _as_float(df.get("inplay", pd.Series(index=df.index, dtype=float))).fillna(
    0
)
df["is_inplay_effective"] = (inplay_raw == 1) | (
    df["tourney_date"].notna() & (df["tourney_date"] <= now_ts)
)
df["kickoff_hhmm"] = df["tourney_date"].dt.strftime("%H:%M").fillna("-")
df["match_label"] = (
    df.get("winner_name", "").astype(str) + " - " + df.get("loser_name", "").astype(str)
)
df["compet"] = df.get("compet", "unknown").astype(str).str.upper()
df["status"] = df.get("status", "").astype(str)
df["orbitx_link"] = df["ID_MARKET"].apply(_orbitx_url)

for col in [
    "home_back",
    "home_back_1",
    "home_back_2",
    "home_lay",
    "home_lay_1",
    "home_lay_2",
    "away_back",
    "away_back_1",
    "away_back_2",
    "away_lay",
    "away_lay_1",
    "away_lay_2",
]:
    if col in df.columns:
        df[col] = _as_float(df[col])

for col in ["pred_w_used", "pred_l_used"]:
    if col in df.columns:
        df[col] = _as_float(df[col])

home_back_cols = ["home_back", "home_back_1", "home_back_2"]
home_lay_cols = ["home_lay", "home_lay_1", "home_lay_2"]
away_back_cols = ["away_back", "away_back_1", "away_back_2"]
away_lay_cols = ["away_lay", "away_lay_1", "away_lay_2"]

df["best_home_back"] = df[home_back_cols].max(axis=1, skipna=True)
df["best_away_back"] = df[away_back_cols].max(axis=1, skipna=True)
df["best_home_lay"] = df[home_lay_cols].min(axis=1, skipna=True)
df["best_away_lay"] = df[away_lay_cols].min(axis=1, skipna=True)


def _pick_size(row, odd_cols, size_cols, best_value):
    if pd.isna(best_value):
        return None
    for oc, sc in zip(odd_cols, size_cols):
        v = row.get(oc)
        if pd.notna(v) and float(v) == float(best_value):
            return row.get(sc)
    return None


home_back_size_cols = ["home_back_size", "home_back_1_size", "home_back_2_size"]
home_lay_size_cols = ["home_lay_size", "home_lay_1_size", "home_lay_2_size"]
away_back_size_cols = ["away_back_size", "away_back_1_size", "away_back_2_size"]
away_lay_size_cols = ["away_lay_size", "away_lay_1_size", "away_lay_2_size"]

for col in (
    home_back_size_cols + home_lay_size_cols + away_back_size_cols + away_lay_size_cols
):
    if col in df.columns:
        df[col] = _as_float(df[col])
    else:
        df[col] = pd.NA

df["best_home_back_size"] = df.apply(
    lambda r: _pick_size(r, home_back_cols, home_back_size_cols, r["best_home_back"]),
    axis=1,
)
df["best_away_back_size"] = df.apply(
    lambda r: _pick_size(r, away_back_cols, away_back_size_cols, r["best_away_back"]),
    axis=1,
)
df["best_home_lay_size"] = df.apply(
    lambda r: _pick_size(r, home_lay_cols, home_lay_size_cols, r["best_home_lay"]),
    axis=1,
)
df["best_away_lay_size"] = df.apply(
    lambda r: _pick_size(r, away_lay_cols, away_lay_size_cols, r["best_away_lay"]),
    axis=1,
)

df["home_spread"] = df["best_home_lay"] - df["best_home_back"]
df["away_spread"] = df["best_away_lay"] - df["best_away_back"]
df["w_ev"] = df.apply(
    lambda r: _ev_pct(r.get("best_home_back"), r.get("pred_w_used")), axis=1
)
df["l_ev"] = df.apply(
    lambda r: _ev_pct(r.get("best_away_back"), r.get("pred_l_used")), axis=1
)
df["w_betable"] = df.apply(
    lambda r: _is_betable(float(r.get("w_ev") or 0), float(r.get("pred_w_used") or 0)),
    axis=1,
)
df["l_betable"] = df.apply(
    lambda r: _is_betable(float(r.get("l_ev") or 0), float(r.get("pred_l_used") or 0)),
    axis=1,
)
df["match_betable"] = df["w_betable"] | df["l_betable"]

# ---------------------------------------------------------------------------
# Filtres
# ---------------------------------------------------------------------------
f1, f2, f3, f4, f5 = st.columns([2, 2, 1, 1, 3])
with f1:
    comp_options = sort_competitions(df["compet"].dropna().unique().tolist())
    selected_comp = st.multiselect(
        "Competition",
        options=comp_options,
        default=comp_options,
    )
with f2:
    status_options = sorted([x for x in df["status"].dropna().unique().tolist() if x])
    selected_status = st.multiselect(
        "Status",
        options=status_options,
        default=status_options,
    )
with f3:
    only_pre = st.toggle("Pré-match uniquement", value=True)
with f4:
    bet_mode = st.selectbox(
        "Statut pari",
        options=["Tous", "BET uniquement", "NO BET uniquement"],
        index=0,
    )
with f5:
    search_text = (
        st.text_input("Recherche match / market / tournoi", value="").strip().lower()
    )

view = df.copy()
if selected_comp:
    view = view[view["compet"].isin(selected_comp)]
if selected_status:
    view = view[view["status"].isin(selected_status)]
if only_pre:
    view = view[~view["is_inplay_effective"]]
if bet_mode == "BET uniquement":
    view = view[view["match_betable"] == True]
elif bet_mode == "NO BET uniquement":
    view = view[view["match_betable"] == False]
if search_text:
    key_cols = ["match_label", "ID_MATCH", "ID_MARKET", "tourney_name"]
    mask = pd.Series(False, index=view.index)
    for c in key_cols:
        if c in view.columns:
            mask = mask | view[c].astype(str).str.lower().str.contains(
                search_text, na=False
            )
    view = view[mask]

if view.empty:
    st.info("Aucune ligne ne correspond aux filtres.")
    st.stop()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
rows_count = len(view)
inplay_count = int(view["is_inplay_effective"].sum())
mean_updates = float(
    _as_float(view.get("n_updates", pd.Series(dtype=float))).fillna(0).mean()
)
last_upd = view["updated_at"].max()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Lignes WS_odds", f"{rows_count}")
k2.metric("Inplay", f"{inplay_count}")
k3.metric("Moyenne updates", f"{mean_updates:.1f}")
k4.metric(
    "Derniere update",
    last_upd.strftime("%d/%m %H:%M:%S") if pd.notna(last_upd) else "-",
)
with st.sidebar:
    st.caption(
        f"Dernière maj data WS : {last_upd.strftime('%d/%m %H:%M:%S') if pd.notna(last_upd) else '-'}"
    )

st.divider()

# ---------------------------------------------------------------------------
# Affichage graphique type Betfair
# ---------------------------------------------------------------------------
st.markdown("### Vue graphique des marches")
st.markdown(_WS_CSS, unsafe_allow_html=True)

st.caption(
    "Back en bleu, Lay en rose. Chaque ligne montre les 3 niveaux de prix et le spread estimé."
)

grid_cols = LAYOUT_TO_COLS.get(layout_choice, 3)

cards_df = view.sort_values(
    ["tourney_date", "match_label"], ascending=[True, True], na_position="last"
)

comp_order = sort_competitions(cards_df["compet"].dropna().unique().tolist())
for comp in comp_order:
    comp_df = cards_df[cards_df["compet"] == comp].copy()
    if comp_df.empty:
        continue

    st.markdown(f"#### {comp} ({len(comp_df)})")
    tournoi_order = (
        comp_df.groupby("tourney_name")["tourney_date"]
        .min()
        .sort_values(na_position="last")
        .index.tolist()
    )

    for tournoi in tournoi_order:
        t_df = comp_df[comp_df["tourney_name"] == tournoi].sort_values(
            ["tourney_date", "match_label"], ascending=[True, True], na_position="last"
        )
        if t_df.empty:
            continue

        tourney_label = str(tournoi) if str(tournoi).strip() else "Tournoi inconnu"
        with st.expander(
            f"{tourney_label} ({len(t_df)})",
            expanded=(len(tournoi_order) <= 2),
        ):
            grid = st.columns(int(grid_cols))
            for idx, (_, r) in enumerate(t_df.iterrows()):
                with grid[idx % int(grid_cols)]:
                    st.markdown(_market_card_html(r), unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Table detaillee
# ---------------------------------------------------------------------------
display_cols = [
    "updated_at",
    "compet",
    "status",
    "inplay",
    "is_inplay_effective",
    "ID_MATCH",
    "ID_MARKET",
    "orbitx_link",
    "match_label",
    "tourney_name",
    "tourney_date",
    "kickoff_hhmm",
    "home_back",
    "home_back_1",
    "home_back_2",
    "pred_w_used",
    "best_home_back",
    "w_ev",
    "w_betable",
    "home_lay",
    "home_lay_1",
    "home_lay_2",
    "best_home_lay",
    "home_spread",
    "away_back",
    "away_back_1",
    "away_back_2",
    "pred_l_used",
    "best_away_back",
    "l_ev",
    "l_betable",
    "away_lay",
    "away_lay_1",
    "away_lay_2",
    "best_away_lay",
    "away_spread",
    "match_betable",
    "n_updates",
]

show = view[[c for c in display_cols if c in view.columns]].copy()
show = show.sort_values(
    ["updated_at", "inplay", "n_updates"], ascending=[False, False, False]
)

col_cfg = {
    "updated_at": st.column_config.DatetimeColumn(
        "Maj WS", format="DD/MM/YYYY HH:mm:ss"
    ),
    "tourney_date": st.column_config.DatetimeColumn(
        "Date match", format="DD/MM/YYYY HH:mm"
    ),
    "kickoff_hhmm": st.column_config.TextColumn("Heure match"),
    "is_inplay_effective": st.column_config.CheckboxColumn("Inplay effectif"),
    "orbitx_link": st.column_config.LinkColumn("OrbitX", display_text="ouvrir"),
    "home_back": st.column_config.NumberColumn("H Back", format="%.3f"),
    "home_back_1": st.column_config.NumberColumn("H Back 1", format="%.3f"),
    "home_back_2": st.column_config.NumberColumn("H Back 2", format="%.3f"),
    "pred_w_used": st.column_config.NumberColumn("Pred W", format="%.3f"),
    "best_home_back": st.column_config.NumberColumn("Best H Back", format="%.3f"),
    "w_ev": st.column_config.NumberColumn("EV W%", format="%+.1f"),
    "w_betable": st.column_config.CheckboxColumn("W betable"),
    "home_lay": st.column_config.NumberColumn("H Lay", format="%.3f"),
    "home_lay_1": st.column_config.NumberColumn("H Lay 1", format="%.3f"),
    "home_lay_2": st.column_config.NumberColumn("H Lay 2", format="%.3f"),
    "best_home_lay": st.column_config.NumberColumn("Best H Lay", format="%.3f"),
    "home_spread": st.column_config.NumberColumn("Spread H", format="%.3f"),
    "away_back": st.column_config.NumberColumn("A Back", format="%.3f"),
    "away_back_1": st.column_config.NumberColumn("A Back 1", format="%.3f"),
    "away_back_2": st.column_config.NumberColumn("A Back 2", format="%.3f"),
    "pred_l_used": st.column_config.NumberColumn("Pred L", format="%.3f"),
    "best_away_back": st.column_config.NumberColumn("Best A Back", format="%.3f"),
    "l_ev": st.column_config.NumberColumn("EV L%", format="%+.1f"),
    "l_betable": st.column_config.CheckboxColumn("L betable"),
    "away_lay": st.column_config.NumberColumn("A Lay", format="%.3f"),
    "away_lay_1": st.column_config.NumberColumn("A Lay 1", format="%.3f"),
    "away_lay_2": st.column_config.NumberColumn("A Lay 2", format="%.3f"),
    "best_away_lay": st.column_config.NumberColumn("Best A Lay", format="%.3f"),
    "away_spread": st.column_config.NumberColumn("Spread A", format="%.3f"),
    "match_betable": st.column_config.CheckboxColumn("Match betable"),
}

st.dataframe(show, width="stretch", hide_index=True, column_config=col_cfg)
csv_download_button(
    show,
    label="Exporter CSV WS_odds",
    filename="ws_odds_monitor.csv",
    key="ws_odds_monitor_csv",
)
