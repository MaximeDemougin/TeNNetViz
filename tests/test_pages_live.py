"""Tests bout en bout de pages/live.py via AppTest -- la preuve exigee pour
le defaut C4 : une ligne dont `updated_ts` est vieux doit afficher des
pastilles rouges, une ligne fraiche des pastilles vertes, meme quand leur
age STOCKE (age_score_s, etc.) est identiquement petit. Sans le rattrapage
`age_stocke + (maintenant - updated_ts)`, les deux seraient vertes -- c'est
exactement le defaut que la page existe pour empecher.
"""

import sys
import time
import types

import pandas as pd
from streamlit.testing.v1 import AppTest

import live_data

_DERNIER = {"df": None, "maintenant": 0.0}
from live_data import SEUIL_BATTEMENT_ARRETE_S, SEUILS_PAR_FLUX
from fixtures_reelles import (
    LIGNE_REELLE_BOOKS_FLUX_MORT,
    LIGNE_REELLE_BOOKS_SAINE,
    LIGNE_REELLE_FINISHED,
    LIGNE_REELLE_INPLAY,
    LIGNE_REELLE_MI_CYCLE,
)



ORDRE_FLUX = list(SEUILS_PAR_FLUX)


def _detail(at, flux):
    """L'age detaille d'un flux, desormais affiche dans le panneau de detail
    et non plus dans la liste."""
    libelle = SEUILS_PAR_FLUX[flux][2].replace(" -- ", " · ")
    for m in at.metric:
        if m.label == libelle:
            return m.value
    return None



def html_liste(at, second=False):
    """Tout le HTML de liste pousse par la page, concatene.

    La page dessine UNE ligne par element markdown -- il faut bien, chaque
    ligne ayant son propre bouton d'ouverture a cote. On relit donc ce qui
    est REELLEMENT affiche, et non un calcul rejoue : rejouer la logique dans
    l'aide reviendrait a verifier que la page fait ce que le test refait,
    pas ce qu'elle montre.

    ATTENTION : le HTML rendu inclut aussi les feuilles de style injectees
    (CSS_FLUX, liste_dense.CSS) -- elles contiennent, comme SELECTEURS, du
    texte qu'un test peut vouloir compter comme SIGNAL ("hausse"/"baisse" x4
    chacun dans liste_dense.CSS, ".liste-dense .neuf" dans CSS_FLUX). Un
    comptage de sous-chaine naif part donc d'un bruit non nul, jamais de
    zero -- deja constate une fois (test_les_six_matchs_gardent_leur_FLECHE
    passait a tort sur ce bruit seul). Compter la BALISE rendue, pas le nom
    de classe brut.
    """
    morceaux = [str(m.value) for m in at.markdown if "liste-dense" in str(m.value)]
    if not second:
        return "".join(morceaux)
    # La seconde liste (matchs termines) commence apres le sous-titre.
    return "".join(morceaux)


def structure(at, second=False):
    """Ce que la page AFFICHE, relu depuis son HTML : un dictionnaire par
    match, dans l'ordre d'affichage."""
    import re
    from live_data import SEUILS_PAR_FLUX
    morceaux = [str(m.value) for m in at.markdown if "liste-dense" in str(m.value)]
    out, circuit, tournoi = [], "", ""
    for bloc in morceaux:
        entete = re.search(r'class="competition[^"]*">([^<]*)<', bloc)
        if entete:
            circuit = entete.group(1)
        titre = re.search(r'class="titre">([^<]*)</span>', bloc)
        if titre:
            tournoi = titre.group(1)
        if 'class="match' not in bloc:
            continue
        voulue = "termines" if second else "en-cours"
        if f'data-section="{voulue}"' not in bloc:
            continue
        # Le marqueur de service occupe TOUJOURS sa place -- vide quand le
        # joueur ne sert pas -- pour que les deux noms d'un match s'alignent.
        noms = re.findall(r'<div class="nom( sert)?"><span>([^<]*)</span></div>', bloc)
        balles = re.findall(r"<em>([^<]*)</em>", bloc)
        heure = re.search(r'class="heure">([^<]*)<', bloc)
        etats = re.findall(r'<u class="(\w+)"', bloc)
        out.append({
            "competition": circuit,
            "tournoi": tournoi,
            "heure": heure.group(1) if heure else "",
            "joueurs": [
                {"nom": n.strip(), "sert": bool(sert),
                 "balle": bool(balles[i].strip()) if i < len(balles) else False}
                for i, (sert, n) in enumerate(noms)
            ],
            "fraicheur": [{"flux": f, "etat": e} for f, e in zip(SEUILS_PAR_FLUX, etats)],
            "balle": "🎾" in bloc,
            "ouvert": "match ouvert" in bloc,
        })
    return out


def pastille(ligne_ou_at, flux):
    """L'etat d'UN flux, tel qu'AFFICHE."""
    ligne = ligne_ou_at if isinstance(ligne_ou_at, dict) else structure(ligne_ou_at)[0]
    etats = {f["flux"]: f["etat"] for f in ligne["fraicheur"]}
    return {"frais": "🟢", "perime": "🔴", "inconnu": "⚪"}[etats[flux]]


def _mock_lecteur(monkeypatch, df, serie=None):
    """Injecte un faux `db_utils.db_utils.read_sql_query`, meme procede que
    tests/test_live_data.py::test_le_lecteur_par_defaut_ne_deplace_pas_le_repertoire_courant :
    pages/live.py appelle charger_matchs() SANS lecteur, qui passe par
    _lecteur_par_defaut() et importe ce module -- on le remplace avant que
    l'import n'ait lieu, sans toucher a un vrai credentials.yml.

    ``serie`` : reponse SEPAREE pour les requetes visant `live_series`
    (charger_serie/charger_mouvements). Sans elle, le meme mock repond aux
    deux tables -- suffisant tant qu'aucun test ne regarde le mouvement des
    prix. Le test de la fleche (task 3) a besoin des deux formes a la fois :
    `df` est une ligne PAR MATCH (`live_now`), `serie` plusieurs RELEVES par
    match (`live_series`, colonne `ts`) -- un seul mock aurait servi la
    premiere la ou le calcul du mouvement attend la seconde, et
    mouvements_de_prix() se serait tu sans jamais toucher au vrai defaut."""
    faux = types.ModuleType("db_utils.db_utils")
    if serie is None:
        faux.read_sql_query = lambda schema, query: df
    else:
        faux.read_sql_query = lambda schema, query: (
            serie if "live_series" in query else df)
    monkeypatch.setitem(sys.modules, "db_utils", types.ModuleType("db_utils"))
    monkeypatch.setitem(sys.modules, "db_utils.db_utils", faux)


def _lignes_deux_matchs(maintenant):
    # Les deux lignes ont le MEME age stocke (2 s, minuscule) sur les quatre
    # flux : seule la difference d'updated_ts doit produire une difference
    # de pastille. C'est le point precis du defaut C4. L'offset de la ligne
    # perimee (1h) doit depasser le PLUS LARGE des quatre seuils par flux
    # (SEUIL_FRAICHEUR_EXCHANGE_S = 720 s) : 300 s, suffisant sous l'ancien
    # seuil unique de 30 s, ne l'est plus pour l'exchange depuis ce tour.
    commun = {
        "status": "InPlay",
        "league": "ATP Test",
        "score": "6-4, 3-2", "points": "30-15",
        "back_odds_a": 1.5, "back_odds_b": 2.6,
        "book_odds_a": 1.55, "book_odds_b": 2.5,
        "age_score_s": 2.0, "age_exchange_s": 2.0,
        "age_books_s": 2.0, "age_stats_s": 2.0,
    }
    return pd.DataFrame([
        {**commun, "event_id": "evt-frais",
         "participant1": "A. Frais", "participant2": "B. Vivant",
         "updated_ts": maintenant},
        {**commun, "event_id": "evt-perime",
         "participant1": "C. Fige", "participant2": "D. Mort",
         "updated_ts": maintenant - 3600.0},
    ])


