"""Tests bout en bout de pages/match.py via AppTest -- point du registre :
`str(m.get(champ) or "-")` affiche litteralement "nan" pour un NaN flottant
(NaN est vrai au sens booleen). Verifie que ce n'est plus le cas."""

import sys
import time
import types

import pandas as pd
from streamlit.testing.v1 import AppTest

from fixtures_reelles import (
    LIGNE_REELLE_MATCH_AUTRE_LIGUE,
    LIGNES_REELLES_MATCHS,
    LIGNES_REELLES_QA,
)


#: Les CINQ tables que la page lit, chacune sous son nom. Le bouchon les
#: distingue par le nom present dans la requete, comme le ferait une vraie
#: base -- servir le meme tableau a toutes ferait passer une requete pour
#: une autre sans que rien ne le signale (une liste de matchs relue comme un
#: bilan de collecte, par exemple).
TABLES = ("live_now", "live_series", "live_qa_daily", "live_matches",
          "live_points")


def _mock_tables(monkeypatch, **tables):
    """Un lecteur bouchonne qui rend, pour chaque table, le tableau donne.

    Une table non fournie rend un tableau VIDE : c'est le cas « la page lit
    une table dont ce test ne parle pas », et il ne doit pas se traduire par
    des donnees d'une autre table.
    """
    inconnues = set(tables) - set(TABLES)
    assert not inconnues, f"table inconnue dans le bouchon : {inconnues}"

    def lire(schema, query):
        for nom in TABLES:
            if nom in query:
                df = tables.get(nom)
                return pd.DataFrame() if df is None else df
        raise AssertionError(f"requete sur une table non bouchonnee : {query}")

    faux = types.ModuleType("db_utils.db_utils")
    faux.read_sql_query = lire
    monkeypatch.setitem(sys.modules, "db_utils", types.ModuleType("db_utils"))
    monkeypatch.setitem(sys.modules, "db_utils.db_utils", faux)


def _mock_lecteur(monkeypatch, matchs_df, serie_df):
    """Le direct seul : live_now et live_series, les autres tables vides."""
    _mock_tables(monkeypatch, live_now=matchs_df, live_series=serie_df)


def _page(monkeypatch, **tables):
    """La page, bouchonnee et connectee, PAS encore executee."""
    _mock_tables(monkeypatch, **tables)
    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    return at



def point_par_point(at):
    """Le tableau point par point, retrouve par ses COLONNES.

    Le detail en affiche plusieurs (cotes, statistiques, recit) : le reperer
    par sa position casserait au prochain bandeau ajoute.
    """
    for d in at.dataframe:
        if {"score", "points"} <= set(d.value.columns):
            return d.value
    return None


def test_un_score_nan_affiche_un_tiret_pas_le_mot_nan(monkeypatch):
    matchs_df = pd.DataFrame([{
        "event_id": "evt-nan", "status": "InPlay",
        "participant1": "A", "participant2": "B", "league": "ATP Test",
        "score": float("nan"), "points": float("nan"), "server": None,
        "updated_ts": time.time(),
    }])
    _mock_lecteur(monkeypatch, matchs_df, pd.DataFrame())

    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.query_params["event_id"] = "evt-nan"
    at.run()

    assert not at.exception
    valeurs = [m.value for m in at.metric]
    assert "nan" not in [v.lower() for v in valeurs], valeurs

    par_label = {m.label: m.value for m in at.metric}
    assert par_label["Score"] == "—"
    assert par_label["Points"] == "—"
    # Pas de metrique "Serveur" (mineur #1, tour 3) : `server` est NULL a
    # 100 % depuis la decision C6 cote publieur -- une metrique qui rend
    # "-" a chaque rendu ne dit rien et a ete retiree.
    assert "Serveur" not in par_label


