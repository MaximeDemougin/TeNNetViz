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
def compte_capture(monkeypatch):
    """Capture le (query, params) du COMPTE hors perimetre, et rend 7."""
    data.load_orbit_search_out_of_scope_count.clear()
    capture = {}

    def faux_read_sql_query(schema, query, params=None):
        capture["query"] = query
        capture["params"] = params
        return capture.get("reponse", pd.DataFrame([{"hors": 7}]))

    monkeypatch.setattr(data, "read_sql_query", faux_read_sql_query)
    return capture


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


def _page(monkeypatch, capture=None, couverture=COUVERTURE, hors_perimetre=0):
    """Lance la page avec des chargeurs bidons, et note la date qu'elle demande."""

    def faux_chargeur(start_date):
        if capture is not None:
            capture["start_date"] = start_date
        return couverture

    def faux_compte_hors_perimetre(start_date):
        if capture is not None:
            capture["hors_perimetre_demande_pour"] = start_date
        return hors_perimetre

    monkeypatch.setattr(data, "load_players_betfair_coverage", faux_chargeur)
    monkeypatch.setattr(
        data, "load_orbit_search_out_of_scope_count", faux_compte_hors_perimetre
    )
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
    assert requete_capturee["params"]["start_date"] == "2026-06-01"


def test_seuls_les_matchs_cherches_par_orbit_search_sont_comptes(requete_capturee):
    """`orbit_search` ne cherche que des matchs qui ont des cotes ET une
    prediction. Compter les autres comme « jamais trouves » accuse OrbitX de
    n'avoir pas trouve ce qu'on ne lui a jamais demande : moitie de la liste
    depuis janvier, deux tiers depuis juin."""
    data.load_players_betfair_coverage(_dt.date(2026, 6, 1))

    query = requete_capturee["query"]
    assert query.count("EXISTS (SELECT 1 FROM odds o WHERE o.id = m.ID_MATCH)") == 4
    assert (
        query.count(
            "EXISTS (SELECT 1 FROM predictions p WHERE p.ID_MATCH = m.ID_MATCH)"
        )
        == 4
    )
    assert query.count("m.tourney_name NOT LIKE :hors_perimetre") == 4


def test_les_matchs_programmes_au_dela_de_trois_heures_sont_exclus(requete_capturee):
    """La fenetre du job s'arrete a NOW()+3h. Un match programme plus tard n'a
    pas encore ete cherche -- le compter comme introuvable est un reproche
    adresse a un travail pas encore fait."""
    data.load_players_betfair_coverage(_dt.date(2026, 6, 1))

    query = requete_capturee["query"]
    assert query.count("m.tourney_date <= DATE_ADD(NOW(), INTERVAL 3 HOUR)") == 4


def test_le_perimetre_est_une_semi_jointure_qui_ne_multiplie_pas_les_lignes(
    requete_capturee,
):
    """`predictions` porte un ID_MATCH en DOUBLE (22438 lignes, 22437
    distincts). Joindre plutot que tester l'existence compterait ce match deux
    fois dans `total_matches`, et fausserait sa couverture."""
    data.load_players_betfair_coverage(_dt.date(2026, 6, 1))

    query = requete_capturee["query"]
    assert "JOIN odds" not in query
    assert "JOIN predictions" not in query


def test_le_motif_davis_cup_part_en_parametre_lie_et_non_en_litteral(requete_capturee):
    """Un `%` litteral dans le texte SQL est a la merci du paramstyle du
    pilote -- c'est pourquoi l'amont doit l'ecrire `I%%`. Lie, il n'y a plus
    rien a echapper."""
    data.load_players_betfair_coverage(_dt.date(2026, 6, 1))

    assert "Davis Cup" not in requete_capturee["query"]
    assert requete_capturee["params"]["hors_perimetre"] == "Davis Cup - World Group I%"


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


def test_le_compte_hors_perimetre_recense_les_quatre_raisons(compte_capture):
    """Passer de 159 « jamais trouves » a 80 sans le dire serait un escamotage.
    Les quatre raisons de sortir du perimetre sont celles du job, pas d'autres."""
    data.load_orbit_search_out_of_scope_count(_dt.date(2026, 6, 1))

    query = compte_capture["query"]
    assert "NOT EXISTS (SELECT 1 FROM odds o WHERE o.id = m.ID_MATCH)" in query
    assert (
        "NOT EXISTS (SELECT 1 FROM predictions p WHERE p.ID_MATCH = m.ID_MATCH)"
        in query
    )
    assert "m.tourney_name LIKE :hors_perimetre" in query
    assert "m.tourney_date > DATE_ADD(NOW(), INTERVAL 3 HOUR)" in query


def test_le_compte_hors_perimetre_rend_zero_quand_la_base_ne_dit_rien(compte_capture):
    """`SUM(...)` sur zero ligne rend NULL, pas 0. Sans garde, la legende
    afficherait « nan match(s) hors perimetre »."""
    compte_capture["reponse"] = pd.DataFrame([{"hors": None}])

    assert data.load_orbit_search_out_of_scope_count(_dt.date(2026, 6, 1)) == 0


def test_la_page_annonce_combien_de_matchs_sont_hors_perimetre(monkeypatch):
    """La page restreint sa liste : elle doit dire de combien, sinon elle
    affirme une couverture qu'elle a silencieusement retaillee."""
    at = _page(monkeypatch, hors_perimetre=482)

    legendes = " ".join(c.value for c in at.caption)
    assert "482" in legendes
    assert "orbit_search" in legendes


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
