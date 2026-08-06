"""Page detail : un match, son score, ses cotes, ses points.

Le graphique superpose SIX series en cotes -- back et lay des deux joueurs,
plus le consensus bookmaker des deux cotes. Tout est en cotes, donc sur une
echelle commune : c'est ce qu'on paie reellement.

Les traits verticaux marquent les fins de jeu et de set, qui se deduisent du
score seul et sont donc exactes. Aucun break n'y figure : il exigerait de
savoir qui servait, et le champ serveur de la source se contredit dans 13 %
des jeux.
"""

import time

import pandas as pd
import streamlit as st

from detail_match import afficher
from live_data import (
    charger_matchs,
    charger_serie,
)

st.set_page_config(layout="wide")

if not st.session_state.get("logged_in", False):
    st.write("Connectez-vous pour voir le detail d'un match.")
    st.stop()

def _etiquette_match(ligne) -> str:
    """« P1 vs P2 -- score (statut) », sans jamais ecrire « nan ».

    NaN est VRAI au sens booleen : `valeur or defaut` laisserait donc passer
    le flottant NaN que pandas rend pour un NULL SQL, et l'afficherait
    litteralement. Meme regle que ``_champ`` plus bas.
    """

    def _v(cle: str, defaut: str = "") -> str:
        valeur = ligne.get(cle)
        return defaut if valeur is None or pd.isna(valeur) else str(valeur)

    texte = f"{_v('participant1', '?')} vs {_v('participant2', '?')}"
    score = _v("score")
    statut = _v("status")
    if score:
        texte += f" -- {score}"
    if statut:
        texte += f" ({statut})"
    return texte


event_id = st.query_params.get("event_id")
if not event_id:
    # Cette page est inscrite au menu lateral : on y arrive donc sans passer
    # par la liste, et sans parametre dans l'URL. Repondre « revenez a la
    # page En direct » faisait de l'entree de menu une impasse -- constate a
    # l'usage. La page choisit elle-meme plutot que de renvoyer ailleurs.
    try:
        publies = charger_matchs()
    except Exception:
        # Meme garde que partout ailleurs dans ces deux pages : une base
        # injoignable donne un message lisible, jamais la trace Python.
        st.error("Base de donnees injoignable. Reessayez plus tard.")
        st.stop()
    if publies.empty:
        st.info("Aucun match publie pour l'instant.")
        st.stop()
    st.title("Detail d'un match")
    # Les matchs en cours en tete : c'est ce qu'on vient regarder. Les
    # termines restent proposes -- leur serie vit sept jours
    # (PUBLISH_RETENTION_DAYS), et c'est justement la qu'on relit un match
    # apres coup.
    if "en_cours" in publies.columns:
        publies = publies.sort_values("en_cours", ascending=False, kind="stable")
    etiquettes = {
        str(ligne["event_id"]): _etiquette_match(ligne)
        for _, ligne in publies.iterrows()
    }
    choix = st.selectbox(
        "Choisir un match",
        list(etiquettes),
        format_func=lambda e: etiquettes[e],
        key="choix_match_detail",
    )
    if st.button("Ouvrir"):
        st.query_params["event_id"] = choix
        st.rerun()
    st.stop()

CADENCES = {"5 s": 5, "15 s": 15, "60 s": 60, "Manuel": None}
choix = st.sidebar.selectbox(
    "Rafraichissement", list(CADENCES), index=1, key="cadence_match"
)
periode = CADENCES[choix]


def _champ(m, cle: str, defaut: str) -> str:
    """Lit un champ d'affichage sans jamais rendre le texte "nan".

    ``m.get(cle) or defaut`` echoue sur un NaN flottant : NaN est vrai au
    sens booleen (``bool(float("nan")) is True``), donc l'expression rend le
    NaN lui-meme et ``str(float("nan"))`` affiche litteralement "nan" a
    l'ecran -- pas une absence, un texte errone. ``pd.notna`` traite None,
    NaN et NaT tous comme "absent", ce que le booleen ne fait pas.
    """
    valeur = m.get(cle)
    return str(valeur) if pd.notna(valeur) else defaut


@st.fragment(run_every=periode)
def zone_donnees():
    try:
        matchs = charger_matchs()
    except Exception:
        # Meme garde que pages/live.py : base injoignable (reseau,
        # identifiants, table absente...) -> message explicite, jamais la
        # trace Python brute a l'ecran.
        st.error("Base de donnees injoignable. Reessayez plus tard.")
        return

    if matchs.empty:
        # Table vide (aucun match publie) : matchs['event_id'] leverait un
        # KeyError sur ce DataFrame sans colonnes. Meme message que le cas
        # "ce match precis n'y est plus" : de son point de vue, le match
        # demande est introuvable dans les deux cas.
        st.warning("Ce match n'est plus publie.")
        return

    # L'URL peut porter PLUSIEURS identifiants separes par des virgules : la
    # source en attribue parfois deux ou trois a une meme rencontre, et
    # `charger_matchs` les a fusionnes en une ligne portant `event_ids`. On
    # cherche donc une APPARTENANCE au groupe, pas une egalite -- sinon une
    # URL portant l'identifiant secondaire ne retrouverait plus son match.
    demandes = {e.strip() for e in str(event_id).split(",") if e.strip()}
    if "event_ids" in matchs.columns:
        appartient = matchs["event_ids"].map(
            lambda ids: bool(demandes & {i.strip() for i in str(ids).split(",")})
        )
        ligne = matchs[appartient]
    else:
        # event_id fait partie du schema garanti de live_now (c'est la cle de
        # jointure avec live_series, cf. live_data.py) : repli legitime.
        ligne = matchs[matchs["event_id"].astype(str).isin(demandes)]
    if ligne.empty:
        st.warning("Ce match n'est plus publie.")
        return
    m = ligne.iloc[0]

    try:
        # TOUS les identifiants du match : la serie est repartie entre eux
        # quand la source en a emis plusieurs.
        serie = charger_serie(_champ(m, "event_ids", "") or event_id)
    except Exception:
        st.error("Base de donnees injoignable. Reessayez plus tard.")
        return

    # Le rendu vit dans `detail_match`, PARTAGE avec la page « En direct » qui
    # l'affiche sous sa liste. L'ecrire deux fois garantirait qu'une
    # correction n'atterrisse que d'un cote -- un ecart qui ne se voit qu'a
    # l'usage, longtemps apres.
    afficher(m, serie, time.time())


zone_donnees()
