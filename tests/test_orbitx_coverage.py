"""Tests du filtre « A partir du » de la page Couverture Orbitx.

La page bornait la periode sur une ANNEE civile (`YEAR(tourney_date) = :year`)
et ne savait donc pas repondre a « et depuis juin ? ». Ces tests fixent le
nouveau contrat : une date de depart libre, transmise telle quelle a la
requete, et une legende qui annonce cette date plutot qu'une annee -- sans
quoi le tableau afficherait une periode et le texte en dessous une autre.

Gestion du cache -- `load_players_betfair_coverage` est decore `@st.cache_data`.
Sans `.clear()`, un second test recevrait le resultat mis en cache par le
premier, calcule sur un `read_sql_query` monkeypatche DIFFERENT, et son
assertion passerait pour de mauvaises raisons.
"""

import datetime as _dt

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

import data


# Un jeu de couverture minimal : un joueur jamais trouve, un partiellement
# trouve. Les colonnes sont celles que `load_players_betfair_coverage` rend.
COUVERTURE = pd.DataFrame(
    [
        {
            "compet": "ATP",
            "player": "Doe J.",
            "total_matches": 3,
            "found_matches": 0,
            "missing_matches": 3,
            "coverage_pct": 0.0,
        },
        {
            "compet": "WTA",
            "player": "Roe A.",
            "total_matches": 4,
            "found_matches": 1,
            "missing_matches": 3,
            "coverage_pct": 25.0,
        },
    ]
)


@pytest.fixture
def requete_capturee(monkeypatch):
    """Capture le (query, params) envoye a la base, sans toucher la base."""
    data.load_players_betfair_coverage.clear()
    capture = {}

    def faux_read_sql_query(schema, query, params=None):
        capture["query"] = query
        capture["params"] = params
        return pd.DataFrame(
            [
                {
                    "compet": "atp",
                    "player": "Doe J.",
                    "total_matches": 3,
                    "found_matches": 0,
                    "missing_matches": 3,
                }
            ]
        )

    monkeypatch.setattr(data, "read_sql_query", faux_read_sql_query)
    return capture


def _page(monkeypatch, capture=None, couverture=COUVERTURE):
    """Lance la page avec un chargeur bidon, et note la date qu'elle demande."""

    def faux_chargeur(start_date):
        if capture is not None:
            capture["start_date"] = start_date
        return couverture

    monkeypatch.setattr(data, "load_players_betfair_coverage", faux_chargeur)
    at = AppTest.from_file("pages/orbitx_coverage.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    return at.run()


def test_la_requete_borne_sur_la_date_de_depart_et_non_sur_lannee(requete_capturee):
    """Le coeur du changement : chacune des quatre branches du UNION borne sur
    `tourney_date >= :start_date`. Tant qu'une seule garde `YEAR(...)`, une
    date de depart en cours d'annee rend un total faux."""
    data.load_players_betfair_coverage(_dt.date(2026, 6, 1))

    query = requete_capturee["query"]
    assert "YEAR(" not in query.upper()
    assert query.count("tourney_date >= :start_date") == 4
    assert requete_capturee["params"] == {"start_date": "2026-06-01"}


def test_la_page_transmet_au_chargeur_la_date_choisie(monkeypatch):
    """Choisir le 1er juin doit faire relire la base depuis le 1er juin --
    et non redessiner le meme tableau annuel."""
    capture = {}
    at = _page(monkeypatch, capture=capture)

    at.date_input[0].set_value(_dt.date(2026, 6, 1)).run()

    assert capture["start_date"] == _dt.date(2026, 6, 1)


def test_par_defaut_la_page_regarde_depuis_le_premier_janvier(monkeypatch):
    """A l'ouverture, la page montre ce qu'elle montrait avant le filtre :
    l'annee civile en cours."""
    capture = {}
    _page(monkeypatch, capture=capture)

    assert capture["start_date"] == _dt.date(_dt.date.today().year, 1, 1)


def test_le_champ_date_vide_ne_fait_pas_lever_la_page(monkeypatch):
    """Un champ date peut etre VIDE : Streamlit rend alors None, et tout ce
    qui suit (`.strftime`, la requete) leve. La page retombe sur l'annee
    civile en cours plutot que d'afficher une trace Python."""
    capture = {}
    at = _page(monkeypatch, capture=capture)

    at.date_input[0].set_value(None).run()

    assert not at.exception
    assert capture["start_date"] == _dt.date(_dt.date.today().year, 1, 1)


def test_la_legende_annonce_la_date_de_depart_et_non_lannee(monkeypatch):
    """Le defaut a eviter : le tableau ne liste plus que depuis juin, et la
    legende continue de dire « en 2026 »."""
    at = _page(monkeypatch)

    at.date_input[0].set_value(_dt.date(2026, 6, 1)).run()

    legendes = " ".join(c.value for c in at.caption)
    assert "01/06/2026" in legendes
    assert "en 2026" not in legendes


def test_aucune_donnee_le_message_parle_de_la_date_pas_de_lannee(monkeypatch):
    """Meme exigence quand la base ne rend rien : « pour cette annee » ment
    des lors que la periode commence en cours d'annee."""
    at = _page(monkeypatch, couverture=pd.DataFrame())

    at.date_input[0].set_value(_dt.date(2026, 6, 1)).run()

    avertissements = " ".join(w.value for w in at.warning)
    assert "01/06/2026" in avertissements
    assert "cette année" not in avertissements