def test_erreur_inattendue_du_graphique_naffiche_pas_de_trace_python(monkeypatch):
    """Toute exception du graphique doit degrader en message, jamais
    remonter une trace Python jusqu'a l'ecran.

    On patche `detail_match.figure_cotes` la ou le nom VIT : `graphique_cotes`
    l'appelle par ce nom-la, et patcher ailleurs ne toucherait pas l'appel --
    meme piege que le chdir differe.
    """
    import detail_match

    def casse(serie):
        raise RuntimeError("panne simulee")

    monkeypatch.setattr(detail_match, "figure_cotes", casse)
    at = _match_avec_cotes(monkeypatch)
    at.run()
    assert not at.exception, "une trace Python est remontee a l'ecran"
    assert any("graphique" in str(e.value).lower() for e in at.error), \
        [str(e.value) for e in at.error]


def test_le_tableau_point_par_point_affiche_une_date_pas_des_secondes_epoch(monkeypatch):
    """Preuve directe de I4 : avant ce tour, la premiere colonne du tableau
    point par point affichait litteralement 1785794036.9001677. Verifie que
    la colonne `ts` rendue est un datetime, pas un flottant epoch brut.

    (Cette docstring affirmait que le graphique n'etait pas inspectable via
    AppTest, aucune classe Element n'exposant le spec Vega-Lite. C'etait vrai
    d'`at.altair_chart`, faux en general : on peut CAPTURER le graphique en
    remplacant `st.altair_chart` avant l'execution, ce que fait
    `test_la_courbe_de_cotes_est_en_echelle_logarithmique` plus bas. Corrige
    plutot que laisse : une affirmation fausse dans un commentaire de test
    decourage precisement le test qui manquait.)"""
    matchs_df = pd.DataFrame([{
        "event_id": "evt-ts", "status": "InPlay",
        "participant1": "A", "participant2": "B", "league": "ATP Test",
        "score": "6-4", "points": "30-15", "server": None,
        "updated_ts": time.time(),
    }])
    serie_df = pd.DataFrame([
        {"ts": 1785794036.9001677, "score": "6-4", "points": "30-15"},
    ])
    _mock_lecteur(monkeypatch, matchs_df, serie_df)

    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.query_params["event_id"] = "evt-ts"
    at.run()

    assert not at.exception
    tableau_pp = point_par_point(at)
    assert tableau_pp is not None, "tableau point par point introuvable"
    assert "server" not in tableau_pp.columns
    assert pd.api.types.is_datetime64_any_dtype(tableau_pp["ts"])
    rendu = str(tableau_pp["ts"].iloc[0])
    assert "1785794036" not in rendu, f"epoch brut encore visible : {rendu!r}"


# ══════════════════════════════════════════════════════════════════════
# NIVEAU 1 : le bilan de collecte, puis la liste filtrable des matchs
# ══════════════════════════════════════════════════════════════════════
#
# « Match » est inscrite au menu lateral (app.py), donc on y arrive sans
# passer par une liste et sans `event_id` dans l'URL. Elle ouvrait alors un
# selecteur des matchs du DIRECT ; elle porte desormais le passe -- le bilan
# de collecte et les matchs deja joues -- et le detail n'en est que le
# second niveau (design du 2026-08-07, §5).

BILAN_REEL = pd.DataFrame(LIGNES_REELLES_QA)
PASSES_REELS = pd.DataFrame(LIGNES_REELLES_MATCHS)


def _niveau_1(monkeypatch, matchs=None, bilan=None):
    """La page sans `event_id` : bilan et liste, sur donnees REELLES."""
    at = _page(
        monkeypatch,
        live_qa_daily=BILAN_REEL if bilan is None else bilan,
        live_matches=PASSES_REELS if matchs is None else matchs,
    )
    at.run()
    assert not at.exception, at.exception
    return at