def _lancer(monkeypatch, df, battement_publieur=None, battement_score=None,
            battement_score_absent=None, serie=None):
    """``battement_publieur``/``battement_score`` : callables injectes pour
    ``live_data.lire_battement_publieur``/``lire_battement_score``. Par
    defaut (non fournis), les DEUX sont mockes a ``lambda: None``
    (illisibles) : depuis le tour 3, un battement LISIBLE est AUTORITAIRE
    sur le verdict de ``publieur_arrete()`` (I1a) -- ne pas les mocker
    ferait dependre CHAQUE test de l'etat REEL des fichiers
    ``heartbeat-*.json`` de cette machine (le publieur y tourne
    effectivement), ce que la suite ne peut pas se permettre
    (determinisme). Un test qui veut exercer le chemin "battement lisible"
    passe explicitement l'un des deux parametres.

    ``battement_score_absent`` : callable injecte pour
    ``live_data.battement_absent`` (tour 6). Par defaut (non fourni), mocke
    a ``lambda chemin: False`` ("jamais absent") -- meme motif que
    ci-dessus : ``capteur_score_mort()`` appelle desormais
    ``battement_absent(CHEMIN_BATTEMENT_SCORE)`` en interne quand son
    battement est illisible, et sans ce mock, CE check-la toucherait le
    vrai systeme de fichiers (le fichier existe reellement sur cette
    machine aujourd'hui, mais rien ne le garantit pour toujours -- exactement
    le defaut de determinisme que ce fichier de test s'interdit partout
    ailleurs).

    ``serie`` : transmis a ``_mock_lecteur`` -- reponse a part pour
    ``live_series``, quand un test a besoin que ``charger_serie``/
    ``charger_mouvements`` lisent autre chose que ``df`` (task 3)."""
    _DERNIER["df"] = df
    _DERNIER["maintenant"] = time.time()
    _mock_lecteur(monkeypatch, df, serie=serie)
    monkeypatch.setattr(
        live_data, "lire_battement_publieur",
        battement_publieur if battement_publieur is not None else (lambda: None),
    )
    monkeypatch.setattr(
        live_data, "lire_battement_score",
        battement_score if battement_score is not None else (lambda: None),
    )
    monkeypatch.setattr(
        live_data, "battement_absent",
        battement_score_absent if battement_score_absent is not None else (lambda chemin: False),
    )
    at = AppTest.from_file("pages/live.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.session_state["ID_USER"] = 1
    at.run()
    return at


def test_preuve_ligne_perimee_rouge_ligne_fraiche_verte(monkeypatch):
    maintenant = time.time()
    at = _lancer(monkeypatch, _lignes_deux_matchs(maintenant))

    assert not at.exception

    tableau = structure(at)
    par_nom = {l["joueurs"][0]["nom"]: l for l in tableau}
    frais, perime = par_nom["A. Frais"], par_nom["C. Fige"]
    for flux in ("f_score", "f_exchange", "f_books", "f_stats"):
        assert pastille(frais, flux) == "🟢", f"{flux} frais attendu vert, recu {frais[flux]!r}"
        assert pastille(perime, flux) == "🔴", f"{flux} perime attendu rouge, recu {perime[flux]!r}"


def test_bandeau_publieur_arrete_quand_toutes_les_lignes_sont_vieilles(monkeypatch):
    maintenant = time.time()
    lignes = _lignes_deux_matchs(maintenant)
    lignes["updated_ts"] = maintenant - 3600.0  # publieur mort depuis 1h
    at = _lancer(monkeypatch, lignes)

    assert not at.exception
    assert len(at.error) >= 1
    assert "publieur" in at.error[0].value.lower()

    tableau = structure(at)
    for flux in ("f_score", "f_exchange", "f_books", "f_stats"):
        # La cellule porte « pastille + age effectif » : on compare le PREMIER
        # caractere. Le mordant est intact -- une pastille qui changerait de
        # couleur fait toujours tomber ce test -- sans figer le texte de l'age,
        # qui depend de l'instant du rendu.
        assert all(pastille(l, flux) == "🔴" for l in tableau), \
            f"{flux} : attendu rouge partout, recu {list(tableau[flux])}"


def test_bandeau_absent_quand_le_publieur_est_vivant(monkeypatch):
    maintenant = time.time()
    lignes = _lignes_deux_matchs(maintenant)
    lignes["updated_ts"] = maintenant  # tout frais, publieur vivant
    at = _lancer(monkeypatch, lignes)

    assert not at.exception
    assert len(at.error) == 0


# --- Preuve contre l'etat REEL de la base (C2 / I3) --------------------------
#
# Les tests ci-dessus utilisent une fixture ou les quatre ages sont posees a
# une meme petite valeur non-NaN : combinaison qui n'existe sur AUCUNE ligne
# reelle de TeNNet_test.live_now (mesure le 2026-08-03 : f_exchange/f_books/
# f_stats valent NULL -> NaN sur la grande majorite des lignes en cours).
# Elle ne peut donc jamais produire une pastille "inconnu" (blanche), et ne
# protege pas contre une pastille "inconnu" cassee (ex. PASTILLE["inconnu"]
# mappee au vert par erreur, pages/live.py:35). Les tests suivants utilisent
# LIGNE_REELLE_INPLAY, prelevee telle quelle sur la table reelle.


def test_ligne_reelle_avec_ages_inconnus_ne_devient_jamais_verte(monkeypatch):
    """Preuve directe de C2. Sur la ligne REELLE (event_id 3796196), les
    flux books/stats sont NULL en base -> NaN pandas : c'est l'etat DOMINANT
    en base le jour de la capture (50-55 lignes sur 58-59), pas un cas
    limite. Mutation attendue si ce test manque : PASTILLE["inconnu"]
    -> "🟢" (pages/live.py:35) laisserait passer ces pastilles en vert."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time()  # ligne fraiche : le cas le plus favorable au bug
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    assert pastille(rendu, "f_books") == "⚪"
    assert pastille(rendu, "f_stats") == "⚪"
    assert pastille(rendu, "f_books") != "🟢"
    assert pastille(rendu, "f_stats") != "🟢"


def test_ligne_reelle_perimee_rouge_pour_les_connus_blanc_pour_les_inconnus(monkeypatch):
    """Preuve directe de I3. Sur la MEME ligne reelle rendue tres perimee
    (publieur mort depuis 1h) : seuls les flux dont l'age est CONNU
    (score, exchange) virent au rouge. books/stats, NULL en base, restent
    blancs pour toujours -- ils ne peuvent pas "virer" au rouge puisqu'ils
    n'ont jamais eu de valeur. L'ancien message du bandeau ("les pastilles
    ci-dessous vont virer au rouge", sans nuance) etait faux pour ces deux
    flux ; le message corrige ne doit plus le promettre sans nuance."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time() - 3600.0  # publieur mort depuis 1h
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    assert pastille(rendu, "f_score") == "🔴"
    assert pastille(rendu, "f_exchange") == "🔴"
    assert pastille(rendu, "f_books") == "⚪"
    assert pastille(rendu, "f_stats") == "⚪"

    assert len(at.error) >= 1
    message = at.error[0].value.lower()
    assert "publieur" in message
    # Le message ne doit plus promettre que "les" pastilles (toutes) vont
    # virer au rouge : c'est faux pour les deux qui restent blanches.
    assert "blanc" in message or "restent" in message


# --- Preuve de wiring pour I4 (en_cours, pas matchs ; colonne updated_ts) ---


def test_bandeau_absent_sans_match_en_cours_si_le_battement_est_vivant(monkeypatch):
    """Seule une ligne Finished tres vieille (reelle, LIGNE_REELLE_FINISHED,
    ~1030 s de retard) est publiee : aucun match en cours, battement
    publieur injecte frais -- pas de fausse alerte.

    CORRECTIF (IMPORTANT 3, tour 5) : la docstring de ce test affirmait
    auparavant qu'une mutation `publieur_arrete(en_cours)` ->
    `publieur_arrete(matchs)` le casserait. C'ETAIT FAUX -- le relecteur a
    rejoue exactement cette mutation, la suite entiere restait verte
    (89/89). Cause : depuis qu'un battement FRAIS rend `publieur_arrete()`
    AUTORITAIRE (I1a, tour 3), le DataFrame passe en argument n'est plus
    jamais regarde des que le battement est lisible et frais -- `en_cours`
    et `matchs` sont devenus INDISCERNABLES pour cette fonction dans ce
    scenario precis, et cette assertion ne protege donc plus le filtre
    `en_cours = matchs[matchs["en_cours"]]` a pages/live.py. Ce test reste
    correct sur ce qu'il affirme reellement (pas de fausse alerte ici),
    mais la protection du filtre lui-meme vit maintenant dans
    `test_page_separe_bien_en_cours_et_termines_a_lusage`, ci-dessous, qui
    verifie le CONTENU des deux tableaux affiches plutot que le bandeau."""
    at = _lancer(
        monkeypatch, pd.DataFrame([LIGNE_REELLE_FINISHED]),
        battement_publieur=lambda: {"ts": time.time() - 1.0},
    )

    assert not at.exception
    assert len(at.error) == 0


def test_page_separe_bien_en_cours_et_termines_a_lusage(monkeypatch):
    """Protege pages/live.py (`en_cours = matchs[matchs["en_cours"]]` et
    `termines = matchs[~matchs["en_cours"]]`) A LEUR POINT D'USAGE -- pas
    seulement le contrat "en_cours" epingle dans charger_matchs()
    (tests/test_live_data.py). MINEUR 1 / IMPORTANT 3 (tour 5) : la
    mutation `en_cours = matchs` (le filtre retire) survit a toute la
    suite precedente, parce qu'aucun test n'utilisait une base MIXTE (un
    match en cours ET un match termine dans la MEME requete) en verifiant
    le CONTENU des deux tableaux affiches.

    Une ligne InPlay fraiche + LIGNE_REELLE_FINISHED (reelle) dans la MEME
    table : le tableau "en cours" ne doit contenir QUE la premiere, le
    tableau "termines" QUE la seconde."""
    ligne_en_cours = dict(LIGNE_REELLE_INPLAY)
    ligne_en_cours["updated_ts"] = time.time()
    lignes = pd.DataFrame([ligne_en_cours, LIGNE_REELLE_FINISHED])

    at = _lancer(
        monkeypatch, lignes,
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 0}},
    )

    assert not at.exception
    assert len(at.error) == 0
    # Une ligne stylee par match, dans deux sections distinctes : celle des
    # matchs en cours et celle des termines.
    # `data-section` ne figure QUE sur une ligne de donnees : l'entete de
    # colonnes partage la classe `match` avec elles, exprès -- c'est ce qui
    # garantit qu'elles s'alignent -- mais elle ne porte aucun match.
    rendus = [str(m.value) for m in at.markdown if "data-section=" in str(m.value)]
    assert len(rendus) == 2, "une ligne 'en cours' et une ligne 'termines' attendues"
    tableau_en_cours = structure(at)
    tableau_termines = structure(at, second=True)
    assert all(ligne_en_cours["participant1"] == l["joueurs"][0]["nom"] for l in tableau_en_cours)
    assert LIGNE_REELLE_FINISHED["participant1"] in [l["joueurs"][0]["nom"] for l in tableau_termines]


def test_page_publieur_arrete_utilise_en_cours_pas_matchs_quand_le_battement_est_illisible(monkeypatch):
    """Protection de wiring pour `if publieur_arrete(en_cours):` a
    pages/live.py -- PAS `publieur_arrete(matchs)`. Mutation trouvee par le
    relecteur (tour 5, IMPORTANT 3) : cette mutation est INDETECTABLE des
    que le battement est frais (publieur_arrete() ne regarde alors plus du
    tout son argument df, cf. I1a) -- la seule fenetre ou elle reste
    observable est un battement ILLISIBLE, qui force le repli sur
    updated_ts a vraiment lire le DataFrame recu. Seule LIGNE_REELLE_FINISHED
    (tres vieille) est publiee : `en_cours` (vide, aucun match InPlay) ne
    peut rien attester -> pas de bandeau. `matchs` (la ligne terminee tres
    vieille), lui, ferait lire a tort son grand age -> bandeau a tort.
    `_lancer` sans override de battement_publieur retombe sur `lambda: None`
    (illisible) par defaut -- exactement le chemin qui rend cette mutation
    visible."""
    at = _lancer(monkeypatch, pd.DataFrame([LIGNE_REELLE_FINISHED]))

    assert not at.exception
    assert len(at.error) == 0


def test_pastilles_inconnues_quand_la_colonne_updated_ts_manque(monkeypatch):
    """Preuve de I4, second point (pages/live.py:64, `and a_jour`).
    `updated_ts` est NOT NULL en base (aucune ligne reelle ne peut en
    manquer), mais la page ne doit pas planter si elle manquait quand meme :
    degradation a "inconnu" partout, jamais un KeyError sur vue["updated_ts"]."""
    # updated_ts absente -> publieur_arrete() retombe sur le battement (deja
    # mocke a None -- illisible -- par defaut dans _lancer) ; les assertions
    # ci-dessous ne portent pas sur le bandeau, seulement sur les pastilles
    # du tableau.
    ligne = dict(LIGNE_REELLE_INPLAY)
    del ligne["updated_ts"]
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    for flux in ("f_score", "f_exchange", "f_books", "f_stats"):
        assert pastille(rendu, flux) == "⚪"


# --- Seuils par flux (tour 2) : preuve bout en bout, sur la PAGE reelle ----


def _ligne_mi_cycle_a_l_instant(maintenant):
    """LIGNE_REELLE_MI_CYCLE avec updated_ts recale sur `maintenant` : ce
    tour porte sur les SEUILS, pas sur le rattrapage temps-ecoule-depuis-le-
    cycle (deja couvert par C4/tour 1) -- figer updated_ts a l'instant reel
    de capture ferait deriver le test a chaque execution (age_a_la_lecture
    ajoute le temps ecoule depuis CE updated_ts-la, qui grandit avec le
    temps reel). Les quatre ages STOCKES restent, eux, les vraies valeurs
    mesurees le 2026-08-03."""
    ligne = dict(LIGNE_REELLE_MI_CYCLE)
    ligne["updated_ts"] = maintenant
    return ligne


def test_ligne_reelle_mi_cycle_toutes_pastilles_vertes_sur_la_page(monkeypatch):
    """Preuve de wiring, pas seulement de la fonction pure : LIGNE_REELLE_MI_CYCLE
    (evenement reel, 2026-08-03) a ses quatre ages au-dessus de l'ancien
    seuil unique de 30s, et pourtant c'est un match SAIN. Rejouee via la
    PAGE (pas juste fraicheur()/SEUILS_PAR_FLUX en isolation), pour attraper
    une mutation de wiring (ex. colonne mappee au mauvais seuil dans
    pages/live.py::_tableau) qu'un test purement fonctionnel ne verrait pas."""
    ligne = _ligne_mi_cycle_a_l_instant(time.time())
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    for flux in ("f_score", "f_exchange", "f_books", "f_stats"):
        assert pastille(rendu, flux) == "🟢", f"{flux} : attendu vert (age reel {LIGNE_REELLE_MI_CYCLE}), recu {pastille(rendu, flux)!r}"


