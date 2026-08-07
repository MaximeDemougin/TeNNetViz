"""La regle d'affichage : tout tableau a axe TEMPOREL se lit du plus recent
au plus ancien.

Ce module tient les tableaux des pages heritees -- « Alertes », « Matchs a
venir », et le tableau groupe du tableau de bord. Ceux des pages du PoC
(bilan de collecte, liste des matchs, point par point, recit des jeux) sont
tenus la ou ils vivent, dans `test_bilan_collecte.py` et
`test_pages_match.py`.

LE PIEGE QUE CES TESTS EXISTENT POUR ATTRAPER : ces pages affichent leurs
dates en `jj/mm/aaaa`, un TEXTE. Trier ce texte donne un ordre
alphabetique -- « 30/07/2026 » y passe AVANT « 05/08/2026 ». Les quatre
rencontres reelles de `MATCHS_REELS_A_VENIR` ont ete choisies pour que les
deux ordres soient presque opposes : un tri sur le texte est donc FATAL au
test, la ou quatre dates du meme mois l'auraient laisse passer.

Les tableaux se relisent depuis le rendu REEL de la page (`AppTest`), pas
depuis une fonction rejouee : ce qui compte est ce que voit l'utilisateur.
"""

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from fixtures_reelles import MATCHS_REELS_A_VENIR

#: L'ordre du TEMPS decroissant sur les quatre rencontres reelles. Ecrit une
#: fois, en toutes lettres, pour que l'attente soit lisible sans recalcul.
ATTENDU_DECROISSANT = [
    "Luciano",   # Darderi,   2026-08-05 00:30
    "Rafael",    # Jodar,     2026-08-02 00:00
    "Denis",     # Yevseyev,  2026-07-30 08:00
    "Frances",   # Tiafoe,    2026-07-28 00:00
]

#: Ce que rendrait un tri sur le TEXTE « jj/mm/aaaa ». Aucun test ne doit
#: jamais l'obtenir -- il est ici pour que l'echec le nomme.
ORDRE_DU_TEXTE = ["Denis", "Frances", "Luciano", "Rafael"]  # 30/07 28/07 05/08 02/08


def _melangees():
    """Les quatre rencontres REELLES, dans un ordre qui n'est ni celui du
    temps ni celui du texte.

    Une entree deja triee laisserait passer une page qui recopie son entree
    sans rien trier -- exactement l'etat de `alerts.py` avant ce tour, ou la
    requete elle-meme n'a aucun `ORDER BY` (trois `SELECT` en `UNION ALL`).
    """
    return pd.DataFrame([MATCHS_REELS_A_VENIR[i] for i in (2, 0, 3, 1)])


def _premier_mot(valeurs):
    """Le prenom du premier joueur de chaque libelle « A B - C D »."""
    return [str(v).split()[0] for v in valeurs]


# ══════════════════════════════════════════════════════════════════════
# Page « Alertes » : les matchs de l'heure absents de `betfair_links`
# ══════════════════════════════════════════════════════════════════════


def _page_alertes(monkeypatch, manquants):
    import data

    monkeypatch.setattr(
        data, "load_future_matchs_missing_betfair",
        lambda within_minutes=60: manquants)
    monkeypatch.setattr(data, "load_future_matchs", lambda: pd.DataFrame())
    monkeypatch.setattr(data, "load_inplay_bets", lambda uid: pd.DataFrame())
    monkeypatch.setattr(
        data, "prepare_bets_data",
        lambda uid, finished=True: pd.DataFrame())

    at = AppTest.from_file("pages/alerts.py", default_timeout=60)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.run()
    assert not at.exception, at.exception
    return at


def _tableau_betfair(at):
    """Le tableau des matchs sans lien Betfair, reconnu par ses colonnes."""
    for d in at.dataframe:
        if {"Date", "Compet", "Match"} <= set(d.value.columns):
            return d.value
    return None