def liste_des_matchs(at):
    """Le tableau de la LISTE, reconnu par une colonne qui n'est qu'a lui.

    Le bilan de collecte porte lui aussi une colonne « Jour » : reperer la
    liste par sa position casserait au premier tableau ajoute au-dessus.
    """
    for d in at.dataframe:
        if "Ligue" in d.value.columns:
            return d.value
    return None


def _captions(at):
    return [str(c.value) for c in at.caption]


def test_le_bilan_de_collecte_est_CABLE_dans_la_page(monkeypatch):
    """`bilan_collecte.afficher` existait et n'etait appele par AUCUNE page :
    les trois seuils continuaient donc de sonner en silence. Ce test protege
    le CABLAGE, pas le rendu (teste ailleurs)."""
    at = _niveau_1(monkeypatch)
    assert any("Santé de la collecte" in str(s.value) for s in at.subheader), \
        [str(s.value) for s in at.subheader]
    par_label = {m.label: m.value for m in at.metric}
    appariement = [v for k, v in par_label.items() if "Appariement" in k]
    assert appariement == ["65,3 %"], par_label


def test_les_circuits_proposes_sont_ceux_des_DONNEES(monkeypatch):
    """Une liste de circuits ecrite dans le code serait fausse le jour ou un
    troisieme apparait -- et personne ne le verrait.

    La preuve tient dans le second cas : un jeu ou seul le WTA a joue ne doit
    proposer QUE `wta`. Une liste en dur y proposerait `atp` sans qu'aucune
    ligne ne le porte.
    """
    at = _niveau_1(monkeypatch)
    assert list(at.multiselect("filtre_circuit").options) == ["atp", "wta"]

    wta_seul = PASSES_REELS[PASSES_REELS["tour_type"] == "wta"]
    at2 = _niveau_1(monkeypatch, matchs=wta_seul)
    assert list(at2.multiselect("filtre_circuit").options) == ["wta"]


def test_ajouter_une_ligue_aux_donnees_la_fait_apparaitre_dans_les_choix(monkeypatch):
    at = _niveau_1(monkeypatch)
    avant = list(at.multiselect("filtre_ligue").options)
    assert "W15 Savitaipale" not in avant, avant

    plus = pd.DataFrame(LIGNES_REELLES_MATCHS + [LIGNE_REELLE_MATCH_AUTRE_LIGUE])
    at2 = _niveau_1(monkeypatch, matchs=plus)
    apres = list(at2.multiselect("filtre_ligue").options)
    assert set(apres) - set(avant) == {"W15 Savitaipale"}, apres
    # La ligne ajoutee porte AUSSI un jour qu'aucune autre n'a : le filtre de
    # jour se tire des memes donnees, pas d'un calendrier.
    jours = list(at2.multiselect("filtre_jour").options)
    assert "2026-07-29" in jours, jours
    # Le plus recent d'abord : c'est celui qu'on vient regarder.
    assert jours[0] == "2026-08-06", jours


def test_filtrer_sur_un_circuit_ne_laisse_que_lui(monkeypatch):
    at = _niveau_1(monkeypatch)
    assert len(liste_des_matchs(at)) == 6

    at.multiselect("filtre_circuit").select("wta")
    at.run()
    assert not at.exception, at.exception

    table = liste_des_matchs(at)
    assert set(table["Circuit"]) == {"wta"}, table.to_dict("records")
    # Les deux lignes de Sabalenka (un match a cheval sur deux journees), et
    # AUCUNE des quatre lignes ATP.
    assert len(table) == 2, table.to_dict("records")
    assert all("Sabalenka" in m for m in table["Match"]), table["Match"].tolist()
    # Le taux affiche suit ce qui est AFFICHE : sur ces deux lignes il vaut
    # 100 %, pas les 66,7 % de la liste entiere.
    taux = [t for t in _captions(at) if "matchs identifiés" in t]
    assert taux and "2 sur 2" in taux[0], _captions(at)