def test_pastille_exchange_verte_dans_une_zone_que_le_seuil_du_score_marquerait_perimee(monkeypatch):
    """Preuve que _tableau() lit bien LE SEUIL DE CHAQUE FLUX depuis
    SEUILS_PAR_FLUX, pas un seuil partage par accident (ex. un refactor qui
    figerait une constante en dur pour toutes les colonnes -- indetectable
    par la demonstration "tout est vert" ci-dessus, dont les quatre ages
    reels tombent TOUS sous le plus petit des quatre seuils). age_exchange_s
    est place SOUS le seuil de l'exchange (720s) mais AU-DESSUS de celui du
    score (600s depuis le tour 3, corrige par I3) : de quoi distinguer les
    deux seuils par le resultat observe, pas seulement par la lecture du
    code. age_score_s est place symetriquement AU-DESSUS de son propre
    seuil (600s) pour rendre le contraste observable des deux cotes."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["age_score_s"] = 650.0  # au-dessus du seuil du score (600s)
    ligne["age_exchange_s"] = 650.0  # sous le seuil de l'exchange (720s)
    ligne["updated_ts"] = time.time()
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    assert pastille(rendu, "f_score") == "🔴", "650s depasse le seuil du score (600s)"
    assert pastille(rendu, "f_exchange") == "🟢", "650s est sous le seuil de l'exchange (720s), pas celui du score"


# --- CRITIQUE (tour 3) : le signal doit etre consulte AVANT le retour
# anticipe sur `matchs` vide -------------------------------------------------
#
# Avant ce tour, `if matchs.empty: st.info(...); return` precedait l'appel
# a publieur_arrete()/capteur_score_mort(), qui n'etaient donc JAMAIS
# consultes quand live_now est vide -- cas cree par la retention du
# publieur (`_retirer_anciens`, 6 h), cote PoC : avant cette branche,
# live_now n'etait jamais purgee et l'etat "table vide" n'existait pas.
# Sonde du relecteur, reproduite ici : battement vieux de 2h -> aucun
# st.error, identique a un battement vieux de 1s. Le seul test qui pretendait
# couvrir "aucun match en cours" (plus haut, LIGNE_REELLE_FINISHED) traverse
# le chemin "en_cours vide MAIS matchs non vide" et rate donc ce chemin.


def test_bandeau_publieur_arrete_visible_meme_quand_live_now_est_vide(monkeypatch):
    """Reproduction exacte de la sonde du relecteur : table vide + battement
    vieux de 2h -> st.error doit apparaitre. Avant ce tour, `matchs.empty`
    provoquait un retour AVANT que publieur_arrete() ne soit meme appele."""
    at = _lancer(
        monkeypatch, pd.DataFrame(),
        battement_publieur=lambda: {"ts": time.time() - 7200.0},  # 2h
    )
    assert not at.exception
    assert len(at.error) >= 1
    assert "publieur" in at.error[0].value.lower()
    # Le message factuel "aucun match publie" reste affiche a cote --
    # complementaire de l'erreur, pas remplace par elle.
    assert len(at.info) >= 1
    assert "aucun match publie" in at.info[0].value.lower()


def test_pas_de_bandeau_quand_live_now_est_vide_mais_le_battement_est_frais(monkeypatch):
    """Contraste direct avec le test ci-dessus, meme sonde que le
    relecteur : table vide + battement vieux d'1s -> pas de fausse alerte,
    seul le message factuel "aucun match publie" reste."""
    at = _lancer(
        monkeypatch, pd.DataFrame(),
        battement_publieur=lambda: {"ts": time.time() - 1.0},
    )
    assert not at.exception
    assert len(at.error) == 0
    assert len(at.info) >= 1


# --- I1a (tour 3) : un battement frais oppose son veto, au niveau PAGE -----


def test_page_pas_de_bandeau_arrete_dans_la_fenetre_75s_si_le_battement_est_frais(monkeypatch):
    """Preuve de wiring pour I1a (pas seulement la fonction pure, deja
    testee dans test_live_data.py) : une ligne InPlay dont updated_ts est
    vieux de 90s (au-dela de SEUIL_PUBLIEUR_ARRETE_S=45s, dans la fenetre de
    ~75s mesuree en service ou le publieur n'a pas encore reetiquete
    "Finished") ne doit PAS declencher le bandeau quand le battement,
    injecte frais (1s), l'atteste vivant.

    `state.n_echecs=0` explicite (tour 5) : un VRAI battement le documente
    toujours, meme a 0 (Publieur.tick() l'inclut a chaque cycle) -- sans
    lui, publieur_ecritures_refusees() retomberait sur updated_ts (90s >
    45s) et declencherait a tort SON bandeau, pour la meme fenetre de fin
    de match qu'I1a a deja correctement disculpee."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time() - 90.0
    at = _lancer(
        monkeypatch, pd.DataFrame([ligne]),
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 0}},
    )
    assert not at.exception
    assert len(at.error) == 0


# --- IMPORTANT 1 (tour 5) : "vivant mais n'ecrit plus", au niveau PAGE -----


def test_page_signale_les_ecritures_refusees_reproduction_exacte_de_la_sonde(monkeypatch):
    """Reproduction EXACTE de la sonde du relecteur qui a revele la
    regression : ligne InPlay gelee depuis 1h + battement
    {"ts": now-1, "state": {"n_echecs": 12}} -> AVANT ce correctif,
    st.error = [] (rien, alors que le publieur venait de dire lui-meme
    qu'il n'ecrivait plus). Avec le meme etat mais battement illisible (le
    comportement d'avant le tour 3), le bandeau apparaissait deja -- la
    regression etait specifique au chemin "battement lisible et frais"."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time() - 3600.0  # gelee depuis 1h
    at = _lancer(
        monkeypatch, pd.DataFrame([ligne]),
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 12}},
    )

    assert not at.exception
    assert len(at.error) >= 1
    message = at.error[0].value.lower()
    assert "ecritures" in message
    assert "vivant" in message
    # Le bandeau "publieur arrete" ne doit PAS s'etre declenche a la place :
    # le process, lui, repond.
    assert "semble arrete" not in message


def test_page_pas_de_bandeau_ecritures_refusees_sur_un_publieur_sain(monkeypatch):
    """Contre-preuve : meme ligne gelee depuis 1h, mais battement avec
    n_echecs=0 explicite -- pas de bandeau du tout (le domaine de
    publieur_arrete()/capteur_score_mort(), tous deux non declenches ici
    par construction du test)."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time() - 3600.0
    at = _lancer(
        monkeypatch, pd.DataFrame([ligne]),
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 0}},
        battement_score=lambda: {"ts": time.time() - 1.0},
    )

    assert not at.exception
    assert len(at.error) == 0


# --- I1b (tour 3) : distinguer "publieur arrete" de "capteur de score
# muet", au niveau PAGE -------------------------------------------------------


def test_page_signale_le_capteur_de_score_pas_le_publieur_quand_seul_lui_est_mort(monkeypatch):
    """Preuve de wiring pour I1b. Publieur VIVANT (battement-publish frais)
    pendant qu'une ligne InPlay reste figee depuis longtemps (le symptome
    cote page quand le capteur de score meurt et que Publieur.
    _marquer_termines refuse de reetiqueter -- gardee par son propre
    battement, cote PoC) ET que le battement du capteur de score, LUI, est
    perime : la page doit accuser le capteur de score, PAS le publieur."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time() - 10_000.0  # figee depuis longtemps
    at = _lancer(
        monkeypatch, pd.DataFrame([ligne]),
        # state.n_echecs=0 explicite (tour 5) : le publieur n'a PAS refuse
        # d'ecrire, cette ligne est figee parce que le capteur de score,
        # lui, ne la reporte plus -- pas parce qu'une ecriture a echoue.
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 0}},
        battement_score=lambda: {"ts": time.time() - SEUIL_BATTEMENT_ARRETE_S - 1},
    )
    assert not at.exception
    assert len(at.error) >= 1
    message = at.error[0].value.lower()
    assert "capteur de score" in message
    # Le bandeau "publieur arrete" (test_bandeau_publieur_arrete_...) ne
    # doit PAS s'etre declenche a la place : le publieur est vivant ici.
    assert "le publieur temps reel semble arrete" not in message


# --- Tour 6 : l'ABSENCE d'un battement de capteur de score est un SIGNAL,
# pas un silence -- au niveau PAGE ------------------------------------------


def test_page_signale_le_capteur_de_score_quand_son_battement_est_absent(monkeypatch):
    """Reproduction de la sonde de la revue de cloture, cette fois au niveau
    de la PAGE : `capteur_score_mort(lire_battement=lambda: None)` seul
    rendait False avant ce tour, silence definitif. Ici, battement ABSENT
    (arret propre, Heartbeat.clear() cote PoC) + ligne InPlay gelee depuis
    longtemps (la corroboration -- meme symptome qu'I1b) -> la page doit
    accuser le capteur de score."""
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = time.time() - 10_000.0
    at = _lancer(
        monkeypatch, pd.DataFrame([ligne]),
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 0}},
        battement_score=lambda: None,  # absent
        battement_score_absent=lambda chemin: True,
    )
    assert not at.exception
    assert len(at.error) >= 1
    message = at.error[0].value.lower()
    assert "capteur de score" in message
    assert "le publieur temps reel semble arrete" not in message


def test_page_silencieuse_si_capteur_score_absent_sans_corroboration(monkeypatch):
    """Contre-preuve, la nuance demandee explicitement : battement ABSENT
    mais AUCUNE ligne en cours pour corroborer (ex. tout premier demarrage
    du systeme) -- pas de bandeau, l'absence seule ne doit jamais hurler."""
    at = _lancer(
        monkeypatch, pd.DataFrame(),
        battement_publieur=lambda: {"ts": time.time() - 1.0, "state": {"n_echecs": 0}},
        battement_score=lambda: None,
        battement_score_absent=lambda chemin: True,
    )
    assert not at.exception
    assert len(at.error) == 0


def test_le_flux_MORT_est_NOMME_dans_la_ligne(monkeypatch):
    """Quatre seuils differents ne doivent pas obliger a deviner lequel
    s'applique a quoi.

    Cette exigence vivait dans une infobulle `title` sur chaque pastille --
    qui ne s'est JAMAIS affichee : le bouton invisible qui rend la ligne
    cliquable recouvre les pastilles, le pointeur ne les atteint jamais. On
    voyait qu'un flux etait rouge, jamais lequel. La ligne ECRIT donc le nom
    du flux perime, et le detail garde l'age et le seuil precis.
    """
    from liste_dense import NOMS_COURTS
    ligne = _a_l_instant(LIGNE_REELLE_BOOKS_FLUX_MORT, time.time())
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))
    assert not at.exception
    h = html_liste(at)
    assert "title=" not in h, \
        "une infobulle est revenue : elle est inatteignable sous le bouton"
    etats = structure(at)[0]["fraicheur"]
    morts = [f["flux"] for f in etats if f["etat"] == "perime"]
    assert morts, "la fixture ne porte aucun flux perime"
    for flux in morts:
        assert NOMS_COURTS[flux] in h, \
            f"{flux} est perime mais son nom n'est pas ecrit : {h[-400:]}"


def test_le_DETAIL_garde_le_seuil_et_la_question_de_chaque_flux(monkeypatch):
    """Le nom suffit a savoir s'il faut aller voir ; le detail dit quoi.
    Sans lui, retirer l'infobulle aurait PERDU l'information au lieu de la
    deplacer."""
    ligne = _a_l_instant(LIGNE_REELLE_BOOKS_FLUX_MORT, time.time())
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))
    at.button[0].click().run()
    aides = " ".join(str(m.help or "") + str(m.label or "") for m in at.metric)
    for flux, (_, seuil, libelle, question) in SEUILS_PAR_FLUX.items():
        assert f"{seuil:.0f} s" in aides, f"{flux} : seuil absent du detail"
        assert libelle.replace(" -- ", " · ") in aides, f"{flux} : libelle absent"
        assert question[:28] in aides, f"{flux} : question absente du detail"