def test_alertes_les_matchs_sans_lien_betfair_sont_du_plus_recent_au_plus_ancien(
        monkeypatch):
    """Ce tableau n'avait AUCUN tri : la requete est un `UNION ALL` de trois
    `SELECT` sans `ORDER BY`, donc l'ordre affiche etait celui que la base
    voulait bien rendre.

    Et sa colonne « Date » est du TEXTE `jj/mm/aaaa hh:mm` : trier apres la
    mise en forme donnerait l'ordre alphabetique, que ce test nomme.
    """
    at = _page_alertes(monkeypatch, _melangees())
    table = _tableau_betfair(at)
    assert table is not None, "tableau des matchs sans lien Betfair introuvable"

    assert _premier_mot(table["Match"]) == ATTENDU_DECROISSANT, \
        table.to_dict("records")
    assert _premier_mot(table["Match"]) != ORDRE_DU_TEXTE, \
        "le tri porte sur le TEXTE de la date, pas sur la date"
    # La date AFFICHEE reste celle de sa ligne : trier une colonne seule les
    # decorrelerait, et chaque match porterait la date d'un autre.
    assert list(table["Date"]) == ["05/08/2026 00:30", "02/08/2026 00:00",
                                   "30/07/2026 08:00", "28/07/2026 00:00"], \
        table.to_dict("records")


def test_alertes_un_match_SANS_DATE_ne_prend_pas_la_tete(monkeypatch):
    """Une date absente ne peut pas passer pour la plus recente -- ni faire
    lever la page. Elle part en fin de tableau."""
    sans_date = dict(MATCHS_REELS_A_VENIR[0])
    sans_date.update({"tourney_date": None, "ID_MATCH": "SANSDATE",
                      "winner_name": "Zzz Inconnu"})
    at = _page_alertes(
        monkeypatch, pd.DataFrame([sans_date] + MATCHS_REELS_A_VENIR))
    table = _tableau_betfair(at)
    assert table is not None
    assert _premier_mot(table["Match"])[0] == "Luciano", \
        table.to_dict("records")
    assert _premier_mot(table["Match"])[-1] == "Zzz", table.to_dict("records")


# ══════════════════════════════════════════════════════════════════════
# Page « Matchs a venir » : le tableau detaille
# ══════════════════════════════════════════════════════════════════════
#
# Les colonnes de prediction et de cote sont RONDES et identiques d'une ligne
# a l'autre : ce tableau-ci ne se juge que sur son ordre, et des montants
# inventes ligne a ligne feraient croire a une mesure. Le depot est public --
# aucune valeur de pari, de prediction reelle ou de compte n'y entre (meme
# regle que `fixtures_bets_synthetiques.py`).


def _page_a_venir(monkeypatch, matchs):
    import data

    enrichis = matchs.copy()
    enrichis["winner_pred"] = 1.5
    enrichis["loser_pred"] = 3.0
    enrichis["max_odds1"] = 2.0
    enrichis["max_odds2"] = 2.0
    enrichis["surface"] = "Hard"
    enrichis["round"] = "R32"
    enrichis["odds_lien"] = ""

    monkeypatch.setattr(data, "load_future_matchs", lambda: enrichis)
    at = AppTest.from_file("pages/future_matchs.py", default_timeout=60)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.run()
    assert not at.exception, at.exception
    return at


def _tableau_detaille(at):
    for d in at.dataframe:
        if {"Date", "Match", "Best_EV"} <= set(d.value.columns):
            return d.value
    return None


def test_a_venir_le_tableau_detaille_est_du_plus_recent_au_plus_ancien(
        monkeypatch):
    """Le tableau detaille est un tableau DATE : il se lit du plus recent au
    plus ancien, et c'est LUI qui pose cet ordre.

    Le tri n'a volontairement pas ete mis dans `_build_match_rows`, dont la
    sortie sert AUSSI aux cartes -- meme si celles-ci se retrient elles-memes
    (test suivant). Deux lectures de la meme donnee, deux ordres : les
    separer est ce qui permet a chacune de dire le sien.
    """
    at = _page_a_venir(monkeypatch, _melangees())
    table = _tableau_detaille(at)
    assert table is not None, "tableau detaille introuvable"

    assert _premier_mot(table["Match"]) == ATTENDU_DECROISSANT, \
        table.to_dict("records")
    assert list(table["Date"]) == sorted(table["Date"], reverse=True), \
        table.to_dict("records")
    # L'heure suit la date : « 00:30 » du 5 aout en tete, pas « 08:00 » du
    # 30 juillet -- un tri sur la seule heure les inverserait.
    assert list(table["Heure"])[0] == "00:30", table.to_dict("records")