def test_filtrer_sur_les_non_apparies_ne_laisse_que_ceux_la(monkeypatch):
    at = _niveau_1(monkeypatch)
    at.radio("filtre_appariement").set_value("Non appariés")
    at.run()
    assert not at.exception, at.exception

    table = liste_des_matchs(at)
    assert set(table["Apparié"]) == {"non"}, table.to_dict("records")
    assert len(table) == 2, table.to_dict("records")
    # 3799286 (un des deux identifiants du match Duckworth) et 3807294, les
    # seules lignes a `matched = 0` du prelevement.
    assert set(table["Identifiants"]) == {"3799286", "3807294"}, \
        table["Identifiants"].tolist()


def test_le_taux_de_la_liste_n_est_PAS_celui_du_bilan(monkeypatch):
    """Deux taux d'appariement circulent, avec DEUX denominateurs (§4 du
    design), et les melanger produirait un chiffre qui ne veut rien dire.

    - le bilan : 65,3 % des MARCHES vus en jeu, hors ambigus ;
    - la liste : 4 sur 6 MATCHS identifies (416/1 153 sur la table entiere).

    Chacun doit s'afficher avec son denominateur, et aucun ne doit prendre
    la place de l'autre.
    """
    at = _niveau_1(monkeypatch)
    taux = [t for t in _captions(at) if "matchs identifiés" in t]
    assert taux, _captions(at)
    texte = taux[0]
    # Le compte COLLE a son denominateur. « 4 sur 6 » suivi de n'importe
    # quel autre denominateur serait un chiffre faux : c'est exactement la
    # confusion que ce test existe pour interdire, et la separer du reste de
    # la phrase la laisserait passer (mutation constatee survivante).
    assert "4 sur 6 matchs identifiés" in texte, texte
    assert "66,7 %" in texte, texte
    # Le taux du BILAN n'a rien a faire ici : ni sa valeur, ni son
    # denominateur seul.
    assert "65,3" not in texte, texte
    # Et le texte nomme la difference, sans quoi le lecteur croirait a une
    # incoherence entre deux chiffres de la meme page.
    assert "marchés vus en jeu" in texte, texte

    # Le bilan, lui, garde SA valeur et SON denominateur.
    par_label = {m.label: m.value for m in at.metric}
    assert [v for k, v in par_label.items() if "Appariement" in k] == ["65,3 %"]


def test_la_liste_ne_dit_jamais_nan(monkeypatch):
    """Meme piege que partout ici : NaN est vrai au sens booleen, donc
    `valeur or defaut` l'ecrirait litteralement « nan » -- dans le tableau
    comme dans la liste deroulante ou l'utilisateur choisit."""
    troue = dict(LIGNES_REELLES_MATCHS[0])
    troue.update({"participant2": float("nan"), "league": float("nan"),
                  "start_ts": float("nan")})
    at = _niveau_1(monkeypatch, matchs=pd.DataFrame([troue]))

    table = liste_des_matchs(at)
    assert "nan" not in table.to_string().lower(), table.to_dict("records")
    etiquettes = list(at.selectbox("choix_match_passe").options)
    assert not any("nan" in e.lower() for e in etiquettes), etiquettes


def test_sans_aucun_match_collecte_la_page_le_dit_sans_trace(monkeypatch):
    at = _page(monkeypatch)
    at.run()
    assert not at.exception
    textes = [str(i.value) for i in at.info]
    assert any("Aucun match collecté" in t for t in textes), textes


def test_sans_parametre_base_injoignable_affiche_un_message_pas_la_trace(monkeypatch):
    """La contrainte du projet -- l'interface ne montre JAMAIS une trace
    Python -- vaut aussi sur ce chemin neuf, qui lit la base avant d'avoir
    le moindre parametre."""
    def lire_qui_tombe(schema, query):
        raise RuntimeError("base injoignable")

    faux = types.ModuleType("db_utils.db_utils")
    faux.read_sql_query = lire_qui_tombe
    monkeypatch.setitem(sys.modules, "db_utils", types.ModuleType("db_utils"))
    monkeypatch.setitem(sys.modules, "db_utils.db_utils", faux)

    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.run()

    assert not at.exception, at.exception
    assert any("injoignable" in str(e.value) for e in at.error), \
        [str(e.value) for e in at.error]