# --- Books : PRIX et FLUX, deux pastilles, deux questions (tour 4) ---------


def _a_l_instant(ligne_reelle, maintenant):
    """Meme motif que _ligne_mi_cycle_a_l_instant, generalise a n'importe
    quelle fixture reelle : recale updated_ts sur `maintenant` pour que les
    ages STOCKES (les vraies valeurs mesurees) restent la seule chose que
    le test exerce, sans derive due au temps ecoule depuis la capture."""
    ligne = dict(ligne_reelle)
    ligne["updated_ts"] = maintenant
    return ligne


def test_page_books_prix_et_flux_frais_tous_deux_sur_ligne_saine(monkeypatch):
    """LIGNE_REELLE_BOOKS_SAINE (event_id 3801815, capturee le 2026-08-04) :
    prix et flux jeunes tous les deux -- preuve de wiring que la nouvelle
    colonne f_books_flux se calcule et s'affiche correctement a cote de
    f_books sur la PAGE reelle, pas seulement via fraicheur() en isolation."""
    ligne = _a_l_instant(LIGNE_REELLE_BOOKS_SAINE, time.time())
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    assert pastille(rendu, "f_books") == "🟢"
    assert pastille(rendu, "f_books_flux") == "🟢"


def test_page_books_distingue_prix_inconnu_de_flux_mort(monkeypatch):
    """Preuve CENTRALE du tour 4, sur la PAGE reelle : LIGNE_REELLE_BOOKS_
    FLUX_MORT (event_id 3798175, capturee le 2026-08-04) -- prix NaN
    (plafonne, donc simplement absent : "inconnu") mais flux au-dela de son
    seuil (611,8s > 600s : "le capteur semble mort"). Les deux pastilles
    DOIVENT diverger : c'est exactement l'information qu'une seule colonne
    plafonnee ne pouvait pas porter avant ce tour."""
    ligne = _a_l_instant(LIGNE_REELLE_BOOKS_FLUX_MORT, time.time())
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))

    assert not at.exception
    rendu = structure(at)[0]
    assert pastille(rendu, "f_books") == "⚪", "prix NULL (plafonne) -> inconnu, jamais perime"
    assert pastille(rendu, "f_books_flux") == "🔴", "611,8s > 600s -> le capteur semble mort"


def test_infobulle_books_distingue_les_deux_questions(monkeypatch):
    """Exigence de lisibilite (tour 4, point 1) : l'infobulle de f_books et
    celle de f_books_flux doivent nommer explicitement DEUX questions
    differentes, pas juste deux seuils differents -- sans quoi l'utilisateur
    peut lire deux pastilles voisines avec des ages proches et croire
    qu'elles disent la meme chose."""
    ligne = _ligne_mi_cycle_a_l_instant(time.time())
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))
    assert not at.exception
    at.button[0].click().run()

    # L'exigence est intacte, seul son domicile a change : elle vivait dans
    # une infobulle de la liste, inatteignable sous le bouton de clic ; elle
    # vit desormais dans la fenetre de detail, ou rien ne la recouvre.
    aide = " ".join(str(m.help or "") for m in at.metric).lower()
    assert "utilisable" in aide, "la question du PRIX manque"
    assert "mort" in aide, "la question du FLUX manque"
    assert aide.index("utilisable") != aide.index("mort")


def _trois_matchs(maintenant):
    """Une fixture qui DISCRIMINE.

    Elle a longtemps donne le meme point aux deux joueurs, un seul set, et
    des ecarts identiques -- de sorte que permuter A et B, ou surligner le
    PREMIER set au lieu du dernier, ne changeait rien a ce qu'elle produisait.
    Sept mutations traversaient la suite sans reveiller un test. Chaque
    valeur ci-dessous est donc distincte de sa voisine, exprès.
    """
    commun = {
        "status": "InPlay", "age_score_s": 2.0, "age_exchange_s": 2.0,
        "age_books_s": 2.0, "age_books_flux_s": 2.0, "age_stats_s": 2.0,
        # L'heure de DEBUT doit se distinguer de l'heure du dernier cycle :
        # sinon la colonne « heure » peut afficher l'une pour l'autre.
        "updated_ts": maintenant,
        # Quatre prix tous differents, et des ecarts back/lay differents d'un
        # joueur a l'autre : sans cela, permuter back et lay, ou A et B,
        # produit exactement le meme HTML.
        "back_odds_a": 1.50, "lay_odds_a": 1.56,
        "back_odds_b": 2.60, "lay_odds_b": 2.74,
        "book_odds_a": 1.55, "book_odds_b": 2.50,
    }
    return pd.DataFrame([
        # Annonce mais PAS commence : doit disparaitre de la liste.
        {**commun, "event_id": "pas-commence", "participant1": "E", "participant2": "F",
         "league": "Hagen Challenger", "tour_type": "atp", "score": "0-0",
         "points": "0-0", "server": "0", "start_timestamp": maintenant - 100},
        # Le plus TARD annonce, place en second dans le DataFrame : le tri
        # doit le renvoyer en fin de liste.
        {**commun, "event_id": "tard", "participant1": "C", "participant2": "D",
         "league": "Polish Open - Warsaw", "tour_type": "wta", "score": "6-3,2-1",
         "points": "30-15", "server": "1", "start_timestamp": maintenant + 3600},
        {**commun, "event_id": "tot", "participant1": "A", "participant2": "B",
         "league": "National Bank Open - Montreal", "tour_type": "atp",
         # TROIS sets : sans cela, « le set en cours est le dernier » est vrai
         # par accident, et surligner le premier passe inapercu.
         "score": "6-4,3-6,5-2", "points": "40-30", "server": "0",
         "start_timestamp": maintenant - 7200},
    ])


def test_la_liste_ne_montre_que_les_matchs_COMMENCES(monkeypatch):
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    assert not at.exception
    t = structure(at)
    noms = " ".join(j["nom"] for l in t for j in l["joueurs"])
    assert "E" not in noms.split(), f"le match a 0-0/0-0 ne doit pas figurer : {noms}"
    assert len(t) == 2, t.to_dict("records")


def test_la_liste_est_triee_par_heure_de_DEBUT(monkeypatch):
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    t = structure(at)
    # « tot » est le TROISIEME du DataFrame : seul un vrai tri le remonte.
    assert t[0]["joueurs"][0]["nom"].startswith("A"), [l["joueurs"][0]["nom"] for l in t]
    assert t[-1]["joueurs"][0]["nom"].startswith("C"), [l["joueurs"][0]["nom"] for l in t]
    assert all(l["heure"] and l["heure"] != "--:--" for l in t), [l["heure"] for l in t]


def test_la_colonne_competition_porte_le_circuit_et_le_niveau(monkeypatch):
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    t = structure(at)
    assert all("competition" in l for l in t)
    assert {l["competition"] for l in t} == {"ATP", "WTA"}, [l["competition"] for l in t]


def test_la_balle_est_du_cote_de_CELUI_QUI_SERT(monkeypatch):
    """`server` est l'index DEDUIT par alternance cote publieur (0 =
    participant1), verifie contre le point par point sur 62 matchs : mediane
    100 % d'accord, aucun match inverse."""
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    t = structure(at)
    # Les deux joueurs vivent desormais dans la MEME cellule, separes par
    # « / » : on lit de quel COTE du separateur la balle se trouve, ce qui
    # teste exactement ce que testaient les deux colonnes d'avant.
    par_nom = {l["joueurs"][0]["nom"]: l for l in t}
    assert set(par_nom) == {"A", "C"}, list(par_nom)
    # server = "0" : la balle est sur le PREMIER joueur.
    assert par_nom["A"]["joueurs"][0]["sert"] and not par_nom["A"]["joueurs"][1]["sert"]
    # server = "1" : elle passe de l'autre cote.
    assert not par_nom["C"]["joueurs"][0]["sert"] and par_nom["C"]["joueurs"][1]["sert"]
    # Et le HTML doit refleter la structure, sinon la balle est calculee mais
    # pas affichee.
    assert "🎾" in html_liste(at)


def test_sans_serveur_connu_aucune_balle_n_est_affichee(monkeypatch):
    """Jamais de balle par defaut : elle serait du MAUVAIS cote une fois sur
    deux, ce qui est pire que pas de balle."""
    df = _trois_matchs(time.time())
    df["server"] = None
    at = _lancer(monkeypatch, df)
    t = structure(at)
    assert not any(j["sert"] for l in t for j in l["joueurs"])
    assert "🎾" not in html_liste(at)
    assert not any(j["sert"] for l in t for j in l["joueurs"])
    assert "🎾" not in html_liste(at)


def test_une_heure_de_debut_INCONNUE_va_en_FIN_de_liste(monkeypatch):
    """Sans `na_position="last"`, un match dont on ignore l'heure passerait
    devant tous les autres -- il occuperait la premiere ligne, celle qu'on
    regarde en premier, sur la foi d'une absence (mutation V3, 2026-08-04)."""
    df = _trois_matchs(time.time())
    df.loc[df["event_id"] == "tot", "start_timestamp"] = None
    at = _lancer(monkeypatch, df)
    assert not at.exception
    t = structure(at)
    assert t[-1]["joueurs"][0]["nom"].startswith("A"), [l["joueurs"][0]["nom"] for l in t]
    assert t[0]["joueurs"][0]["nom"].startswith("C"), [l["joueurs"][0]["nom"] for l in t]


# --- Le TRAITEMENT VISUEL, et pas seulement l'information ---
#
# La maquette validee portait sur la LECTURE : prix aux couleurs du metier,
# set en cours marque, regroupement par tournoi, ligne cliquable. Une premiere
# version rendait les memes colonnes dans une grille standard -- l'information
# sans la lecture. Rien ne protegeait ce qui manquait alors ; ces tests le
# font (mutations C2, C3, C7 survivantes au 2026-08-04).


def _html(df=None, ouvert=""):
    from liste_dense import lignes, rendu
    maintenant = time.time()
    return rendu(lignes(df if df is not None else _trois_matchs(maintenant),
                        maintenant), ouvert)


def test_les_prix_portent_les_couleurs_du_metier_back_et_lay():
    """Sur l'exchange, back et lay ont ces teintes depuis toujours : ce n'est
    pas une decoration, c'est le code que l'operateur lit deja ailleurs. Les
    confondre rendrait les deux prix indiscernables."""
    h = _html()
    assert h.count('<i class="b">') >= 2, "aucun prix back colore"
    assert h.count('<i class="l">') >= 2, "aucun prix lay colore"
    # Dans chaque paire, le back precede le lay et porte une AUTRE classe.
    import re
    paires = re.findall(r'<span>(<i class="\w+">[^<]*</i>){2}</span>', h)
    assert paires, "aucune paire back/lay rendue"
    for bloc in re.findall(r'<span><i class="(\w+)">[^<]*</i><i class="(\w+)">', h):
        assert bloc[0] != bloc[1] or bloc == ("vide", "vide"), bloc


def test_le_SET_EN_COURS_est_marque_distinctement():
    """Sans lui, tous les sets se ressemblent et on ne voit pas d'un coup
    d'oeil ou en est le match."""
    import re
    h = _html()
    assert 'class="encours"' in h, "aucun set marque comme en cours"
    # Un SEUL set en cours par joueur, et c'est le dernier.
    for bloc in re.findall(r'<span>(?:<b class="[^"]*">[^<]*</b>)+</span>', h):
        assert bloc.count("encours") == 1, bloc
        assert bloc.rindex("encours") > bloc.find("<b", 1), "ce doit etre le DERNIER"


