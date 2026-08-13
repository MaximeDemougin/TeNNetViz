# ruff: noqa: E402
"""Analyse de couverture Orbitx (betfair_links).

Liste les joueurs (ATP/WTA) ayant joué des matchs depuis une date choisie
sans qu'aucun de leurs matchs n'apparaisse dans `betfair_links`. La période
n'est plus une année civile : « à partir du » permet de demander « et
depuis juin ? » sans être renvoyé au 1er janvier.
"""

from __future__ import annotations

import datetime as _dt

import pandas as pd
import streamlit as st

from data import load_players_betfair_coverage


st.set_page_config(
    layout="wide",
    page_icon="logo_TeNNet.png",
    page_title="Couverture Orbitx - TeNNet",
)
st.title("🛰️ Couverture Orbitx (betfair_links)")
st.caption(
    "Joueurs dont les matchs ne sont pas (ou peu) présents dans `betfair_links`."
)

if not st.session_state.get("logged_in", False):
    st.info("Veuillez vous connecter.")
    st.stop()

current_year = _dt.date.today().year
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    start_date = st.date_input(
        "À partir du",
        value=_dt.date(current_year, 1, 1),
        min_value=_dt.date(2015, 1, 1),
        max_value=_dt.date.today(),
        format="DD/MM/YYYY",
    )
    # Champ vidé par l'utilisateur : Streamlit rend None. On retombe sur
    # l'année civile en cours plutôt que de faire lever la page.
    if start_date is None:
        start_date = _dt.date(current_year, 1, 1)
start_label = start_date.strftime("%d/%m/%Y")
with col2:
    compet_filter = st.multiselect(
        "Compétitions",
        options=["ATP", "WTA"],
        default=["ATP", "WTA"],
    )
with col3:
    min_matches = st.slider(
        "Nombre minimum de matchs joués",
        min_value=1,
        max_value=20,
        value=1,
    )

with st.spinner("Chargement..."):
    df = load_players_betfair_coverage(start_date)

if df is None or df.empty:
    st.warning(f"Aucune donnée disponible depuis le {start_label}.")
    st.stop()

if compet_filter:
    df = df[df["compet"].isin(compet_filter)]
df = df[df["total_matches"] >= int(min_matches)]

if df.empty:
    st.info("Aucun joueur ne correspond aux filtres.")
    st.stop()

never_found = df[df["found_matches"] == 0].copy()
partial = df[(df["found_matches"] > 0) & (df["coverage_pct"] < 100)].copy()
fully_found = df[df["coverage_pct"] >= 100]

# Vue d'ensemble
total_players = df["player"].nunique()
n_never = never_found["player"].nunique()
n_partial = partial["player"].nunique()
n_full = fully_found["player"].nunique()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Joueurs analysés", total_players)
c2.metric("Jamais trouvés", n_never)
c3.metric("Couverture partielle", n_partial)
c4.metric("Couverture totale", n_full)

st.divider()
st.markdown("### ❌ Joueurs jamais trouvés dans `betfair_links`")
if never_found.empty:
    st.success("Tous les joueurs filtrés ont au moins un match lié à Betfair.")
else:
    never_display = never_found[["compet", "player", "total_matches"]].rename(
        columns={
            "compet": "Compet",
            "player": "Joueur",
            "total_matches": "Matchs joués",
        }
    )
    st.dataframe(
        never_display.sort_values("Matchs joués", ascending=False),
        width="stretch",
        hide_index=True,
    )
    st.caption(
        f"{len(never_found)} joueur(s) sans aucun match présent dans `betfair_links` "
        f"depuis le {start_label}."
    )

st.divider()
st.markdown("### 🟡 Couverture partielle")
if partial.empty:
    st.info("Aucun joueur en couverture partielle.")
else:
    partial_display = partial[
        [
            "compet",
            "player",
            "total_matches",
            "found_matches",
            "missing_matches",
            "coverage_pct",
        ]
    ].rename(
        columns={
            "compet": "Compet",
            "player": "Joueur",
            "total_matches": "Total",
            "found_matches": "Trouvés",
            "missing_matches": "Manquants",
            "coverage_pct": "Couverture %",
        }
    )
    st.dataframe(
        partial_display.sort_values(["Couverture %", "Total"], ascending=[True, False]),
        width="stretch",
        hide_index=True,
    )
    st.caption(f"{len(partial)} joueur(s) avec une couverture incomplète.")

# Bouton CSV global
csv_bytes = df.to_csv(index=False).encode("utf-8")
st.download_button(
    "📥 Télécharger le rapport complet (CSV)",
    data=csv_bytes,
    file_name=f"orbitx_coverage_depuis_{start_date.isoformat()}.csv",
    mime="text/csv",
)