# --- Le tableau porte les cotes, et la courbe est en echelle log ---
#
# Demandes a l'usage : « dans le point par point je veux voir les cotes
# back/lay de l'exchange » et « la courbe n'est pas lisible, avec les grosses
# cotes de fin on ne voit rien ». Mesure : 3 a 4 % des releves depassent la
# cote 20 (max 990 en lay) et ecrasent l'echelle des 97 % autres.


def _match_avec_cotes(monkeypatch, series_df=None):
    matchs_df = pd.DataFrame([{
        "event_id": "evt-c", "status": "InPlay", "participant1": "Aa",
        "participant2": "Bb", "league": "ATP Test", "score": "1-0",
        "points": "15-0", "updated_ts": time.time(),
    }])
    if series_df is None:
        series_df = pd.DataFrame([
            {"ts": 100.0, "score": "1-0", "points": "0-0", "evenement": None,
             "back_odds_a": 1.5, "lay_odds_a": 1.55,
             "back_odds_b": 2.6, "lay_odds_b": 2.7,
             "book_odds_a": 1.52, "book_odds_b": 2.58},
            # MEME etat de jeu, prix qui a bouge : c'est la suite que le
            # repliement doit reduire, et c'est le seul cas ou « premiere »
            # et « derniere » ligne different. Sans elle, un test qui pretend
            # verifier que la cote est celle de l'INSTANT DU POINT ne verifie
            # rien -- mutation P3 constatee survivante le 2026-08-04.
            {"ts": 150.0, "score": "1-0", "points": "0-0", "evenement": None,
             "back_odds_a": 1.9, "lay_odds_a": 1.95,
             "back_odds_b": 2.1, "lay_odds_b": 2.2,
             "book_odds_a": 1.88, "book_odds_b": 2.12},
            # La cote explose en fin de match : c'est ce releve qui rendait la
            # courbe illisible en echelle lineaire.
            {"ts": 200.0, "score": "1-0", "points": "30-0", "evenement": None,
             "back_odds_a": 120.0, "lay_odds_a": 990.0,
             "back_odds_b": 1.01, "lay_odds_b": 1.02,
             "book_odds_a": 59.5, "book_odds_b": 1.01},
        ])
    _mock_lecteur(monkeypatch, matchs_df, series_df)
    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.query_params["event_id"] = "evt-c"
    return at


def test_le_point_par_point_porte_les_cotes_back_et_lay_des_deux_joueurs(monkeypatch):
    at = _match_avec_cotes(monkeypatch)
    at.run()
    assert not at.exception
    colonnes = list(point_par_point(at).columns)
    for attendue in ("back_odds_a", "lay_odds_a", "back_odds_b", "lay_odds_b"):
        assert attendue in colonnes, colonnes
    # Et ce sont les cotes de l'instant du POINT, pas les dernieres connues :
    # la fixture porte DEUX releves du meme etat (1,5 puis 1,9), et c'est le
    # premier qui doit survivre au repliement. Un test ecrit sans cette suite
    # laisserait passer un repliement qui garde la derniere ligne.
    tableau = point_par_point(at)
    assert tableau is not None
    assert len(tableau) == 2, tableau.to_dict("records")
    ligne = tableau.iloc[-1]      # affichage inverse : la plus ancienne
    assert float(ligne["back_odds_a"]) == 1.5, ligne.to_dict()
    assert float(ligne["lay_odds_a"]) == 1.55, ligne.to_dict()