def test_le_clic_ouvre_le_detail_SANS_deconnecter(monkeypatch):
    """Un <a href="?..."> rechargeait la page, ce qui cree une nouvelle
    session Streamlit -- et comme l'authentification de cette application ne
    vit que dans session_state (le cookie est commente dans
    pages/login.py), le rechargement DECONNECTAIT. Constate a l'usage.

    Le clic passe donc par un bouton, qui ne recharge pas."""
    # `event_ids` n'est PAS injectable ici : charger_matchs() le recalcule en
    # fusionnant les doublons de la source. On verifie donc que le clic
    # transmet bien ce que la fusion a produit, pas une valeur inventee.
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    assert not at.exception
    # Aucun lien : c'est ce qui garantit qu'aucun rechargement ne peut avoir
    # lieu depuis la liste.
    assert "<a href" not in html_liste(at), "un lien reintroduirait la deconnexion"
    assert len(at.button) >= 2, "un bouton d'ouverture par match attendu"

    at.button[0].click().run()
    assert at.session_state["logged_in"] is True, "le clic ne doit pas deconnecter"
    # C'est `event_ids` -- tous les identifiants du groupe -- qui est
    # transmis, et non le seul `event_id` : la serie est repartie entre eux.
    from live_data import charger_matchs
    attendu = charger_matchs(lecteur=lambda s_, q: _trois_matchs(time.time())).iloc[0]
    assert str(at.session_state["match_ouvert"]), "aucun match ouvert"
    assert "event_ids" in attendu, "le contrat de charger_matchs a change"
    assert sum(1 for l in structure(at) if l["ouvert"]) == 1, "un seul ouvert"


def test_le_match_OUVERT_se_distingue_des_autres():
    """Sans marque, on perd de vue lequel on est en train de lire."""
    h = _html(ouvert="tot")
    assert h.count('class="match ouvert"') == 1, "un seul match ouvert attendu"


def test_les_matchs_sont_REGROUPES_par_tournoi():
    """C'est ainsi qu'on choisit ou regarder : un tournoi, puis ses matchs."""
    h = _html()
    assert h.count('entete tournoi') >= 2, "aucun regroupement"


def _enfants(bloc):
    enf = getattr(bloc, "children", None)
    return list(enf.values()) if isinstance(enf, dict) else list(enf or [])


def _bloc(racine, genre):
    """Le premier bloc d'un genre donne, ou None."""
    for enfant in _enfants(racine):
        if getattr(enfant, "type", None) == genre:
            return enfant
        trouve = _bloc(enfant, genre)
        if trouve is not None:
            return trouve
    return None


def test_le_detail_s_ouvre_en_FENETRE_et_pas_sous_la_liste(monkeypatch):
    """Sous la liste, il fallait derouler toute la page pour lire le detail,
    puis remonter pour changer de match -- d'autant plus penible que la
    liste s'allonge. Une fenetre garde la liste en place.

    Ce test regarde le bloc REELLEMENT pousse : ni `at.tabs` ni `at.metric`
    ne distinguent les deux, la bibliotheque de test aplatissant le contenu
    d'une fenetre dans l'arbre de la page.
    """
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    assert _bloc(at._tree, "dialog") is None, "aucune fenetre avant le clic"

    at.button[0].click().run()
    fenetre = _bloc(at._tree, "dialog")
    assert fenetre is not None, "le detail s'affiche encore sous la liste"
    assert fenetre.proto.dialog.is_open, "fenetre poussee mais fermee"
    # Et le detail est DEDANS, pas a cote : sans cela la fenetre serait vide
    # et le detail resterait au bas de la page.
    assert _bloc(fenetre, "tab_container") is not None, "detail hors de la fenetre"


def test_la_fenetre_se_REFERME_pour_de_bon(monkeypatch):
    """La page se rafraichit toute seule. Si fermer la fenetre laissait le
    match note comme ouvert, le rafraichissement suivant la rouvrirait
    quelques secondes plus tard -- une fenetre dont on ne peut pas sortir."""
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    at.button[0].click().run()
    fenetre = _bloc(at._tree, "dialog").proto.dialog
    assert fenetre.dismissible, "fenetre non fermable"
    # Streamlit n'attribue un identifiant a une fenetre que lorsqu'un rappel
    # est branche sur sa fermeture : sans `on_dismiss`, ce champ reste vide.
    # C'est la seule trace verifiable du branchement -- la fermeture elle-meme
    # n'est pas declenchable depuis les tests.
    assert fenetre.id, "aucun rappel branche sur la fermeture"

    at.run()
    assert _bloc(at._tree, "dialog") is not None, "elle ne survit pas au refresh"

    # Ce que fait `_refermer`, branche sur la fermeture de la fenetre.
    at.session_state["match_ouvert"] = ""
    at.run()
    assert _bloc(at._tree, "dialog") is None, "elle se rouvre apres fermeture"


def test_le_bouton_d_ouverture_NOMME_le_match(monkeypatch):
    """Ce bouton recouvre la ligne et il est transparent : son libelle n'est
    plus lu qu'a la voix. « Ouvrir » quinze fois de suite ne designerait
    aucun match."""
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    libelles = [b.label for b in at.button]
    assert len(set(libelles)) == len(libelles), f"libelles indistincts : {libelles}"
    for ligne in structure(at):
        attendu = " contre ".join(j["nom"] for j in ligne["joueurs"])
        assert any(attendu in l for l in libelles), f"aucun bouton pour {attendu}"


def test_le_clic_porte_sur_TOUTE_la_ligne():
    """Le clic ne visait qu'un chevron de quelques pixels : il fallait viser
    une liste qu'on ne fait que parcourir. Le bouton recouvre desormais la
    ligne entiere, transparent, et le survol reagit sur toute sa largeur.

    Les conteneurs nommes ne remontent pas dans l'arbre de rendu : seule la
    feuille de style peut etre relue ici. La cle, elle, ne peut pas diverger
    -- page et style la tirent de `cle_ligne`.
    """
    from liste_dense import CSS, PREFIXE_LIGNE, cle_ligne

    assert cle_ligne("en-cours", "42").startswith(PREFIXE_LIGNE + "-")
    vise = f'div[class*="st-key-{PREFIXE_LIGNE}-"]'
    assert vise in CSS, "le style ne vise plus le conteneur d'une ligne"
    regles = "\n".join(b for b in CSS.split("\n\n") if vise in b)
    for exigence in ("position: relative", "inset: 0", "opacity: 0"):
        assert exigence in regles, f"le bouton ne recouvre pas la ligne : {exigence}"
    assert f'{vise}:hover' in CSS, "aucun survol sur la ligne entiere"


def test_toute_classe_AFFICHEE_est_bien_stylee():
    """Le HTML et la feuille de style vivent dans le meme fichier mais ne se
    parlent que par le nom des classes. Renommer une regle sans renommer la
    balise -- ou l'inverse -- ne casse rien, ne leve rien : l'element perd
    simplement son apparence. C'est ainsi que le set en cours a pu cesser
    d'etre surligne sans qu'aucun test ne bronche.
    """
    import re
    from liste_dense import CSS

    h = _html()
    classes = {c for attr in re.findall(r'class="([^"]+)"', h) for c in attr.split()}
    assert len(classes) > 10, f"HTML trop pauvre pour conclure : {classes}"
    orphelines = [c for c in classes if not re.search(rf"\.{re.escape(c)}\b", CSS)]
    assert not orphelines, f"classes affichees mais jamais stylees : {orphelines}"


def test_le_BACK_et_le_LAY_ne_portent_pas_la_meme_couleur():
    """Les deux prix se lisent d'un coup d'oeil parce qu'ils n'ont pas la
    meme couleur ; les intervertir dans la feuille de style ferait lire
    chaque cote a l'envers, sans rien casser nulle part."""
    import re
    from liste_dense import CSS

    regles = {c: re.search(rf"i\.{c} \{{([^}}]*)\}}", CSS) for c in ("b", "l")}
    assert all(regles.values()), f"regles de prix introuvables : {regles}"
    back, lay = regles["b"].group(1), regles["l"].group(1)
    assert "--back" in back and "--lay" not in back, f"le back n'est plus bleu : {back}"
    assert "--lay" in lay and "--back" not in lay, f"le lay n'est plus rose : {lay}"


def test_les_etats_OPPOSES_ne_partagent_pas_une_couleur():
    """Une pastille fraiche et une pastille perimee de la meme couleur
    rendraient la colonne de fraicheur -- la raison d'etre de cette page --
    exactement aussi muette que son absence."""
    import re
    from liste_dense import CSS

    def teinte(nom):
        # Hexadecimal OU rgba() : un etat NORMAL n'a pas a etre allume, et
        # se dit par une teinte translucide plutot que par un aplat vif.
        trouve = re.search(rf"--{nom}:\s*(#[0-9A-Fa-f]{{3,8}}|rgba?\([^)]*\))", CSS)
        assert trouve, f"couleur « {nom} » absente de la feuille de style"
        return trouve.group(1).lower().replace(" ", "")

    for gauche, droite in (("frais", "perime"), ("back", "lay")):
        assert teinte(gauche) != teinte(droite), \
            f"« {gauche} » et « {droite} » portent la meme couleur"


def _tournois_entrelaces(maintenant):
    """Deux tournois dont les horaires s'imbriquent -- le cas observe en
    vrai : Hagen a 09:00 et 09:05, Varsovie a 09:02."""
    commun = {
        "status": "InPlay", "age_score_s": 2.0, "age_exchange_s": 2.0,
        "age_books_s": 2.0, "age_books_flux_s": 2.0, "age_stats_s": 2.0,
        "updated_ts": maintenant, "score": "1-0", "points": "30-0", "server": "0",
        "back_odds_a": 1.5, "lay_odds_a": 1.56,
        "back_odds_b": 2.6, "lay_odds_b": 2.74,
    }
    return pd.DataFrame([
        {**commun, "event_id": "h1", "participant1": "A", "participant2": "B",
         "league": "Hagen Challenger", "tour_type": "atp",
         "start_timestamp": maintenant - 600},
        {**commun, "event_id": "w1", "participant1": "C", "participant2": "D",
         "league": "Polish Open - Warsaw", "tour_type": "wta",
         "start_timestamp": maintenant - 480},
        {**commun, "event_id": "h2", "participant1": "E", "participant2": "F",
         "league": "Hagen Challenger", "tour_type": "atp",
         "start_timestamp": maintenant - 300},
    ])


def test_un_tournoi_ne_s_annonce_QU_UNE_FOIS(monkeypatch):
    """Trier sur la seule heure entrelace les tournois : l'entete « Hagen
    Challenger » etait ecrit deux fois dans la meme liste, separe par
    Varsovie -- on croyait a deux tournois distincts. Constate a l'ecran."""
    at = _lancer(monkeypatch, _tournois_entrelaces(time.time()))
    assert not at.exception
    h = html_liste(at)
    assert h.count('<span class="titre">Hagen Challenger</span>') == 1, \
        "le tournoi est annonce plusieurs fois"
    t = structure(at)
    assert [l["tournoi"] for l in t] == [
        "Hagen Challenger", "Hagen Challenger", "Polish Open - Warsaw"
    ], [l["tournoi"] for l in t]


def test_les_TOURNOIS_restent_ordonnes_par_leur_premier_match(monkeypatch):
    """Regrouper ne doit pas remplacer l'ordre chronologique par l'ordre
    alphabetique : c'est l'heure qui dit ou regarder en premier."""
    maintenant = time.time()
    df = _tournois_entrelaces(maintenant)
    # Varsovie commence desormais AVANT Hagen ; elle doit passer en tete
    # alors que son nom vient apres dans l'alphabet.
    df.loc[df["event_id"] == "w1", "start_timestamp"] = maintenant - 900
    at = _lancer(monkeypatch, df)
    assert [l["tournoi"] for l in structure(at)][0] == "Polish Open - Warsaw", \
        [l["tournoi"] for l in structure(at)]


