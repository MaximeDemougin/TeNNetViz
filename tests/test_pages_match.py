"""Tests bout en bout de pages/match.py via AppTest -- point du registre :
`str(m.get(champ) or "-")` affiche litteralement "nan" pour un NaN flottant
(NaN est vrai au sens booleen). Verifie que ce n'est plus le cas."""

import re
import sys
import time
import types

import pytest

import pandas as pd
from streamlit.testing.v1 import AppTest

from fixtures_reelles import (
    CHRONOLOGIE_REELLE,
    LIGNE_REELLE_MATCH_AUTRE_LIGUE,
    LIGNE_REELLE_POINT_FINAL,
    LIGNES_REELLES_MATCHS,
    LIGNES_REELLES_POINTS,
    LIGNES_REELLES_POINTS_NON_APPARIE,
    LIGNES_REELLES_POINTS_RECENTS,
    LIGNES_REELLES_QA,
    LIGNES_REELLES_SERIE_RECENTE,
)


#: Les CINQ tables que la page lit, chacune sous son nom. Le bouchon les
#: distingue par le nom present dans la requete, comme le ferait une vraie
#: base -- servir le meme tableau a toutes ferait passer une requete pour
#: une autre sans que rien ne le signale (une liste de matchs relue comme un
#: bilan de collecte, par exemple).
TABLES = ("live_now", "live_series", "live_qa_daily", "live_matches",
          "live_points")


def _restreindre_aux_identifiants(df, query):
    """Le `WHERE event_id IN (...)` de la requete, applique pour de vrai.

    Sans cela le bouchon rendrait TOUS les points quel que soit le match
    demande, et une page qui n'ouvrirait qu'un identifiant sur deux
    passerait le test sans qu'on le voie -- la mesure qui compte ici est
    justement que 3799286 porte 2 points quand 3802032 en porte 105.

    Un tableau sans colonne `event_id` (les series ecrites a la main par
    les tests plus anciens) traverse tel quel : il n'y a rien a restreindre.
    """
    demandes = re.findall(r"'([^']*)'", query)
    if not demandes or df is None or df.empty or "event_id" not in df.columns:
        return df
    return df[df["event_id"].astype(str).isin(demandes)]


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
                if df is None:
                    return pd.DataFrame()
                return _restreindre_aux_identifiants(df, query)
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


def recit_des_jeux(at):
    """Le tableau du recit jeu par jeu, retrouve par ses COLONNES."""
    for d in at.dataframe:
        if {"jeu", "service", "issue"} <= set(d.value.columns):
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


def test_le_point_par_point_reste_du_plus_recent_au_plus_ancien(monkeypatch):
    """L'intention EXISTANTE -- le dernier point en tete -- avec un tri qui
    ne depend plus de l'ordre d'arrivee.

    Le module inversait le tableau par `.iloc[::-1]`. Juste tant que la
    lecture rend les releves dans l'ordre du temps ; faux des qu'elle ne le
    fait plus, et `.iloc[::-1]` ne peut PAS le rattraper -- il ne sait rien
    du temps, il retourne des positions. On donne donc les quatre lignes
    REELLES de 3807291 dans un ordre MELANGE : le tableau doit rendre
    l'ordre du temps, decroissant.

    Les quatre scores sont distincts (0-0, 0-1, 0-2, 3-6/6-6), donc aucun
    repliement n'intervient et une permutation se voit ligne a ligne.
    """
    melangee = SERIE_RECENTE.iloc[[2, 0, 3, 1]].reset_index(drop=True)
    at = _niveau_2(monkeypatch, "3807291", serie=melangee,
                   points=POINTS_RECENTS)

    tableau = point_par_point(at)
    assert tableau is not None, "aucun tableau point par point"
    assert list(tableau["score"]) == ["3-6,6-6", "0-2", "0-1", "0-0"], \
        tableau.to_dict("records")
    # Les horodatages eux-memes decroissent -- le score seul pourrait
    # coincider par hasard sur un match ou il ne bouge pas.
    assert list(tableau["ts"]) == sorted(tableau["ts"], reverse=True), \
        tableau.to_dict("records")