def test_la_courbe_de_cotes_est_en_echelle_logarithmique(monkeypatch):
    """Capture le graphique REELLEMENT pousse : sans cela le test ne
    verifierait que le source, pas ce que voit l'utilisateur.

    3 a 4 % des releves depassent la cote 20 (maximum observe 990 en lay) et
    ces extremes sont ceux de la FIN de match. En lineaire ils ecrasent
    l'echelle des 97 % autres.
    """
    import streamlit as st

    captures = []
    vrai = st.plotly_chart
    monkeypatch.setattr(
        st, "plotly_chart",
        lambda fig, **kw: (captures.append(fig), vrai(fig, **kw))[1],
    )
    at = _match_avec_cotes(monkeypatch)
    at.run()

    assert not at.exception
    assert captures, "aucun graphique pousse"
    fig = captures[0]
    assert fig.layout.yaxis.type == "log", fig.layout.yaxis.type
    # Et le lay reste masque dans ce qui est POUSSE, pas seulement dans ce
    # que la fabrique rend.
    lay = [t for t in fig.data if t.name and "lay" in t.name]
    assert lay and all(t.visible == "legendonly" for t in lay), \
        [(t.name, t.visible) for t in fig.data]

def _age_affiche(at, flux):
    from live_data import SEUILS_PAR_FLUX
    libelle = SEUILS_PAR_FLUX[flux][2].replace(" -- ", " · ")
    for metrique in at.metric:
        if metrique.label == libelle:
            return metrique.value
    return None


def _detail_de(monkeypatch, ligne):
    matchs_df = pd.DataFrame([ligne])
    _mock_lecteur(monkeypatch, matchs_df, pd.DataFrame())
    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.query_params["event_id"] = str(ligne["event_id"])
    at.run()
    assert not at.exception, at.exception
    return at


def test_le_detail_porte_l_age_EFFECTIF_a_cote_de_la_pastille(monkeypatch):
    """L'age affiche doit etre celui de la LECTURE -- age stocke plus temps
    ecoule depuis le cycle -- le meme que celui qui decide de la couleur.
    Sinon les deux se contrediraient sous les yeux de l'operateur."""
    maintenant = time.time()
    ligne = {
        "event_id": "evt-age", "event_ids": "evt-age", "status": "InPlay",
        "participant1": "A", "participant2": "B", "league": "Test Open",
        "score": "1-0", "points": "15-0", "server": "0",
        # Age STOCKE de 5 s, cycle vieux de 40 s -> age a la LECTURE ~45 s.
        "updated_ts": maintenant - 40.0,
        "age_score_s": 5.0, "age_exchange_s": 5.0, "age_books_s": 5.0,
        "age_books_flux_s": 5.0, "age_stats_s": 5.0,
    }
    at = _detail_de(monkeypatch, ligne)
    for flux in ("f_score", "f_exchange", "f_books", "f_books_flux", "f_stats"):
        valeur = _age_affiche(at, flux) or ""
        assert valeur[:1] in "🟢🔴⚪", (flux, valeur)
        assert any(x in valeur for x in ("44s", "45s", "46s")), \
            f"{flux} : age de lecture attendu ~45s, recu {valeur!r}"


def test_un_age_inconnu_affiche_un_point_d_interrogation_pas_zero(monkeypatch):
    """Confondre « je ne sais pas » avec « a l'instant » ferait passer un flux
    muet pour le plus vivant des cinq."""
    maintenant = time.time()
    ligne = {
        "event_id": "evt-inc", "event_ids": "evt-inc", "status": "InPlay",
        "participant1": "A", "participant2": "B", "league": "Test Open",
        "score": "1-0", "points": "15-0", "server": "0",
        "updated_ts": maintenant, "age_score_s": 2.0, "age_exchange_s": 2.0,
        "age_books_s": None, "age_books_flux_s": 2.0, "age_stats_s": None,
    }
    at = _detail_de(monkeypatch, ligne)
    for flux in ("f_books", "f_stats"):
        valeur = _age_affiche(at, flux) or ""
        assert valeur == "⚪ ?", (flux, valeur)
        assert "0s" not in valeur