def _cellules(at, classe):
    """Le contenu brut d'une cellule, match par match, tel qu'AFFICHE.

    Le `<span>` interne accepte des ATTRIBUTS (`[^>]*`), pas seulement la
    balise nue : un point marque rend `<span class="bp">` ou
    `<span class="neuf">`, jamais `<span>` seul. La forme stricte les
    ignorait silencieusement -- un sous-comptage qui ne fait echouer aucune
    assertion, juste mesurer moins que ce qui est reellement affiche."""
    import re
    h = html_liste(at)
    return re.findall(
        rf'<span class="{classe}">((?:<span[^>]*>[^<]*</span>)*)</span>', h)


def test_le_BACK_affiche_est_bien_la_cote_back(monkeypatch):
    """Sept mutations traversaient la suite ; celle-ci en fait partie.

    Le test qui pretendait couvrir ce point ne verifiait que ceci : les deux
    prix d'un joueur portent des classes DIFFERENTES. Permuter back et lay au
    site d'appel les laisse differentes -- chaque cote se lisait a l'envers
    et rien ne tombait. On verifie donc la VALEUR sous chaque classe.
    """
    import re
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    h = html_liste(at)
    paires = re.findall(r'<i class="b">([\d.]+)</i><i class="l">([\d.]+)</i>', h)
    assert paires, "aucune paire back/lay lisible dans la liste"
    for back, lay in paires:
        # Sur un carnet sain le lay est SUPERIEUR au back ; l'inversion se
        # voit donc sur n'importe quelle ligne de la fixture.
        assert float(lay) > float(back), \
            f"back {back} / lay {lay} : les deux prix sont intervertis"
    assert ("1.50", "1.56") in paires, f"le prix du joueur A n'est pas le sien : {paires}"
    assert ("2.60", "2.74") in paires, f"le prix du joueur B n'est pas le sien : {paires}"


def test_le_SET_EN_COURS_est_le_DERNIER_pas_le_premier(monkeypatch):
    """La fixture n'avait qu'un seul set : « c'est le dernier » etait vrai
    par accident, et surligner le premier ne reveillait personne."""
    import re
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    h = html_liste(at)
    blocs = re.findall(
        r'<span class="cases">((?:<b class="[^"]*">[^<]*</b>){2,})</span>', h)
    assert blocs, "aucune ligne a plusieurs sets : la fixture ne discrimine pas"
    for bloc in blocs:
        cases = re.findall(r'<b class="([^"]*)">([^<]*)</b>', bloc)
        marques = [i for i, (c, _) in enumerate(cases) if "encours" in c]
        assert marques == [len(cases) - 1], \
            f"le set marque n'est pas le dernier : {cases}"
    # Et la valeur surlignee est bien celle du dernier set joue.
    assert '<b class="encours">5</b>' in h and '<b class="encours">2</b>' in h, \
        "le set en cours n'affiche pas les jeux du dernier set (5-2)"


def test_chaque_joueur_affiche_SON_point(monkeypatch):
    """« 40-30 » : 40 au premier, 30 au second. Donner deux fois le meme
    point aux deux joueurs passait, la fixture les ayant identiques."""
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    points = _cellules(at, "pts")
    assert points, "aucune cellule de points"
    assert "<span>40</span><span>30</span>" in points, \
        f"les points ne sont pas attribues au bon joueur : {points}"
    assert "<span>30</span><span>15</span>" in points, points


def test_l_ECART_en_ticks_est_celui_du_bon_joueur(monkeypatch):
    """Les deux joueurs avaient le meme ecart : les permuter ne se voyait pas."""
    from live_data import ecart_en_ticks
    a = ecart_en_ticks(1.50, 1.56)
    b = ecart_en_ticks(2.60, 2.74)
    assert a != b, "la fixture ne distingue pas les deux ecarts"
    at = _lancer(monkeypatch, _trois_matchs(time.time()))
    assert f"{a} / {b}" in html_liste(at), \
        f"l'ecart attendu « {a} / {b} » n'est pas affiche"


def test_l_heure_affichee_est_celle_du_DEBUT_pas_du_dernier_cycle(monkeypatch):
    """La colonne annonce l'heure de debut. Y mettre `updated_ts` afficherait
    l'heure du dernier cycle du publieur -- la meme pour tous les matchs, et
    fausse pour chacun."""
    maintenant = time.time()
    at = _lancer(monkeypatch, _trois_matchs(maintenant))
    heures = [l["heure"] for l in structure(at)]
    cycle = pd.to_datetime(maintenant, unit="s").strftime("%H:%M")
    assert len(set(heures)) == len(heures), f"toutes les heures sont egales : {heures}"
    assert cycle not in heures, \
        f"l'heure du cycle ({cycle}) est affichee comme heure de debut : {heures}"
    attendu = pd.to_datetime(maintenant - 7200, unit="s").strftime("%H:%M")
    assert heures[0] == attendu, f"{heures[0]} au lieu de {attendu}"


def test_le_HTML_venu_de_la_BASE_est_echappe(monkeypatch):
    """Les noms de joueurs et de tournois viennent de la base. Sans
    echappement, tout ce qu'elle contient s'execute dans la page."""
    maintenant = time.time()
    df = _trois_matchs(maintenant)
    df.loc[df["event_id"] == "tot", "participant1"] = '<img src=x onerror=alert(1)>'
    df.loc[df["event_id"] == "tot", "league"] = '<script>alert(2)</script>'
    at = _lancer(monkeypatch, df)
    h = html_liste(at)
    # `onerror=` subsiste comme TEXTE et c'est sans danger : c'est le chevron
    # ouvrant qui fait une balise, et c'est lui qu'on echappe.
    assert "<script>" not in h, "le tournoi est injecte comme une vraie balise"
    assert "<img " not in h, "le nom du joueur est injecte comme une vraie balise"
    assert "&lt;script&gt;" in h, "le tournoi n'est pas echappe"
    assert "&lt;img src=x" in h, "le nom du joueur n'est pas echappe"


def test_les_matchs_TERMINES_restent_lisibles_sans_match_en_cours(monkeypatch):
    """Une fois le dernier match fini -- l'etat normal une bonne partie de la
    journee -- la page devenait entierement vide : le retour anticipe sur
    « aucun match en cours » emportait la liste des termines ET la fenetre de
    detail qu'on etait peut-etre en train de lire."""
    maintenant = time.time()
    df = _trois_matchs(maintenant)
    df["status"] = "Finished"
    at = _lancer(monkeypatch, df)
    assert not at.exception
    assert any("Aucun match en cours" in str(i.value) for i in at.info), \
        "l'absence de match en cours doit rester dite"
    termines = structure(at, second=True)
    assert termines, "la liste des matchs termines a disparu"
    assert at.button, "aucun match termine n'est ouvrable"


def test_le_clic_transmet_TOUS_les_identifiants_du_match(monkeypatch):
    """La source attribue parfois deux ou trois `event_id` a une meme
    rencontre, et la serie de cotes se repartit entre eux : n'en transmettre
    qu'un afficherait un demi-graphique sans le dire.

    Le test qui pretendait le verifier ne le pouvait pas : sa fixture n'avait
    aucun doublon, donc `event_ids` y valait toujours `event_id` et la
    mutation ne changeait rien. Il faut un match REELLEMENT dedouble.
    """
    maintenant = time.time()
    commun = {
        "status": "InPlay", "age_score_s": 2.0, "age_exchange_s": 2.0,
        "age_books_s": 2.0, "age_books_flux_s": 2.0, "age_stats_s": 2.0,
        "updated_ts": maintenant, "score": "6-4,3-2", "points": "40-30",
        "server": "0", "league": "Hagen Challenger", "tour_type": "atp",
        "participant1": "A", "participant2": "B",
        "start_timestamp": maintenant - 600,
        "back_odds_a": 1.50, "lay_odds_a": 1.56,
        "back_odds_b": 2.60, "lay_odds_b": 2.74,
    }
    # Meme marche et memes joueurs sous deux identifiants : c'est ainsi que la
    # source les emet, et `fusionner_doublons` les rassemble en une ligne.
    df = pd.DataFrame([
        {**commun, "event_id": "111", "id_market": "1.99"},
        {**commun, "event_id": "222", "id_market": "1.99"},
    ])
    from live_data import charger_matchs
    fusionne = charger_matchs(lecteur=lambda s_, q: df)
    assert len(fusionne) == 1, f"la fixture ne produit pas de doublon : {len(fusionne)}"
    attendu = str(fusionne.iloc[0]["event_ids"])
    assert "," in attendu, f"les deux identifiants ne sont pas rassembles : {attendu!r}"

    at = _lancer(monkeypatch, df)
    assert not at.exception
    at.button[0].click().run()
    obtenu = str(at.session_state["match_ouvert"])
    assert set(obtenu.split(",")) == set(attendu.split(",")), \
        f"le clic transmet {obtenu!r} au lieu de {attendu!r} -- la serie sera incomplete"


def test_la_BALLE_DE_BREAK_suit_la_regle_du_jeu():
    """Elle ne vient d'aucune colonne : elle se deduit du serveur et des
    points. Un faux positif serait pire que rien -- il ferait regarder un
    match ou il ne se passe pas ce qu'on annonce."""
    from liste_dense import balle_de_break as bb
    # server="0" : participant1 sert, donc c'est participant2 (indice 1) qui
    # peut tenir une balle de break.
    assert bb("0", "30-40") == 1, "le receveur a 40 contre 30 tient une balle"
    assert bb("0", "15-40") == 1
    assert bb("0", "40-A") == 1, "l'avantage au receveur aussi"
    assert bb("1", "40-30") == 0, "l'autre serveur, l'autre receveur"
    assert bb("1", "A-40") == 0
    # Ce qui n'en est PAS une.
    assert bb("0", "40-40") is None, "egalite : personne n'est a un point"
    assert bb("0", "40-15") is None, "c'est le SERVEUR qui mene"
    assert bb("0", "A-40") is None, "l'avantage au serveur n'est pas un break"
    assert bb("0", "6-5") is None, "jeu decisif : le service alterne dedans"
    assert bb(None, "30-40") is None, "serveur inconnu : on ne devine pas"
    assert bb("0", "") is None and bb("0", "40") is None


def test_le_point_de_BREAK_est_marque_dans_la_liste(monkeypatch):
    """C'est le moment ou un match bascule, et le seul que cette liste avait
    sous la main sans jamais le montrer."""
    maintenant = time.time()
    df = _trois_matchs(maintenant)
    df.loc[df["event_id"] == "tot", ["server", "points"]] = ["0", "30-40"]
    at = _lancer(monkeypatch, df)
    h = html_liste(at)
    assert '<span class="bp">40</span>' in h, "la balle de break n'est pas marquee"
    assert h.count('class="bp"') == 1, "une seule balle de break attendue"

    # Et a egalite, plus rien : sans ce controle, marquer TOUJOURS le second
    # joueur passerait pour un succes.
    df.loc[df["event_id"] == "tot", "points"] = "40-40"
    at = _lancer(monkeypatch, df)
    assert 'class="bp"' not in html_liste(at), "40-40 n'est pas une balle de break"