def test_a_venir_les_CARTES_restent_chronologiques(monkeypatch):
    """La contrepartie du test precedent, et l'exception ASSUMEE.

    Les cartes ne sont pas un tableau : ce sont des tuiles groupees par
    TOURNOI, et chaque tournoi est place a l'heure de son premier match. Cet
    ordre croissant est ce qui fait qu'un tournoi ne s'annonce qu'une fois --
    exactement la raison pour laquelle `live_data.ordonner_par_tournoi` fait
    de meme sur la page « En direct ». Un operateur qui prepare sa journee
    lit d'ailleurs ces tuiles dans l'ordre ou les matchs vont se jouer.

    On le lit sur l'ordre des ENTETES de tournoi : Citi Open (28/07, son
    premier match) avant Samsun (30/07) avant Montreal (05/08).
    """
    at = _page_a_venir(monkeypatch, _melangees())
    entetes = [str(e.label) for e in at.expander]
    tournois = [t for t in entetes
                if any(n in t for n in ("Citi Open", "Samsun", "Montreal"))]
    assert len(tournois) == 3, entetes
    assert "Citi Open" in tournois[0], tournois
    assert "Samsun" in tournois[1], tournois
    assert "Montreal" in tournois[2], tournois


# ══════════════════════════════════════════════════════════════════════
# Tableau de bord : le tableau groupe PAR JOUR
# ══════════════════════════════════════════════════════════════════════
#
# `render_grouped_table` est un composant : on l'appelle depuis un banc
# minimal, comme le fait deja `test_navigateur.py`, plutot que de monter la
# page entiere. Les paris sont SYNTHETIQUES en valeur (depot public) ; ce qui
# compte ici est que les gains soient dans un ordre DIFFERENT des dates --
# sans quoi le repli du composant (« a defaut de cle, trier par gains »)
# rendrait le bon ordre par accident et le test ne prouverait rien.

_BANC_GROUPE = '''
import sys
sys.path.insert(0, {racine!r})
import pandas as pd
import streamlit as st
from pages.components.grouped_table import render_grouped_table

# Trois journees, et des gains qui DECROISSENT quand les dates CROISSENT :
# un tri par gains rendrait exactement l'ordre chronologique inverse de
# celui qu'on attend.
_paris = pd.DataFrame([
    {{"Match": "Aa Un - Bb Deux", "Date": pd.Timestamp("2026-07-28 10:00"),
      "Horaire": "10:00", "Compétition": "Atp", "Level": "A", "Surface": "Dur",
      "Round": "R32", "player_bet": "Aa Un", "Score": "6-1 6-1", "Cote": 1.50,
      "Prédiction": 1.40, "Mise": 10.0, "Gains net": 500.0,
      "Marge attendue": 1.0}},
    {{"Match": "Cc Trois - Dd Quatre", "Date": pd.Timestamp("2026-07-30 11:00"),
      "Horaire": "11:00", "Compétition": "Wta", "Level": "A", "Surface": "Dur",
      "Round": "R32", "player_bet": "Cc Trois", "Score": "6-2 6-2",
      "Cote": 2.00, "Prédiction": 1.80, "Mise": 10.0, "Gains net": 200.0,
      "Marge attendue": 1.0}},
    {{"Match": "Ee Cinq - Ff Six", "Date": pd.Timestamp("2026-08-05 12:00"),
      "Horaire": "12:00", "Compétition": "Atp", "Level": "A", "Surface": "Dur",
      "Round": "R32", "player_bet": "Ee Cinq", "Score": "6-3 6-3",
      "Cote": 3.00, "Prédiction": 2.50, "Mise": 10.0, "Gains net": 1.0,
      "Marge attendue": 1.0}},
])
render_grouped_table(_paris)
'''


