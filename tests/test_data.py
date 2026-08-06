"""Tests du filtre `stake > 0` dans `data._prepare_bets_data_cached`.

Un ordre jamais apparie (mise nulle ou absente) ne doit ni faire lever la
page (groupe entierement nul -> ancienne `ZeroDivisionError` de la moyenne
ponderee), ni fausser la moyenne ponderee des cotes (groupe mixte).

Gestion du cache -- `_prepare_bets_data_cached` est decore `@st.cache_data`
et clef sur `(user_id, finished)`. Sans precaution, un second test appelant
`data.prepare_bets_data(999, True)` recevrait le resultat mis en cache par
le premier, calcule sur un `load_bets` monkeypatche DIFFERENT, et fausserait
silencieusement l'assertion. La fixture `paris` ci-dessous appelle
`data._prepare_bets_data_cached.clear()` avant de monkeypatcher `load_bets`,
a chaque test qui l'utilise ; le test qui n'utilise pas la fixture (compte
sans aucun pari paye) le fait explicitement lui aussi.
"""

import logging
import re

import numpy as np
import pandas as pd
import pytest

import data
from fixtures_bets_synthetiques import PARIS_SYNTHETIQUES  # nom NU, voir conftest.py

USER_ID = 999


@pytest.fixture
def paris(monkeypatch):
    """Branche `data.load_bets` sur les paris synthetiques, sans toucher la
    base, et vide le cache de `_prepare_bets_data_cached` pour que ce test
    ne reçoive pas le resultat d'un test precedent."""
    data._prepare_bets_data_cached.clear()

    def faux_load_bets(user_id):
        return pd.DataFrame(PARIS_SYNTHETIQUES).reset_index(drop=True)

    monkeypatch.setattr(data, "load_bets", faux_load_bets)
    return faux_load_bets


def test_le_groupe_entierement_nul_ne_fait_plus_lever(paris):
    """Le defaut exact : un groupe (match, joueur) dont l'unique pari a une
    mise nulle faisait lever une ZeroDivisionError dans la moyenne ponderee,
    et avec lui la page par defaut de l'application."""
    resultat = data.prepare_bets_data(USER_ID)
    assert len(resultat) > 0
    assert "TEST0001" not in set(resultat["ID_MATCH"])


def test_le_groupe_mixte_garde_son_pari_a_mise_positive(paris):
    """Le detail qui distingue « ecarter les lignes a mise nulle » de
    « ecarter le groupe entier » : sans cette assertion, jeter tout le
    groupe TEST0002 passerait aussi le test precedent."""
    resultat = data.prepare_bets_data(USER_ID)
    mixte = resultat[resultat["ID_MATCH"] == "TEST0002"]
    assert len(mixte) == 1
    assert mixte["Mise"].iloc[0] > 0


def test_la_moyenne_des_cotes_du_groupe_normal_reste_PONDEREE(paris):
    """Le groupe normal (TEST0003) a des mises et des cotes tres inegales :
    si la moyenne ponderee etait remplacee par une moyenne simple, l'ecart
    se verrait."""
    resultat = data.prepare_bets_data(USER_ID)
    ligne = resultat[resultat["ID_MATCH"] == "TEST0003"]
    assert len(ligne) == 1

    brut = pd.DataFrame(PARIS_SYNTHETIQUES)
    sub = brut[brut["ID_MATCH"] == "TEST0003"].copy()
    is_back = sub["side_back_lay"] == "back"
    sub["real_odds"] = np.where(
        is_back,
        (sub["odds"] - 1) * 0.97 + 1,
        (1 / (sub["odds"] - 1)) * 0.97 + 1,
    )
    ponderee = round(np.average(sub["real_odds"], weights=sub["stake"]), 3)
    simple = round(sub["real_odds"].mean(), 3)
    assert ponderee != simple, "la fixture ne discrimine plus les deux moyennes"
    assert ligne["Cote"].iloc[0] == pytest.approx(ponderee, abs=0.001)


def test_le_nombre_de_paris_ecartes_est_JOURNALISE(paris, caplog):
    """Un ecart qui ne laisse pas de trace n'atteste rien. Le journal doit
    porter le NOMBRE exact, pas seulement le fait qu'il y en a eu."""
    brut = pd.DataFrame(PARIS_SYNTHETIQUES)
    # Meme predicat que le filtre : `stake > 0` est faux pour une mise nulle
    # ET pour une mise absente (NaN). `stake <= 0` manquerait le NaN.
    attendu = int((~(brut["stake"] > 0)).sum())
    assert attendu == 3, "la fixture ne porte plus les trois paris ecartes attendus"

    with caplog.at_level(logging.INFO, logger="data"):
        data.prepare_bets_data(USER_ID)
    messages = [r.message for r in caplog.records if r.name == "data"]
    # Frontieres `\b` : le NOMBRE, pas un chiffre qu'il contient -- un
    # message portant "31" ne doit pas faire passer un test qui attend "3".
    motif = re.compile(rf"\b{attendu}\b")
    assert any(motif.search(m) for m in messages), messages


def test_la_mise_absente_NaN_est_ecartee_elle_aussi(paris):
    """`NaN > 0` est faux : le pari TEST0004 (mise NaN, pas nulle) doit
    disparaitre du tableau exactement comme une mise a 0."""
    resultat = data.prepare_bets_data(USER_ID)
    assert "TEST0004" not in set(resultat["ID_MATCH"])


def test_un_compte_dont_TOUS_les_ordres_sont_a_mise_nulle_rend_un_tableau_vide(
    monkeypatch,
):
    """Le cas que le filtre a lui-meme rendu atteignable, et qui exige qu'il
    soit place AVANT la garde de vacuite de `_prepare_bets_data_cached`.

    Avant le filtre, un `load_bets` non vide donnait toujours un
    `prepared_bets` non vide. Depuis, un compte dont TOUS les ordres sont a
    mise nulle passe la garde (les lignes existent) puis devient vide APRES
    le filtre -- et plus bas, `prepared_bets["Score"].apply(_score_is_void)`
    sur une Series vide rend un dtype `float64` faute d'element ou deviner
    `bool`. `prepared_bets[~prepared_bets["voided"]]` degenere alors en un
    DataFrame (0, 0) SANS COLONNES -- pandas lit le masque non booleen comme
    une selection de colonnes -- et le `groupby` suivant leve
    `KeyError: 'ID_MATCH'`.

    Ce n'est pas un cas de bord theorique : c'est exactement le compte d'un
    parieur dont aucun ordre n'a jamais trouve de contrepartie. Il doit voir
    un tableau vide, comme quelqu'un qui n'a jamais parie -- ce qu'il est.

    Le test DISCRIMINE : remettre le filtre apres la garde de vacuite le
    fait rougir en `KeyError`.
    """
    data._prepare_bets_data_cached.clear()

    jamais_apparies = [
        dict(pari, stake=0.0)
        for pari in PARIS_SYNTHETIQUES
        if pari["ID_MATCH"] == "TEST0003"
    ]
    assert jamais_apparies, "la fixture ne porte plus le groupe normal attendu"

    monkeypatch.setattr(
        data, "load_bets", lambda user_id: pd.DataFrame(jamais_apparies)
    )

    resultat = data.prepare_bets_data(USER_ID)

    assert resultat.empty
    # Le repli doit rendre le SCHEMA attendu, pas un DataFrame nu : la page
    # lit ces colonnes sans les tester.
    for colonne in ("ID_MATCH", "Match", "Mise", "Cote", "Gains net"):
        assert colonne in resultat.columns, resultat.columns.tolist()