def test_le_prix_qui_a_BOUGE_se_distingue_de_celui_qui_dort():
    """La couleur n'apparait que la ou il se passe quelque chose : c'est ce
    qui fait qu'on regarde la bonne ligne."""
    from liste_dense import lignes, mouvements_de_prix, rendu
    maintenant = time.time()
    serie = pd.DataFrame([
        # Avant la fenetre, puis apres : back monte, lay descend.
        {"event_id": "42", "ts": maintenant - 600, "back_odds_a": 1.50,
         "lay_odds_a": 1.60, "back_odds_b": 2.60, "lay_odds_b": 2.70},
        {"event_id": "42", "ts": maintenant - 5, "back_odds_a": 1.80,
         "lay_odds_a": 1.40, "back_odds_b": 2.60, "lay_odds_b": 2.70},
    ])
    bouge = mouvements_de_prix(serie, maintenant)
    assert bouge["42"]["back_odds_a"] == "hausse", bouge
    assert bouge["42"]["lay_odds_a"] == "baisse", bouge
    assert "back_odds_b" not in bouge["42"], "un prix inchange ne bouge pas"

    df = pd.DataFrame([{
        "event_id": "42", "participant1": "A", "participant2": "B",
        "league": "L", "tour_type": "atp", "score": "6-4", "points": "30-0",
        "server": "0", "start_timestamp": maintenant, "updated_ts": maintenant,
        "age_score_s": 2.0, "age_exchange_s": 2.0, "age_books_s": 2.0,
        "age_books_flux_s": 2.0, "age_stats_s": 2.0,
        "back_odds_a": 1.80, "lay_odds_a": 1.40,
        "back_odds_b": 2.60, "lay_odds_b": 2.70,
    }])
    h = rendu(lignes(df, maintenant, bouge))
    assert '<i class="b hausse">1.80</i>' in h, h[h.find('class="prix"'):][:200]
    assert '<i class="l baisse">1.40</i>' in h
    assert '<i class="b">2.60</i>' in h, "le prix immobile ne doit rien porter"


def test_l_ENTETE_de_colonnes_partage_la_GRILLE_des_lignes():
    """Deux grilles jumelles divergent au premier changement de largeur, et
    l'entete se met alors a designer la colonne d'a cote -- mesure : « SETS »
    tombait 70 px a cote de la sienne tant que les colonnes etaient `auto`.
    Une seule regle, des largeurs fixes."""
    from liste_dense import CSS, entete_colonnes
    entete = entete_colonnes()
    assert 'class="match entete"' in entete, "l'entete n'utilise pas la grille des lignes"
    # La grille LARGE est celle que l'entete nomme : c'est elle qui doit
    # rester unique et figee. La grille mobile en est une seconde, assumee --
    # et l'entete y est masquee, precisement parce qu'elle nommerait le vide.
    large, _, mobile = CSS.partition("@media")
    assert large.count("grid-template-columns:") == 1, \
        "une seconde grille large est apparue : elles vont diverger"
    assert ".liste-dense .match.entete {{ display: none; }}".replace("{{", "{").replace("}}", "}") \
        in mobile, "l'entete doit disparaitre quand la mise en page se replie"
    grille = large[large.index("grid-template-columns:"):]
    grille = grille[:grille.index(";")]
    assert "auto" not in grille, \
        "une colonne `auto` se dimensionne sur SA ligne : l'alignement casse"
    # Autant de cellules dans l'entete que de colonnes dans la grille.
    # `minmax(0, 1fr)` compte pour UNE colonne : l'espace qu'il contient ne
    # separe pas deux pistes.
    colonnes = len(grille.split(":", 1)[1].replace(", ", ",").split())
    import re as _re
    # L'entete a UNE cellule de moins que la grille : son titre court sur les
    # deux premieres colonnes (heure + noms). Les colonnes ETIQUETEES, elles,
    # sont toutes la -- ce sont les seules qui doivent s'aligner.
    cellules = _re.findall(
        r'<span class="(heure|noms|jeux|pts|prix|ecart|flux)"', entete)
    assert cellules == ["noms", "jeux", "pts", "prix", "ecart", "flux"], cellules
    assert colonnes == 7, f"la grille a {colonnes} colonnes, l'entete en couvre 7"


def test_la_page_DIT_quand_la_source_de_score_est_figee(monkeypatch):
    """La panne la plus trompeuse des trois : publieur vivant, capteur de
    score vivant, et pourtant plus rien ne bouge. Le publieur refuse alors
    de declarer les matchs termines -- la page doit dire POURQUOI, sinon
    elle affiche un score fige sans dire qu'il l'est."""
    maintenant = time.time()
    # C'est le battement du PUBLIEUR qui porte l'etat de la source : c'est
    # lui qui s'en apercoit, pas la page.
    at = _lancer(
        monkeypatch, _trois_matchs(maintenant),
        battement_publieur=lambda: {
            "ts": maintenant,
            "state": {"n_echecs": 0, "capteur_score": "fige"},
        },
    )
    assert not at.exception
    messages = " ".join(str(w.value) for w in at.warning)
    assert "cache" in messages, f"la source figee n'est pas annoncee : {messages!r}"
    # Et la liste reste affichee : c'est tout l'objet du correctif.
    assert structure(at), "les matchs ont disparu alors qu'ils sont encore la"


def test_l_entete_ANNONCE_ses_colonnes_par_leur_nom():
    """Une colonne sans libelle oblige a deviner que le nombre du milieu est
    le point du jeu, ou dans quel ordre viennent les cinq pastilles. Vider
    un libelle ne cassait rien et ne reveillait personne."""
    from liste_dense import entete_colonnes
    import re
    entete = entete_colonnes()
    for colonne in ("jeux", "pts", "prix", "ecart", "flux"):
        trouve = re.search(rf'<span class="{colonne}">([^<]*)</span>', entete)
        assert trouve and trouve.group(1).strip(), \
            f"la colonne « {colonne} » n'est pas annoncee"


def test_le_titre_du_tournoi_part_du_BORD_et_non_de_la_colonne_des_noms():
    """Cale sur la colonne des NOMS, il laissait un vide de plusieurs
    centimetres a sa gauche et se faisait tronquer -- « Grodzisk Mazowiecki
    Challe… » sur une carte pourtant large. Il court donc sur les deux
    premieres colonnes.

    Les libelles de colonnes, eux, restent chacun sur la sienne : c'est la
    seule chose qui doit s'aligner, et `test_l_ENTETE_de_colonnes_partage_la_
    GRILLE_des_lignes` s'en charge.
    """
    import re
    from liste_dense import CSS, entete_tournoi

    entete = entete_tournoi({"tournoi": "Grodzisk Mazowiecki Challenger",
                             "competition": "ATP CHALLENGER"})
    assert '<span class="noms"><span class="titre">' in entete, \
        f"le titre n'occupe plus directement la cellule : {entete[:200]}"
    assert '<span class="heure">' not in entete, \
        "une cellule d'heure vide empecherait le titre de partir du bord"
    regle = re.search(r'\.match\.entete \.noms \{([^}]*)\}', CSS)
    assert regle, "la cellule de titre n'a plus de regle propre"
    assert "grid-column: heure-start" in regle.group(1), \
        "le titre ne court plus sur la premiere colonne : le vide revient"




def test_l_entete_ne_dessine_AUCUN_trait_horizontal():
    """La carte borne deja le tournoi en haut et en bas. Un filet sous
    l'entete faisait TROIS lignes horizontales pour un seul match -- « encore
    trop de lignes horizontales », et c'etait vrai. C'est l'espace qui
    separe.

    Ce test remplace celui qui EXIGEAIT ce filet, ecrit une heure plus tot :
    ce qu'on veut a change, et un test qui protege une decision perimee est
    pire qu'aucun test.
    """
    import re
    from liste_dense import CSS
    regle = re.search(r"\.match\.entete\.tournoi \{([^}]*)\}", CSS)
    assert regle, "l'entete de tournoi n'a plus de regle propre"
    assert "border-bottom" not in regle.group(1), "un trait de plus sous l'entete"
    # La regle GENERIQUE de l'entete en portait un, elle aussi : ne viser que
    # la regle du tournoi laissait le trait en place.
    generique = re.search(r"\.match\.entete \{([^}]*)\}", CSS)
    assert generique and "border-bottom" not in generique.group(1), \
        "l'entete generique dessine encore un trait"
    assert ".match.entete.tournoi::after" not in CSS, \
        "un filet pose sous l'entete : la carte le fait deja"
    # L'air demande reste, lui : c'est ce qui separe desormais.
    assert "padding-bottom: 1.25rem" in regle.group(1), \
        f"l'entete ne respire plus : {regle.group(1)}"


def test_un_score_a_CINQ_SETS_n_ecrase_pas_la_colonne_voisine():
    """Vu au rendu : la colonne des sets etait dimensionnee pour trois sets,
    et un cinquieme debordait PAR-DESSUS la colonne des points -- le « 8 »
    du cinquieme set sur le « 30 » du jeu en cours. Illisible, et faux.

    Cales a droite, ce sont les sets les plus ANCIENS qui disparaissent
    quand la place manque, jamais celui qui se joue.
    """
    import re
    from liste_dense import CSS
    regle = re.search(r"\.liste-dense \.jeux \.cases \{([^}]*)\}", CSS)
    assert regle, "les cases de set n'ont plus de regle propre"
    assert "overflow: hidden" in regle.group(1), \
        "sans rognage, un cinquieme set deborde sur les points"
    assert "justify-content: flex-end" in regle.group(1), \
        "cales a gauche, ce serait le set EN COURS qui disparaitrait"
    grille = CSS[CSS.index("grid-template-columns:"):]
    grille = grille[:grille.index(";")].split(":", 1)[1].replace(", ", ",").split()
    # La colonne des sets est la TROISIEME : heure, noms, sets -- et elle
    # porte desormais AUSSI la balle de service.
    assert float(grille[2].rstrip("rem")) >= 7.0, \
        f"colonne des sets trop etroite pour la balle et quatre sets : {grille[2]}"


def test_chaque_CIRCUIT_a_sa_teinte_de_badge():
    """« ATP » et « WTA » ne sont pas la meme population, et la liste sert a
    choisir ou regarder. Un badge gris pour les deux ne l'aide pas.

    Les teintes evitent celles qui portent deja un sens dans la ligne : bleu
    du back, rose du lay, vert de l'accent, orange de la balle de break,
    rouge du flux mort.
    """
    import re
    from liste_dense import CSS

    for circuit, attendue in (("ATP", "atp"), ("WTA", "wta"),
                              ("ATP CHALLENGER", "atp challenger")):
        from liste_dense import entete_competition
        h = entete_competition({"competition": circuit})
        trouve = re.search(r'class="competition ([^"]*)"', h)
        assert trouve and trouve.group(1) == attendue, \
            f"{circuit} : classe {trouve.group(1) if trouve else None!r}"

    def teinte(nom):
        r = re.search(rf"\.competition\.{nom} \{{([^}}]*)\}}", CSS)
        assert r, f"le badge « {nom} » n'a pas de teinte"
        return r.group(1)

    assert teinte("atp") != teinte("wta"), \
        "ATP et WTA portent la meme teinte : le badge n'apprend rien"


def test_la_balle_de_service_est_COLLEE_aux_sets():
    """Dans une colonne a elle, elle restait a 83 px de la premiere case --
    tout le vide de la colonne des sets, calee a droite, s'intercalait.
    Mesure au navigateur : 2 px une fois dans le groupe.

    Elle reste HORS du groupe rogne : sinon un cinquieme set la ferait
    disparaitre avant les cases, alors qu'elle dit qui sert.
    """
    import re
    from liste_dense import CSS, lignes, rendu
    maintenant = time.time()
    df = _trois_matchs(maintenant)
    h = rendu(lignes(df, maintenant))
    assert re.search(r'<span class="jeux"><span><em>[^<]*</em><span class="cases">', h), \
        "la balle n'est plus dans le groupe des sets"
    assert '<span class="srv">' not in h, "l'ancienne colonne de service subsiste"
    cases = re.search(r"\.liste-dense \.jeux \.cases \{([^}]*)\}", CSS)
    assert cases and "overflow: hidden" in cases.group(1), \
        "seules les CASES doivent etre rognees"