def _banc_groupe(regroupement):
    from pathlib import Path

    racine = str(Path(__file__).resolve().parent.parent)
    at = AppTest.from_string(_BANC_GROUPE.format(racine=racine),
                             default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    at.radio[0].set_value(regroupement).run()
    assert not at.exception, at.exception
    return at


@pytest.mark.parametrize("regroupement,colonne,attendu", [
    ("Jour", "Jour", ["2026-08-05", "2026-07-30", "2026-07-28"]),
    ("Mois", "Mois", ["Août", "Juillet"]),
])
def test_le_tableau_groupe_par_temps_est_du_plus_recent_au_plus_ancien(
        regroupement, colonne, attendu):
    """Les trois regroupements DATES du tableau de bord.

    « Jour » est celui qui pouvait casser en silence : sa colonne est du
    TEXTE (`%Y-%m-%d`, pose avant le groupage) et, a defaut de cle, le
    composant retombe sur un tri par gains. Les gains de la fixture
    DECROISSENT quand les dates croissent -- ce repli rendrait donc l'ordre
    exactement inverse.
    """
    at = _banc_groupe(regroupement)
    tables = [d.value for d in at.dataframe if colonne in d.value.columns]
    assert tables, [list(d.value.columns) for d in at.dataframe]
    assert list(tables[0][colonne]) == attendu, tables[0].to_dict("records")


def test_le_tableau_groupe_par_SEMAINE_est_du_plus_recent_au_plus_ancien():
    """La semaine porte un LIBELLE (« 03 Aug → 09 Aug »), pas une date : rien
    dans la colonne affichee ne permet de la trier, c'est `Semaine_key` qui
    le fait. La semaine du 5 aout doit venir avant celle du 28 juillet.

    Les deux libelles contiennent tous deux « Aug » (la premiere semaine
    est a cheval sur les deux mois) : chercher le mois ne discriminerait
    RIEN -- constate en mutation, l'inversion survivait. On compare donc les
    deux libelles en entier, dans l'ordre.
    """
    at = _banc_groupe("Semaine")
    tables = [d.value for d in at.dataframe if "Semaine" in d.value.columns]
    assert tables, [list(d.value.columns) for d in at.dataframe]
    assert list(tables[0]["Semaine"]) == ["03 Aug → 09 Aug", "27 Jul → 02 Aug"], \
        tables[0].to_dict("records")


def test_le_tableau_groupe_par_JOUR_DE_LA_SEMAINE_reste_du_lundi_au_dimanche():
    """La contre-epreuve : « jour de la semaine » n'est PAS un axe temporel.

    C'est un cycle de sept categories, comme une surface ou un circuit. Le
    lire a l'envers -- dimanche, samedi, vendredi... -- ne rapprocherait rien
    du present, ca desordonnerait juste une echelle que tout le monde connait
    par coeur. Ce test existe pour que l'exception soit VOULUE et non oubliee
    le jour ou l'on generalisera le tri decroissant.
    """
    at = _banc_groupe("Jour de la semaine")
    tables = [d.value for d in at.dataframe
              if "Jour de la semaine" in d.value.columns]
    assert tables, [list(d.value.columns) for d in at.dataframe]
    # 2026-07-28 mardi, 2026-07-30 jeudi, 2026-08-05 mercredi.
    assert list(tables[0]["Jour de la semaine"]) == ["Mardi", "Mercredi",
                                                     "Jeudi"], \
        tables[0].to_dict("records")


def test_le_tableau_groupe_par_MATCH_est_du_plus_recent_au_plus_ancien():
    """Le regroupement « Match » est une autre branche du composant, avec sa
    propre mise en forme de date -- « HH:MM AAAA-MM-JJ », l'heure D'ABORD.
    Trier ce texte-la mettrait le match de 12:00 avant celui de 10:00 quelle
    que soit sa date : c'est bien la valeur, avant la mise en forme, qui doit
    porter le tri."""
    at = _banc_groupe("Match")
    tables = [d.value for d in at.dataframe if "Match" in d.value.columns]
    assert tables, [list(d.value.columns) for d in at.dataframe]
    assert _premier_mot(tables[0]["Match"]) == ["Ee", "Cc", "Aa"], \
        tables[0].to_dict("records")