def test_le_recit_des_jeux_est_du_plus_recent_au_plus_ancien(monkeypatch):
    """Meme regle sur le recit : le dernier jeu joue en tete.

    La chronologie REELLE de Xi Luo vs Meng Yi Chen est donnee dans un
    ordre MELANGE, pour la meme raison que ci-dessus : `.iloc[::-1]`
    rendrait alors n'importe quoi.
    """
    import json

    matchs_df = pd.DataFrame([{
        "event_id": "evt-recit", "status": "InPlay",
        "participant1": "Xi Luo", "participant2": "Meng Yi Chen",
        "league": "W15 Test", "score": "1-3", "points": "0-0", "server": None,
        "updated_ts": time.time(),
        "chronologie": json.dumps([CHRONOLOGIE_REELLE[i] for i in (2, 0, 3, 1)]),
    }])
    _mock_lecteur(monkeypatch, matchs_df, pd.DataFrame())
    at = AppTest.from_file("pages/match.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.query_params["event_id"] = "evt-recit"
    at.run()
    assert not at.exception, at.exception

    tableau = recit_des_jeux(at)
    assert tableau is not None, "aucun tableau de recit"
    assert list(tableau["jeu"]) == [4, 3, 2, 1], tableau.to_dict("records")
    # Le service ALTERNE et les issues ne sont pas toutes egales : les deux
    # colonnes suivent leur jeu, elles ne sont pas triees a part.
    assert list(tableau["service"]) == ["Meng Yi Chen", "Xi Luo",
                                        "Meng Yi Chen", "Xi Luo"], \
        tableau.to_dict("records")
    assert list(tableau["issue"]) == ["BREAK", "BREAK", "tenu", "BREAK"], \
        tableau.to_dict("records")


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


def test_la_liste_des_matchs_est_du_plus_recent_au_plus_ancien(monkeypatch):
    """La regle de toute l'application, sur le tableau de la liste.

    L'entree est deliberement MELANGEE : `charger_matchs_passes` demande
    bien `ORDER BY day DESC, start_ts DESC`, mais un tableau qui se
    contenterait de recopier son entree afficherait n'importe quoi le jour
    ou la lecture change (un filtre, un cache, un regroupement, une autre
    source). L'ordre doit etre garanti PAR la mise en forme.

    Les six lignes REELLES discriminent a DEUX niveaux : cinq journees
    distinctes du 2 au 6 aout, et DEUX lignes le 6 aout dont les heures de
    debut different (08:00 pour Dzumhur, 09:00 pour Alexandrescou). Un tri
    qui oublierait la seconde cle passerait le premier niveau et raterait
    celui-la.

    LE MELANGE N'EST PAS QUELCONQUE : les deux lignes du 6 aout arrivent
    dans l'ordre CROISSANT (08:00 avant 09:00). Le tri etant stable, un tri
    sur la seule journee les laisserait dans cet ordre-la -- donc faux. Le
    melange precedent les donnait deja dans le bon ordre et la mutation
    « cle d'heure perdue » y survivait, verte.
    """
    melange = pd.DataFrame(LIGNES_REELLES_MATCHS).iloc[[3, 0, 4, 2, 5, 1]]
    at = _niveau_1(monkeypatch, matchs=melange.reset_index(drop=True))

    table = liste_des_matchs(at)
    assert list(table["Jour"]) == ["2026-08-06", "2026-08-06", "2026-08-05",
                                   "2026-08-04", "2026-08-03", "2026-08-02"], \
        table.to_dict("records")
    # A journee egale, l'heure de debut DECROIT elle aussi.
    #
    # La propriete est enoncee comme un ORDRE et non par deux valeurs en dur :
    # celles-ci etaient de l'UTC, et le passage a l'heure de Paris le
    # 2026-08-11 les a fait rougir alors que le tri -- l'objet de ce test --
    # n'avait pas bouge. Un test qui casse quand son sujet ne change pas
    # designe mal son sujet.
    debuts = list(table["Début"])[:2]
    assert debuts[0] > debuts[1], table.to_dict("records")
    assert len(set(debuts)) == 2, (
        "les deux heures sont EGALES : ce niveau de tri n'est pas discrimine"
    )
    # Et les colonnes restent SOLIDAIRES de leur ligne : trier le seul
    # « Jour » sans emporter le reste melangerait les matchs entre les jours.
    assert table["Match"].iloc[0].startswith("Yannick"), \
        table.to_dict("records")
    assert table["Identifiants"].iloc[0] == "3807294", table.to_dict("records")
    # La colonne « Apparié » suit elle aussi : elle est calculee a part, sur
    # une Serie -- si le tri arrive apres, elle se decale d'un cran et le
    # match non apparie s'affiche comme apparie.
    assert table["Apparié"].iloc[0] == "non", table.to_dict("records")
    assert table["Apparié"].iloc[1] == "oui", table.to_dict("records")


def test_une_ligne_SANS_journee_ne_prend_pas_la_tete_de_la_liste(monkeypatch):
    """`day` absente : sans `na_position`, pandas la pose ou il veut. Une
    absence ne peut pas occuper la place de la journee la plus recente --
    ni faire lever la page."""
    sans_jour = dict(LIGNES_REELLES_MATCHS[0])
    sans_jour.update({"day": None, "start_ts": float("nan"),
                      "event_id": "9999999", "match_id": None})
    at = _niveau_1(
        monkeypatch,
        matchs=pd.DataFrame([sans_jour] + LIGNES_REELLES_MATCHS),
    )
    table = liste_des_matchs(at)
    assert table["Jour"].iloc[0] == "2026-08-06", table.to_dict("records")
    assert table["Jour"].iloc[-1] == "—", table.to_dict("records")


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


# ══════════════════════════════════════════════════════════════════════
# NIVEAU 2 : le match choisi -- avec ses cotes, ou en le DISANT
# ══════════════════════════════════════════════════════════════════════
#
# LA LIMITE DURE : `live_series` ne couvre que ~2,6 jours (45 179 lignes du
# 2026-08-04 13:50 au 2026-08-07 09:04) quand `live_points` en couvre dix.
# Un match ancien garde donc son point par point mais perd sa courbe de
# cotes. La page doit le DIRE et ne jamais afficher un graphique vide : une
# absence silencieuse se lit comme une panne.
#
# Ce n'est PAS une perte de donnee mais une limite d'ACCES -- les cotes
# brutes vivent dans les fichiers du collecteur, que cette page (hebergee
# ailleurs) ne peut pas lire. Le message doit etre juste sur ce point.

SERIE_RECENTE = pd.DataFrame(LIGNES_REELLES_SERIE_RECENTE)
POINTS_RECENTS = pd.DataFrame(LIGNES_REELLES_POINTS_RECENTS)
POINTS_ANCIENS = pd.DataFrame(LIGNES_REELLES_POINTS + [LIGNE_REELLE_POINT_FINAL])
POINTS_NON_APPARIE = pd.DataFrame(LIGNES_REELLES_POINTS_NON_APPARIE)

#: Les deux identifiants de la MEME rencontre (Duckworth vs O'Connell) :
#: c'est ce que la liste met dans l'URL, et ce que le detail doit ouvrir.
DUCKWORTH = "3799286,3802032"


def _capturer_graphiques(monkeypatch):
    """Les figures REELLEMENT poussees a l'ecran.

    Verifier le source ne suffirait pas : ce qui compte est qu'aucun cadre
    vide n'arrive devant l'utilisateur.
    """
    import streamlit as st

    captures = []
    vrai = st.plotly_chart
    monkeypatch.setattr(
        st, "plotly_chart",
        lambda fig, **kw: (captures.append(fig), vrai(fig, **kw))[1],
    )
    return captures


def _niveau_2(monkeypatch, event_id, serie=None, points=None, matchs=None):
    """La page avec un match choisi, et AUCUN match dans le direct.

    `live_now` vide est l'etat normal d'un match archive : il n'est plus
    publie depuis longtemps, et c'est justement pour ceux-la que les tables
    du passe existent.
    """
    at = _page(
        monkeypatch,
        live_qa_daily=BILAN_REEL,
        live_matches=PASSES_REELS if matchs is None else matchs,
        live_points=points,
        live_series=serie,
    )
    at.query_params["event_id"] = event_id
    at.run()
    assert not at.exception, at.exception
    return at


def _messages(at):
    return ([str(i.value) for i in at.info] + [str(w.value) for w in at.warning]
            + [str(c.value) for c in at.caption])


def test_un_match_ancien_sans_serie_DIT_que_les_cotes_ne_sont_pas_conservees(monkeypatch):
    """Le match Duckworth du 2-3 aout a ses 107 points mais plus une seule
    ligne de serie : la retention est passee dessus.

    Deux exigences, et la seconde compte autant que la premiere : le dire,
    et ne PAS pousser de graphique vide.
    """
    captures = _capturer_graphiques(monkeypatch)
    at = _niveau_2(monkeypatch, DUCKWORTH, serie=None, points=POINTS_ANCIENS)

    dits = [t for t in _messages(at) if "cotes conservées" in t]
    assert dits, _messages(at)
    texte = dits[0]
    # La retention, chiffree : sans elle le lecteur ne sait pas si c'est
    # une panne, un oubli, ou la regle.
    assert "2,6" in texte, texte
    # Et ce n'est PAS une perte : les cotes existent, ailleurs. Alarmer
    # ferait rouvrir un chantier qui n'a pas lieu d'etre.
    assert "pas une perte" in texte, texte
    assert not captures, "un graphique a ete pousse alors que la serie est vide"


def test_le_point_par_point_reste_affiche_quand_les_cotes_manquent(monkeypatch):
    """`live_points` couvre dix jours quand `live_series` en couvre 2,6 :
    perdre la courbe ne doit pas emporter le deroulement du match."""
    at = _niveau_2(monkeypatch, DUCKWORTH, serie=None, points=POINTS_ANCIENS)

    tableau = point_par_point(at)
    assert tableau is not None, "aucun tableau point par point"
    # Les SIX releves des deux identifiants, replies en quatre etats de jeu
    # (trois « 0-0 / 0-0 » consecutifs n'en font qu'un).
    assert len(tableau) == 4, tableau.to_dict("records")
    assert "6-3,6-1" in set(tableau["score"]), tableau.to_dict("records")
    # Les DEUX identifiants ont ete ouverts : n'en lire qu'un ne donnerait
    # que quatre releves sur six, et la page le compte a voix haute.
    assert any("6 relevés" in t for t in _messages(at)), _messages(at)


def test_le_score_d_un_match_archive_vient_du_DERNIER_point(monkeypatch):
    """`live_matches` ne porte ni score ni statut. Et le statut du dernier
    releve dit encore « InPlay » alors que le match est fini depuis quatre
    jours -- le reprendre ferait passer une archive pour un match en cours.
    """
    at = _niveau_2(monkeypatch, DUCKWORTH, serie=None, points=POINTS_ANCIENS)

    par_label = {m.label: m.value for m in at.metric}
    assert par_label["Score"] == "6-3,6-1", par_label
    textes = " ".join(_messages(at))
    assert "archivé" in textes, textes
    assert "InPlay" not in textes, textes


def test_un_match_recent_affiche_bien_ses_cotes(monkeypatch):
    """Le meme ecran, sur un match que la retention couvre encore : la
    courbe est la, et aucun message d'absence ne s'affiche."""
    captures = _capturer_graphiques(monkeypatch)
    at = _niveau_2(monkeypatch, "3807291", serie=SERIE_RECENTE,
                   points=POINTS_RECENTS)

    assert captures, "aucun graphique pousse alors que la serie existe"
    noms = {t.name for t in captures[0].data}
    assert {"back a", "back b"} <= noms, noms
    assert not [t for t in _messages(at) if "cotes conservées" in t], _messages(at)
    assert not [t for t in _messages(at) if "marché apparié" in t], _messages(at)


def test_un_match_JAMAIS_apparie_ne_parle_PAS_de_retention(monkeypatch):
    """Deux absences de cotes, deux motifs, et les confondre serait mentir.

    3807294 (Plovdiv 2 Challenger) n'a jamais eu de marche : `id_market`,
    `ID_MATCH` et `p1_is_home` tous NULL -- l'etat de 737 lignes sur 1 153.
    Ses cotes ne manquent pas parce que la retention est passee : il n'y en
    a jamais eu. Accuser la retention ferait chercher un trou de collecte
    la ou il n'y en a pas.
    """
    at = _niveau_2(monkeypatch, "3807294", serie=None,
                   points=POINTS_NON_APPARIE)

    textes = _messages(at)
    assert not [t for t in textes if "cotes conservées" in t], textes
    assert [t for t in textes if "marché apparié" in t], textes
    # Le match est quand meme la, avec son deroulement.
    tableau = point_par_point(at)
    assert tableau is not None and "7-5,6-3" in set(tableau["score"]), \
        None if tableau is None else tableau.to_dict("records")


def test_le_detail_s_affiche_SOUS_la_liste_et_pas_a_sa_place(monkeypatch):
    """Un ecran a deux niveaux : choisir un match ne doit pas faire
    disparaitre le bilan ni la liste -- on passe d'un match a l'autre sans
    revenir en arriere."""
    at = _niveau_2(monkeypatch, "3807291", serie=SERIE_RECENTE,
                   points=POINTS_RECENTS)

    titres = [str(s.value) for s in at.subheader]
    assert any("Santé de la collecte" in t for t in titres), titres
    assert any("Le match choisi" in t for t in titres), titres
    assert liste_des_matchs(at) is not None, "la liste a disparu"


def test_l_heure_de_la_page_MATCH_est_aussi_a_l_heure_de_Paris():
    """Trouve par le garde structurel, pas a l'oeil : la page « Match » porte
    son PROPRE `_heure`, que le balayage du 2026-08-11 a fait sortir.

    Deux echelles sur deux pages voisines seraient pires qu'une seule fausse :
    le meme match afficherait deux heures differentes selon l'endroit ou on le
    regarde.
    """
    import importlib

    module = importlib.import_module("pages.match")
    assert module._heure(1786449600) == "14:00"   # ete, CEST
    assert module._heure(1800014400) == "13:00"   # hiver, CET
    assert module._heure(None) == "—"


# ── Les paris du compte dans la fenetre de detail ────────────────────────
#
# La ligne donne UN montant ; la fenetre donne le detail. Fixture PRELEVEE :
# marche 1.260944641, ID_BET 31402 et 31396, deux lay reels du 2026-08-10.


def _position_reelle():
    return {
        "a": {"n": 2, "demande": 76.39, "mise": 54.31, "gain": 76.39,
              "cote_moyenne": 1.7109, "cote_courante": 1.30,
              "cash_out": -31.9,
              "paris": [
                  {"ID_BET": 31402, "bet_libelle": "Denis Yevseyev",
                   "side_back_lay": "lay", "odds": 1.72, "stake": 62.58,
                   "potential_profit": 62.58, "liability": 45.06,
                   "created_at": pd.Timestamp("2026-08-10 14:00:00")},
                  {"ID_BET": 31396, "bet_libelle": "Denis Yevseyev",
                   "side_back_lay": "lay", "odds": 1.67, "stake": 13.81,
                   "potential_profit": 13.81, "liability": 9.25,
                   "created_at": pd.Timestamp("2026-08-10 13:50:00")},
              ]},
        "b": None, "non_rattaches": [],
    }


def test_la_fenetre_DETAILLE_les_paris_du_compte():
    """La ligne donne le montant, la fenetre donne le detail : chaque pari
    avec son heure, sa cote, ce qu'il risque et ce qu'il rapporte.

    Ce test verifie la STRUCTURE rendue, pas la mise en page : c'est ce qui
    doit rester vrai quand la feuille de style change.
    """
    from detail_match import tableau_paris

    lignes = tableau_paris(_position_reelle())
    assert len(lignes) == 2
    assert "Demandé" not in lignes[0], (
        "une colonne « Demandé » identique a l'apparie repete la meme somme "
        "et laisse croire a deux montants distincts"
    )
    assert lignes[0]["Sélection"] == "Denis Yevseyev"
    assert lignes[0]["Sens"] == "lay"
    assert lignes[0]["Cote"] == 1.72
    # Le RISQUE est `stake` -- pas la colonne `liability` (45,06), fausse
    # pour un lay. Le GAIN s'en deduit par la formule de `data.py`.
    from paris_live import gain_net
    assert lignes[0]["Risque"] == 62.58
    assert lignes[0]["Gain"] == pytest.approx(gain_net("lay", 62.58, 1.72), abs=0.01)
    assert lignes[0]["Gain"] != pytest.approx(62.58, abs=0.5)


def test_la_fenetre_n_affiche_PLUS_les_colonnes_fausses_de_la_base():
    """`liability` et `potential_profit` sont fausses pour un lay, et la
    fenetre les rendait telles quelles. La fixture les met a des valeurs
    ABSURDES : si l'une reapparait, le test tombe.

    ID_BET 31449, releve tel quel : `stake` 81,18 quand `liability` en dit
    130,59 et `potential_profit` 77,73."""
    from detail_match import tableau_paris

    position = _position_reelle()
    position["a"]["paris"] = [{
        **position["a"]["paris"][0], "ID_BET": 31449, "odds": 2.68,
        "stake": 81.18, "potential_profit": -999.0, "liability": -999.0}]
    ligne = tableau_paris(position)[0]
    assert "Demandé" not in ligne
    assert ligne["Risque"] == 81.18
    assert ligne["Gain"] > 0


def test_un_pari_NON_RATTACHE_apparait_quand_meme_dans_la_fenetre():
    """Sa mise et son sens ne dependent d'aucun cote. Le cacher reviendrait a
    faire disparaitre de l'argent reellement engage."""
    from detail_match import tableau_paris

    position = {"a": None, "b": None, "non_rattaches": [
        {"ID_BET": 1, "bet_libelle": "Joueur Inconnu", "side_back_lay": "lay",
         "odds": 2.0, "stake": 10.0, "potential_profit": 10.0,
         "liability": 10.0,
         "created_at": pd.Timestamp("2026-08-10 14:00:00")}]}
    lignes = tableau_paris(position)
    assert len(lignes) == 1
    assert lignes[0]["Sélection"] == "Joueur Inconnu"


def test_l_heure_d_un_pari_est_DEJA_locale_et_ne_se_reconvertit_PAS():
    """`Bet.created_at` est un DATETIME, pas un epoch, et le serveur de base
    tourne a l'heure de PARIS.

    Mesure du 2026-08-11 : son `NOW()` rend 15:49:36 quand son
    `UTC_TIMESTAMP()` rend 13:49:36, et son dernier pari date de 15:33 -- seize
    minutes plus tot. En UTC, ce pari serait dans deux heures.

    Le passer par `to_paris`, qui suppose l'UTC pour un instant NAIF, le
    decalerait donc de deux heures : un pari de 14:00 s'afficherait a 16:00.
    C'est l'erreur SYMETRIQUE de celle du 2026-08-11 -- convertir ce qui l'est
    deja -- et elle est aussi fausse.
    """
    from detail_match import tableau_paris

    position = _position_reelle()
    position["a"]["paris"] = [position["a"]["paris"][0]]
    heure = tableau_paris(position)[0]["Heure"]
    assert heure == "14:00", (
        f"heure affichee : {heure}. « 16:00 » signifie qu'on reconvertit un "
        "instant deja local ; « 12:00 » qu'on le reconvertit a l'envers"
    )


def test_un_NOMBRE_ne_devient_PAS_une_heure():
    """On ne devine pas une heure a partir d'un nombre.

    `pd.Timestamp(1786449600.0)` lit le flottant comme des NANOSECONDES depuis
    1970 et rend « 00:00 » -- une heure parfaitement plausible, et fausse de
    cinquante-six ans. Le tiret dit qu'on ne sait pas, et c'est le vocabulaire
    deja employe partout ailleurs dans cette application pour une donnee
    absente.
    """
    from detail_match import tableau_paris

    position = _position_reelle()
    position["a"]["paris"] = [
        {**position["a"]["paris"][0], "created_at": 1786449600.0}]
    assert tableau_paris(position)[0]["Heure"] == "—"


def test_le_tableau_des_paris_TIENT_sur_la_forme_REELLE_de_la_base():
    """LE TEST QUI MANQUAIT, et son absence a casse la production.

    `Bet.created_at` remonte en `datetime64[ns]`, donc en `pd.Timestamp` une
    fois passe par `to_dict("records")`. La fixture d'origine portait un
    EPOCH -- inventee, pas prelevee -- et `float(Timestamp)` leve un
    `TypeError`. La fenetre de detail tombait des qu'on ouvrait un match
    parie ; rien ne l'a vu, parce qu'aucun test ne faisait passer des paris
    par la CHAINE ENTIERE.

    Celui-ci part d'un `DataFrame` aux dtypes de la base et traverse
    `positions` puis `tableau_paris`, exactement comme la page.
    """
    import pandas as pd

    from detail_match import tableau_paris
    from paris_live import positions

    paris = pd.DataFrame([{
        "ID_BET": 31402, "ID_MARKET": "1.260944641", "side_back_lay": "lay",
        "bet_libelle": "Denis Yevseyev", "odds": 1.72, "stake": 62.58,
        "potential_profit": 62.58, "liability": 45.06,
        "created_at": "2026-08-10 14:00:00",
    }])
    paris["created_at"] = pd.to_datetime(paris["created_at"])
    assert str(paris["created_at"].dtype) == "datetime64[ns]", (
        "la fixture n'a pas le type de la base : elle ne prouve rien"
    )
    match = {"event_id": "3818322", "id_market": "1.260944641",
             "participant1": "Yevseyev", "participant2": "Purtseladze",
             "back_odds_a": 1.30, "lay_odds_a": 1.32,
             "back_odds_b": 4.20, "lay_odds_b": 4.40, "status": "InPlay"}
    lignes = tableau_paris(positions(paris, [match])["3818322"])
    assert lignes[0]["Heure"] == "14:00"
    assert lignes[0]["Risque"] == 62.58


def test_SANS_pari_la_fenetre_ne_rend_aucune_ligne():
    """Pas de tableau vide sur les matchs qu'on n'a pas paries."""
    from detail_match import tableau_paris

    assert tableau_paris(None) == []
    assert tableau_paris({"a": None, "b": None, "non_rattaches": []}) == []


class _StreamlitEnregistreur:
    """Un Streamlit de paille qui note ce qu'on lui demande d'afficher.

    Lire la SOURCE du module ne vaut rien ici : le mot « indicatif » figure
    aussi dans la docstring, et vider la legende laissait le test vert.
    C'est ce qui est RENDU qu'il faut regarder.
    """

    def __init__(self):
        self.legendes, self.titres, self.mesures, self.tableaux = [], [], [], []

    def caption(self, texte, *a, **k):
        self.legendes.append(str(texte))

    def markdown(self, texte, *a, **k):
        self.titres.append(str(texte))

    def dataframe(self, table, *a, **k):
        self.tableaux.append(table)

    def metric(self, libelle, valeur, *a, **k):
        self.mesures.append((str(libelle), str(valeur)))

    def columns(self, n, *a, **k):
        return [self] * (n if isinstance(n, int) else len(n))


def test_la_fenetre_DIT_que_le_cash_out_est_indicatif(monkeypatch):
    """Notre chiffre se calcule sur le MEILLEUR prix affiche ; celui de
    l'exchange applique son propre ecart et sa liquidite, et le vrai reglement
    nette le marche ENTIER. Afficher un montant sans cette reserve le ferait
    prendre pour une promesse."""
    import detail_match

    faux = _StreamlitEnregistreur()
    monkeypatch.setattr(detail_match, "st", faux)
    detail_match.bandeau_paris({"participant1": "Yevseyev",
                                "participant2": "Purtseladze"},
                               _position_reelle())
    assert faux.legendes, "aucune reserve n'est rendue sous les montants"
    assert "INDICATIF" in " ".join(faux.legendes).upper()
    assert ("-31,90 €" in dict(faux.mesures).get("Cash-out Yevseyev", "")
            or "-31.90 €" in dict(faux.mesures).get("Cash-out Yevseyev", "")), \
        dict(faux.mesures)


def test_SANS_pari_la_fenetre_n_affiche_RIEN_du_tout(monkeypatch):
    """Ni titre, ni tableau vide, ni reserve orpheline sur les matchs qu'on
    n'a pas paries -- c'est-a-dire la plupart."""
    import detail_match

    faux = _StreamlitEnregistreur()
    monkeypatch.setattr(detail_match, "st", faux)
    detail_match.bandeau_paris({"participant1": "A", "participant2": "B"}, None)
    assert (faux.legendes, faux.titres, faux.mesures, faux.tableaux) == ([], [], [], [])


def test_le_bloc_des_paris_est_CABLE_dans_la_fenetre():
    """Une reserve parfaite et jamais rendue ne protege personne."""
    import inspect

    import detail_match

    assert "bandeau_paris(" in inspect.getsource(detail_match.afficher)