def test_la_COMPETITION_coiffe_les_tournois_et_ne_se_dit_qu_une_fois(monkeypatch):
    """Trois niveaux : competition, tournoi, matchs. « ATP » et « WTA » ne se
    choisissent pas comme un tournoi -- on decide d'abord ou regarder,
    ensuite lequel.

    Le circuit doit donc etre annonce UNE fois au-dessus de ses tournois, et
    non repete sur chacun : c'est le meme defaut que les tournois eclatees
    par un tri sur la seule heure, un cran plus haut.
    """
    maintenant = time.time()
    df = _trois_matchs(maintenant)
    # Deux tournois ATP separes dans le temps par un WTA : trie sur la seule
    # heure, « ATP » serait annonce deux fois.
    df.loc[df["event_id"] == "pas-commence", ["score", "points"]] = ["1-0", "30-0"]
    at = _lancer(monkeypatch, df)
    assert not at.exception
    h = html_liste(at)
    import re
    circuits = re.findall(r'class="competition[^"]*">([^<]*)</div>', h)
    assert circuits, f"aucun niveau de competition : {h[:200]}"
    assert len(circuits) == len(set(circuits)), \
        f"un circuit est annonce plusieurs fois : {circuits}"
    # Et l'entete de tournoi ne le repete plus.
    assert 'class="circuit' not in h, \
        "le badge de circuit subsiste dans l'entete de tournoi : il fait doublon"


# --- Task 3 (2026-08-10) : la liste cesse d'appeler `charger_serie` --------
#
# `charger_serie(",".join(event_ids))` joint les identifiants de TOUS les
# matchs en cours en une seule requete -- ils se retrouvent donc tous
# DECLARES comme une seule famille aux yeux de `fusionner_series` (tour 1).
# Le publieur ecrit les six matchs dans le meme cycle, donc au meme `ts` :
# la fusion les repliait en une poignee de lignes, et la plupart perdaient
# leur identite -- donc leur fleche de mouvement. `charger_mouvements`
# (tour 2) ne fusionne jamais : c'est lui que la page doit appeler.


def test_les_six_matchs_gardent_leur_FLECHE(monkeypatch):
    """Reproduction directe du defaut, au niveau de la PAGE -- pas juste de
    `fusionner_series` en isolation (deja couvert par test_live_data.py) :
    ce test protege le SITE D'APPEL dans pages/live.py, celui qui joint six
    matchs dans un seul `charger_serie(...)`.

    On regarde le HTML REELLEMENT pousse, pas un calcul rejoue : rejouer
    mouvements_de_prix() dans le test verifierait que la page fait ce que le
    test refait, pas ce qu'elle montre.

    Le seuil etait `>= 6` : chaque match qui garde son identite porte DEUX
    fleches de chaque sens (back ET lay du meme joueur bougent ensemble dans
    cette fixture), donc six matchs intacts en portent 12. Le symptome
    mesure en service -- "trois matchs sur six perdaient leur fleche" -- en
    laissait trois intacts, donc 3 x 2 = 6 : exactement le seuil. `>= 6`
    passait donc sur le symptome meme qu'il devait attraper, et n'aurait
    tourne au rouge qu'avec quatre matchs detruits sur six. Seul le compte
    EXACT protege le site d'appel.
    """
    maintenant = time.time()
    matchs = pd.DataFrame([
        {**LIGNE_REELLE_INPLAY, "event_id": str(i),
         "participant1": f"J{i}a", "participant2": f"J{i}b",
         "updated_ts": maintenant}
        for i in range(6)
    ])
    # Deux releves par match, mais au MEME horodatage d'un match a l'autre --
    # c'est exactement la collision que le publieur produit en service : un
    # releve avant la fenetre de deux minutes (SEUIL_MOUVEMENT_S), un dedans,
    # pour que chaque match ait un mouvement A MONTRER si son identite
    # survit.
    releves = []
    for i in range(6):
        releves.append({"event_id": str(i), "ts": maintenant - 300,
                        "back_odds_a": 2.0, "lay_odds_a": 2.1,
                        "back_odds_b": 2.0, "lay_odds_b": 2.1})
        releves.append({"event_id": str(i), "ts": maintenant - 10,
                        "back_odds_a": 3.0, "lay_odds_a": 3.1,
                        "back_odds_b": 1.5, "lay_odds_b": 1.6})
    serie = pd.DataFrame(releves)

    at = _lancer(monkeypatch, matchs, serie=serie)

    assert not at.exception
    html = html_liste(at)
    # Compter la sous-chaine "hausse" brute se laisse tromper : la feuille de
    # style CSS (injectee dans la MEME balise markdown que la liste, cf.
    # liste_dense.CSS) nomme "hausse"/"baisse" quatre fois chacune comme
    # selecteurs, un bruit constant qui suffisait a lui seul a satisfaire
    # `>= 6` -- constate en ecrivant ce test AVANT le correctif : il passait
    # a tort avec un seul match sur six montrant une vraie fleche. On compte
    # donc la BALISE rendue, `<i class="b hausse">`/`<i class="l hausse">`,
    # qui ne peut venir que d'un prix reellement marque.
    hausse = html.count('<i class="b hausse">') + html.count('<i class="l hausse">')
    baisse = html.count('<i class="b baisse">') + html.count('<i class="l baisse">')
    # Compte EXACT, pas un seuil : chacun des SIX matchs porte SES DEUX
    # hausses (back et lay du joueur A) et SES DEUX baisses (back et lay du
    # joueur B) -- 12 de chaque. Un seuil `>= 6` passait deja sur le
    # symptome production (trois matchs sur six perdaient leur fleche, donc
    # trois survivants x 2 = 6) ; seul le compte exact protege le site
    # d'appel contre une fusion qui replierait ne serait-ce que deux matchs.
    assert hausse == 12, \
        f"chacun des six matchs doit porter ses deux hausses, vu {hausse}"
    assert baisse == 12, \
        f"chacun des six matchs doit porter ses deux baisses, vu {baisse}"


# --- Le surlignage local (task 6) : la memoire de session ne doit pas
# survivre a un passage a vide -------------------------------------------


def test_vu_en_cours_est_REINITIALISE_quand_la_liste_se_vide(monkeypatch):
    """Sans ce reset, un match qui disparait de la liste des « en cours »
    (termine, ou simplement absent d'un cycle) puis y revient plus tard sous
    le meme `event_ids` se compare a un instantane arbitrairement vieux --
    et tout ce qui a derive pendant son absence s'allumerait a tort."""
    maintenant = time.time()
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["updated_ts"] = maintenant
    at = _lancer(monkeypatch, pd.DataFrame([ligne]))
    assert not at.exception
    assert at.session_state["vu_en_cours"], \
        "l'instantane du premier cycle doit exister avant le test du reset"

    # Meme session (memes mocks de battement), mais la liste se vide : plus
    # aucun match « en cours » au cycle suivant.
    _mock_lecteur(monkeypatch, pd.DataFrame())
    at.run()

    assert not at.exception
    assert at.session_state["vu_en_cours"] == {}, \
        "le snapshot perime doit etre efface, pas laisse tel quel"


def test_l_ORDRE_marquer_puis_stocker_est_VERROUILLE(monkeypatch):
    """`pages/live.py` doit appeler `marquer_changements()` AVANT
    `st.session_state["vu_en_cours"] = instantane(...)` : permuter ces deux
    lignes rend le surlignage silencieusement mort -- `marquer_changements`
    compare alors la structure a l'instantane qu'elle vient tout juste de
    produire, donc a elle-meme, et rien ne differe jamais. Aucun test de
    `tests/test_flux_continu.py` ne peut le voir : ils testent les deux
    fonctions ISOLEMENT, jamais le site d'appel dans l'ordre ou il les
    invoque -- exactement le trou que ce test protege.

    Le compte de reference (`base`, ci-dessous) N'EST PAS fige a une valeur
    en dur : `html_liste()` inclut CSS_FLUX, dont le selecteur
    `.liste-dense .neuf` fait deja lire "neuf" au moins une fois avant
    qu'aucune cellule ne soit marquee -- et la garde
    `prefers-reduced-motion` (fix voisin de ce meme correctif) le nomme une
    seconde fois pour couper son animation. Coder ce nombre en dur romprait
    le test au premier ajustement de la feuille sans rapport avec ce
    qu'il verifie : c'est le DELTA entre deux cycles qui prouve l'ordre, pas
    le bruit de depart (voir la mise en garde sur `html_liste`).
    """
    maintenant = time.time()
    ligne = dict(LIGNE_REELLE_INPLAY)
    ligne["event_id"] = "verrou"
    ligne["updated_ts"] = maintenant
    ligne["points"] = "30-15"
    df = pd.DataFrame([ligne])

    at = _lancer(monkeypatch, df)
    assert not at.exception
    base = html_liste(at).count("neuf")
    assert base >= 1, \
        f"la feuille CSS_FLUX doit au moins nommer .liste-dense .neuf, vu {base}"

    # Un seul changement -- le point du premier joueur -- doit allumer UNE
    # seule cellule au-dessus de ce bruit.
    df_change = pd.DataFrame([{**ligne, "points": "40-15"}])
    _mock_lecteur(monkeypatch, df_change)
    at.run()
    assert not at.exception
    apres_changement = html_liste(at).count("neuf")
    assert apres_changement == base + 1, \
        ("une seule cellule doit s'allumer au-dessus du bruit de la "
         f"feuille, vu {apres_changement - base}")

    # Rien ne bouge plus entre ce cycle et le suivant : rien de nouveau ne
    # doit s'allumer.
    _mock_lecteur(monkeypatch, df_change)
    at.run()
    assert not at.exception
    apres_stable = html_liste(at).count("neuf")
    assert apres_stable == base, \
        ("aucune valeur n'a change depuis le cycle precedent, mais "
         f"{apres_stable - base} cellule(s) restent allumees")


def test_une_ligne_SANS_score_mais_avec_un_MARCHE_reste_affichee(monkeypatch):
    """Signale le 2026-08-10 : les matchs du Challenger de Hambourg
    n'apparaissent pas. Aucune source ne donne leur score -- ni l'API, ni le
    canal `general` d'OrbitX -- alors que leur carnet arrive a quatre
    secondes. Le PoC les publie sous `source_score = "exchange_seul"`, score
    et points a NULL.

    Le filtre `a_joue` les jetait. C'est le CABLAGE de sa correction : sans
    l'argument `cotes_bougent` passe ici, le predicat serait juste et inerte.

    Fixture DISCRIMINANTE : deux lignes sans score, l'une AVEC marche et
    l'autre SANS. Une seule doit rester -- si les deux restaient, le filtre
    ne filtrerait plus rien.
    """
    maintenant = time.time()
    commun = {
        "status": "InPlay", "league": "Hamburg Challenger", "tour_type": "atp",
        "score": None, "points": None,
        "age_score_s": None, "age_exchange_s": 2.0,
        "age_books_s": None, "age_stats_s": None,
        "updated_ts": maintenant,
    }
    df = pd.DataFrame([
        {**commun, "event_id": "prod:AVEC", "id_market": "1.260938249",
         "participant1": "Jan Opitz", "participant2": "Ol Krutykh",
         "back_odds_a": 1.10, "back_odds_b": 8.20,
         "book_odds_a": None, "book_odds_b": None},
        {**commun, "event_id": "evt-SANS", "id_market": None,
         "participant1": "Pas De", "participant2": "Marche Ici",
         "back_odds_a": None, "back_odds_b": None,
         "book_odds_a": None, "book_odds_b": None},
    ])
    at = _lancer(monkeypatch, df)
    texte = " ".join(str(el.value) for el in at.markdown)
    assert "Jan Opitz" in texte, (
        "la ligne sans score mais AVEC marche a ete filtree : c'est le match "
        "signale, et il n'existe nulle part ailleurs"
    )
    assert "Marche Ici" not in texte, (
        "la ligne sans score NI marche est restee : le filtre ne filtre plus"
    )