# ── le graphique de cotes : Plotly, et le lay masque par defaut ────────


def _figure(serie=None):
    """La figure Plotly du graphique de cotes, construite hors Streamlit."""
    import pandas as pd
    from detail_match import figure_cotes
    if serie is None:
        base = time.time()
        serie = pd.DataFrame([
            {"ts": base + 60 * i, "back_odds_a": 1.5 + i * 0.1,
             "lay_odds_a": 1.56 + i * 0.1, "back_odds_b": 2.6 - i * 0.1,
             "lay_odds_b": 2.7 - i * 0.1, "book_odds_a": 1.55,
             "book_odds_b": 2.5,
             # Sans score ni points la fixture ne peut rien dire du survol.
             "score": f"6-4,{i}-2", "points": "30-15",
             "evenement": "fin_de_jeu" if i == 2 else None}
            for i in range(6)
        ])
    return figure_cotes(serie)


def test_le_graphique_de_cotes_est_une_figure_PLOTLY():
    """Altair ne permettait ni de masquer une serie par defaut ni de la
    rallumer d'un clic sur la legende."""
    fig = _figure()
    assert fig is not None, "aucune figure produite"
    assert type(fig).__module__.startswith("plotly"), type(fig)


def test_les_cotes_LAY_sont_masquees_par_defaut():
    """Six courbes d'un coup rendent le graphique illisible. Le back porte
    la lecture ; le lay reste disponible d'un clic sur la legende, ce qui
    n'est pas la meme chose que de le supprimer.
    """
    fig = _figure()
    par_nom = {t.name: t for t in fig.data if t.name}
    lay = {n: t for n, t in par_nom.items() if "lay" in n.lower()}
    back = {n: t for n, t in par_nom.items() if "back" in n.lower()}
    assert lay, f"aucune serie lay dans la figure : {list(par_nom)}"
    assert back, f"aucune serie back dans la figure : {list(par_nom)}"
    for nom, trace in lay.items():
        assert trace.visible == "legendonly", \
            f"« {nom} » est affichee d'emblee ({trace.visible})"
    for nom, trace in back.items():
        assert trace.visible in (True, None), \
            f"« {nom} » devrait etre visible ({trace.visible})"


def test_l_echelle_des_cotes_reste_LOGARITHMIQUE():
    """3 a 4 % des releves depassent la cote 20, maximum observe 990 en lay,
    et ces extremes sont ceux de la FIN de match. En lineaire ils ecrasent
    l'echelle des 97 % autres."""
    fig = _figure()
    assert fig.layout.yaxis.type == "log", fig.layout.yaxis.type


def test_les_fins_de_jeu_sont_marquees():
    """Sans reperes, une courbe de cotes ne se rattache a rien du match."""
    fig = _figure()
    marques = list(fig.layout.shapes or []) + [
        a for a in (fig.layout.annotations or [])
    ]
    assert marques, "aucun repere de fin de jeu sur le graphique"


def test_le_graphique_porte_le_SCORE_au_survol():
    """Une courbe de cotes seule ne dit pas ce qui l'a fait bouger. Le score
    de l'instant, au survol, rattache chaque mouvement au match."""
    fig = _figure()
    porteuses = [t for t in fig.data if getattr(t, "customdata", None) is not None]
    assert porteuses, "aucune serie ne porte de donnee de survol"
    for t in porteuses:
        assert "%{customdata" in t.hovertemplate, \
            f"« {t.name} » n'affiche pas le score au survol : {t.hovertemplate}"
    # Et c'est bien le score qui y est, pas un indice.
    valeurs = {str(v[0]) for t in porteuses for v in t.customdata}
    assert any("-" in v for v in valeurs), f"pas un score : {sorted(valeurs)[:5]}"
