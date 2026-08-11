"""Premiers tests du depot : les fonctions qui interrogent la base et
transforment en tableau. Ce sont elles qui peuvent mentir en silence."""

from datetime import date

import pandas as pd

from live_data import (
    CHEMIN_BATTEMENT_PUBLIEUR,
    CHEMIN_BATTEMENT_SCORE,
    COLONNES_MOUVEMENT,
    SCHEMA,
    SEUIL_BATTEMENT_ARRETE_S,
    SEUIL_FRAICHEUR_BOOKS_FLUX_S,
    SEUIL_FRAICHEUR_BOOKS_S,
    SEUIL_FRAICHEUR_EXCHANGE_S,
    SEUIL_FRAICHEUR_SCORE_S,
    SEUIL_FRAICHEUR_STATS_S,
    SEUIL_PUBLIEUR_ARRETE_S,
    SEUILS_PAR_FLUX,
    age_a_la_lecture,
    age_du_battement,
    battement_absent,
    capteur_score_mort,
    a_joue,
    charger_mouvements,
    competition,
    chronologie,
    ecart_en_ticks,
    probabilite_implicite,
    charger_bilan_qa,
    charger_matchs,
    charger_matchs_passes,
    charger_points,
    charger_serie,
    duree_courte,
    en_datetime,
    evenements,
    fusionner_doublons,
    fusionner_series,
    avancement,
    fraicheur,
    lire_battement_publieur,
    points_uniques,
    publieur_arrete,
    publieur_ecritures_refusees,
    serie_longue,
)
from fixtures_reelles import (
    BATTEMENT_REEL_PUBLIEUR,
    CAPTURE_TS,
    CAPTURE_TS_FINISHED,
    LIGNE_REELLE_BOOKS_FLUX_MORT,
    LIGNE_REELLE_BOOKS_SAINE,
    LIGNE_REELLE_FINISHED,
    LIGNE_REELLE_INPLAY,
    LIGNE_REELLE_MI_CYCLE,
    LIGNES_REELLES_MATCHS,
    LIGNES_REELLES_POINTS,
    LIGNES_REELLES_QA,
)


def test_un_flux_recent_est_frais():
    assert fraicheur(5.0, seuil=30.0) == "frais"


def test_un_flux_ancien_est_perime():
    assert fraicheur(120.0, seuil=30.0) == "perime"


def test_un_age_inconnu_n_est_pas_frais():
    """None n'est pas zero : un flux dont on ignore l'age ne doit surtout pas
    s'afficher en vert. C'est le defaut qui a laisse le capteur de cotes
    passer pour vivant pendant des heures."""
    assert fraicheur(None, seuil=30.0) == "inconnu"


# --- age_a_la_lecture : le coeur du defaut C4 -------------------------------
#
# Le publieur ecrit `age_stocke` (l'age du flux) ET `updated_ts` (l'instant du
# cycle) UNE SEULE FOIS. Si on relit `age_stocke` tel quel, un publieur mort
# depuis des heures affiche toujours le meme petit age -- vert pour toujours.
# L'age vrai a la lecture rattrape le temps ecoule depuis le cycle :
# `age_stocke + (maintenant - updated_ts)`.


def test_age_a_la_lecture_rattrape_le_temps_ecoule_depuis_le_cycle():
    """Le cas nominal du defaut : un cycle vieux de 300 s avec un age stocke
    de 2 s doit rendre un age reel proche de 302 s, pas 2 s."""
    maintenant = 1_000_000.0
    reel = age_a_la_lecture(2.0, maintenant - 300.0, maintenant)
    assert reel == 302.0


def test_publieur_mort_depuis_longtemps_rend_toutes_les_pastilles_rouges():
    """Demonstration bout en bout de la correction : un publieur arrete
    depuis 1h, avec un dernier age stocke minuscule (2 s, le cycle qui a
    ecrit la ligne l'a vu frais), doit neanmoins virer perime a la lecture."""
    maintenant = 1_000_000.0
    updated_ts_mort = maintenant - 3600.0
    reel = age_a_la_lecture(2.0, updated_ts_mort, maintenant)
    assert fraicheur(reel, seuil=30.0) == "perime"


def test_age_a_la_lecture_age_stocke_absent_reste_inconnu():
    """Un flux jamais recu par ce cycle (age_stocke=None) est inconnu,
    quelle que soit la sante du publieur : ce n'est pas la meme information
    qu'un publieur mort."""
    assert age_a_la_lecture(None, 1_000_000.0, 1_000_000.0) is None


def test_age_a_la_lecture_updated_ts_absent_devient_inconnu():
    """updated_ts absent ou illisible : impossible de savoir depuis combien
    de temps la ligne n'a pas bouge -- inconnu, jamais frais par defaut."""
    assert age_a_la_lecture(2.0, None, 1_000_000.0) is None
    assert fraicheur(age_a_la_lecture(2.0, None, 1_000_000.0), seuil=30.0) == "inconnu"


def test_age_a_la_lecture_updated_ts_illisible_devient_inconnu():
    assert age_a_la_lecture(2.0, "pas-une-date", 1_000_000.0) is None


def test_age_a_la_lecture_updated_ts_dans_le_futur_ne_devient_pas_negatif():
    """Derive d'horloge : updated_ts au futur ne doit ni rendre l'age negatif
    ni le diminuer -- meme convention que Live.live_state.age, qui borne le
    delta a zero plutot que d'afficher plus frais que l'age stocke lui-meme."""
    maintenant = 1_000_000.0
    reel = age_a_la_lecture(2.0, maintenant + 50.0, maintenant)
    assert reel == 2.0


# --- NaN pandas (pas None Python) : la moitie non testee des gardes -------
#
# Toutes les assertions ci-dessus passent le None de Python. Une lecture
# pandas d'un NULL SQL dans une colonne flottante rend numpy.nan, une valeur
# DIFFERENTE de None que `is None` ne detecte pas -- seul `pd.isna` le fait.
# LIGNE_REELLE_INPLAY (event_id 3796196, TeNNet_test.live_now, capture du
# 2026-08-03) porte ce NaN reel sur age_books_s/age_stats_s : sur cette
# capture, c'est l'etat DOMINANT (50-55 lignes sur 58-59), pas un cas rare.


def test_fraicheur_sur_un_nan_pandas_reel_reste_inconnu():
    """Mutation attendue si ce test manque : `if x is None or pd.isna(x)`
    -> `if x is None` dans fraicheur() passerait ce NaN pour un age valide
    (float(nan) <= seuil vaut False -> "perime", jamais "frais" par chance,
    mais ce n'est PAS la garde qui le protege)."""
    age_nan_reel = pd.DataFrame([LIGNE_REELLE_INPLAY]).iloc[0]["age_books_s"]
    assert fraicheur(age_nan_reel, seuil=30.0) == "inconnu"


def test_age_a_la_lecture_sur_un_nan_pandas_reel_reste_inconnu():
    """Meme angle mort que ci-dessus, cote age_a_la_lecture() : age_stocke
    ET updated_ts passes comme de vrais scalaires numpy issus d'une lecture
    pandas, pas des None Python ecrits a la main."""
    ligne = pd.DataFrame([LIGNE_REELLE_INPLAY]).iloc[0]
    assert age_a_la_lecture(ligne["age_books_s"], ligne["updated_ts"], CAPTURE_TS) is None
    assert age_a_la_lecture(ligne["age_stats_s"], ligne["updated_ts"], CAPTURE_TS) is None
    # Contraste : le meme appel sur un flux CONNU de la meme ligne reelle
    # rend un nombre, pas None -- la garde ne bloque pas tout par accident.
    reel = age_a_la_lecture(ligne["age_score_s"], ligne["updated_ts"], CAPTURE_TS)
    assert reel is not None and reel > 0


# --- SEUILS_PAR_FLUX : un seuil de fraicheur PROPRE a chaque source --------
#
# Un seuil unique (30 s, ancien) applique aux quatre flux affichait du rouge
# PERMANENT sur l'exchange (cadence documentee 180 s) et les books (jusqu'a
# 227 s pour le plus lent des bookmakers "en direct") -- l'operateur apprend
# alors a ignorer la pastille, le meme mecanisme que l'incident d'origine,
# cote rouge cette fois. Chaque test ci-dessous pin la valeur EXACTE (pas
# seulement relue -- c'est le defaut I1 du tour precedent, applique cette
# fois aux quatre seuils) ET verifie un cas reel/mesure concret, pas
# seulement la constante contre elle-meme.


def test_seuils_par_flux_couvre_les_cinq_colonnes_dage():
    """Cinq colonnes depuis le tour 4 : `age_books_s` (le PRIX) et
    `age_books_flux_s` (le FLUX) sont deux quantites distinctes, chacune sa
    propre pastille et son propre seuil."""
    assert {v[0] for v in SEUILS_PAR_FLUX.values()} == {
        "age_score_s", "age_exchange_s", "age_books_s",
        "age_books_flux_s", "age_stats_s",
    }


def test_seuils_par_flux_associe_chaque_flux_a_sa_bonne_colonne_et_son_bon_seuil():
    """Hardcode le mapping (colonne, seuil) ATTENDU pour chaque pastille,
    independamment du dict lui-meme : une mutation qui permuterait deux
    paires dans SEUILS_PAR_FLUX (ex. f_score lie a la colonne ou au seuil de
    f_books) ne serait PAS attrapee par un test qui derive son attendu du
    meme dict qu'il verifie -- ni, dans ce cas precis, par la demonstration
    "tout est vert" sur LIGNE_REELLE_MI_CYCLE (ses quatre ages reels sont
    tous sous les quatre seuils, une permutation resterait donc verte elle
    aussi)."""
    assert SEUILS_PAR_FLUX["f_score"][:2] == ("age_score_s", 600.0)
    assert SEUILS_PAR_FLUX["f_exchange"][:2] == ("age_exchange_s", 720.0)
    assert SEUILS_PAR_FLUX["f_books"][:2] == ("age_books_s", 180.0)
    assert SEUILS_PAR_FLUX["f_books_flux"][:2] == ("age_books_flux_s", 600.0)
    assert SEUILS_PAR_FLUX["f_stats"][:2] == ("age_stats_s", 900.0)


def test_fraicheur_exige_un_seuil_explicite():
    """`seuil` n'a plus de defaut depuis ce tour : quatre flux, quatre
    seuils, aucune valeur par defaut ne serait jamais la bonne pour tout le
    monde -- un defaut aurait reproduit, a l'identique, le defaut que ce
    tour corrige (un seuil pense pour un flux applique par accident a un
    autre)."""
    import pytest
    with pytest.raises(TypeError):
        fraicheur(5.0)


def test_seuil_score_est_epingle():
    assert SEUIL_FRAICHEUR_SCORE_S == 600.0


def test_seuil_score_couvre_le_p95_de_la_bonne_distribution_avec_marge():
    """CORRECTIF I3 (tour 3) : la premiere version de ce seuil (180 s)
    mesurait l'ecart ENTRE deux changements de score (p95=103s). C'est la
    mauvaise quantite -- paradoxe de l'inspection, voir le commentaire de
    SEUIL_FRAICHEUR_SCORE_S. Remesure sur l'AGE LU (echantillonne toutes les
    5s entre deux changements) : p95 = 315,0s (agent) / 294,5s (relecteur,
    independant). Le seuil doit rester au-dessus des DEUX -- pas seulement
    de l'ancien p95, qui n'etait pas la bonne mesure."""
    p95_agent = 315.0
    p95_relecteur = 294.5
    assert SEUIL_FRAICHEUR_SCORE_S > p95_agent
    assert SEUIL_FRAICHEUR_SCORE_S > p95_relecteur
    assert fraicheur(p95_agent, SEUIL_FRAICHEUR_SCORE_S) == "frais"


def test_seuil_score_180_aurait_produit_9_pourcent_de_rouge_sur_matchs_vivants():
    """Preuve directe du defaut I3 : avec l'ANCIEN seuil (180s), l'age
    mesure au p90 de la bonne distribution (175,3s le relecteur, 170,0s
    l'agent) est... juste EN DESSOUS de 180 -- mais le p95 (294,5-315,0s)
    est LARGEMENT au-dessus, confirmant le taux de ~9,6% de rouge mesure
    sur matchs vivants sous ce seuil. Avec le seuil corrige, ce meme p95
    reste frais."""
    ancien_seuil_refute = 180.0
    p95_relecteur = 294.5
    assert fraicheur(p95_relecteur, ancien_seuil_refute) == "perime"
    assert fraicheur(p95_relecteur, SEUIL_FRAICHEUR_SCORE_S) == "frais"


def test_seuil_score_detecte_un_score_reellement_fige():
    assert fraicheur(SEUIL_FRAICHEUR_SCORE_S + 1.0, SEUIL_FRAICHEUR_SCORE_S) == "perime"


def test_seuil_exchange_est_epingle():
    assert SEUIL_FRAICHEUR_EXCHANGE_S == 720.0


def test_seuil_exchange_couvre_la_dent_de_scie_et_le_retard_de_reception_mesures():
    """1 cycle documente (Live/books.py::EXCHANGE_PUBLICATION_PERIOD_SECONDS
    = 180 s, "mesuree exacte : mediane = p25 = p75") + p90 du retard de
    reception mesure independamment (307 s) = 487 s, le pire cas normal
    recompose : doit rester frais -- alors qu'il aurait ete perime sous
    l'ancien seuil unique de 30 s (52,7 % des trames deja mesurees perimees
    a la reception sous ce seuil-la)."""
    pire_cas_normal = 180.0 + 307.0
    assert pire_cas_normal > 30.0
    assert SEUIL_FRAICHEUR_EXCHANGE_S > pire_cas_normal
    assert fraicheur(pire_cas_normal, SEUIL_FRAICHEUR_EXCHANGE_S) == "frais"


def test_seuil_exchange_detecte_un_exchange_reellement_mort():
    assert fraicheur(SEUIL_FRAICHEUR_EXCHANGE_S + 1.0, SEUIL_FRAICHEUR_EXCHANGE_S) == "perime"


# --- books : PRIX et FLUX, deux questions, deux seuils (tour 4) ------------
#
# Le tour 3 a refute le seuil unique (3*227=681s, derive a tort de la
# cadence d'un bookmaker) : la vraie quantite est une loi de puissance sans
# plateau, pilotee par l'abandon d'un book, qu'aucun seuil fixe ne peut
# fermer. Le publieur a tranche en publiant DEUX colonnes : `age_books_s`
# (le prix, desormais plafonne a 180s a la source) et `age_books_flux_s`
# (le flux, jamais plafonne). Chiffres cites ci-dessous : rejeu du publieur,
# 2026-08-02/03, pas de 60s, n=13 498, matchs vivants.


def test_seuil_books_prix_est_epingle():
    assert SEUIL_FRAICHEUR_BOOKS_S == 180.0


def test_seuil_books_prix_egale_exactement_le_plafond_de_publication():
    """`age_books_s` est plafonne a 180s A LA SOURCE (Live/books.py::
    DEFAULT_MAX_AGE_SECONDS) : au-dela, la valeur elle-meme devient NULL,
    jamais "perimee" au sens de ce seuil -- rien ne peut jamais depasser
    180s pour ce flux tant que la valeur n'est pas NULL. Le seuil colle donc
    exactement au plafond, pas une marge choisie independamment."""
    assert SEUIL_FRAICHEUR_BOOKS_S == 180.0
    # Le pire cas mesure AVEC plafond (max=179s, borne par construction)
    # doit rester frais -- il est structurellement impossible qu'il ne le
    # soit pas, mais la mutation "seuil < 179" doit quand meme tomber.
    pire_cas_mesure_avec_plafond = 179.0
    assert fraicheur(pire_cas_mesure_avec_plafond, SEUIL_FRAICHEUR_BOOKS_S) == "frais"


def test_seuil_books_prix_detecte_un_prix_reellement_perime():
    assert fraicheur(SEUIL_FRAICHEUR_BOOKS_S + 1.0, SEUIL_FRAICHEUR_BOOKS_S) == "perime"


def test_seuil_books_flux_est_epingle():
    assert SEUIL_FRAICHEUR_BOOKS_FLUX_S == 600.0


def test_seuil_books_flux_couvre_le_p99_mesure_avec_marge():
    """Mesure du publieur sur `age_books_flux_s` (jamais plafonnee) : p99 =
    1 229s. Le seuil (600s) est SOUS ce p99 -- delibere : le publieur a
    mesure 2,4% de rouge a 600s contre 7,8% a 300s, et a choisi le taux le
    plus bas des deux options qu'il a testees, pas le p99 lui-meme (qui
    donnerait un seuil bien trop permissif pour un signal de mort de
    capteur)."""
    taux_a_600s = 0.024
    taux_a_300s = 0.078
    assert taux_a_600s < taux_a_300s
    assert SEUIL_FRAICHEUR_BOOKS_FLUX_S == 600.0


def test_seuil_books_flux_detecte_un_capteur_reellement_mort():
    assert fraicheur(SEUIL_FRAICHEUR_BOOKS_FLUX_S + 1.0, SEUIL_FRAICHEUR_BOOKS_FLUX_S) == "perime"


def test_ligne_reelle_books_saine_prix_et_flux_tous_deux_frais():
    """LIGNE_REELLE_BOOKS_SAINE (event_id 3801815, capturee le 2026-08-04) :
    un prix jeune (age_books_s=73,8s, sous 180) ET un flux jeune
    (age_books_flux_s=31,0s, sous 600) -- le cas sain ou les deux pastilles
    s'accordent."""
    assert fraicheur(LIGNE_REELLE_BOOKS_SAINE["age_books_s"], SEUIL_FRAICHEUR_BOOKS_S) == "frais"
    assert fraicheur(LIGNE_REELLE_BOOKS_SAINE["age_books_flux_s"], SEUIL_FRAICHEUR_BOOKS_FLUX_S) == "frais"


def test_ligne_reelle_books_flux_mort_distingue_prix_inconnu_de_capteur_mort():
    """LIGNE_REELLE_BOOKS_FLUX_MORT (event_id 3798175, capturee le
    2026-08-04) : PREUVE DIRECTE de la raison d'etre de la deuxieme
    colonne. `age_books_s` est NaN (aucun prix utilisable -- plafonne, donc
    NULL des que trop vieux : "inconnu", jamais "perime") ; `age_books_flux_s`
    vaut 611,8s, au-dela du seuil (600s) : "perime", le signal que le
    capteur de cotes semble mort. Une seule colonne (l'ancien `age_books_s`
    seul) ne pouvait jamais produire cette distinction : plafonnee, elle
    dit "inconnu" pour les DEUX cas (prix simplement absent, ou capteur
    mort depuis 10 minutes) -- exactement l'information que le publieur a
    perdue en plafonnant sans ajouter la deuxieme colonne."""
    age_prix = LIGNE_REELLE_BOOKS_FLUX_MORT["age_books_s"]
    age_flux = LIGNE_REELLE_BOOKS_FLUX_MORT["age_books_flux_s"]
    assert pd.isna(age_prix)
    assert fraicheur(age_prix, SEUIL_FRAICHEUR_BOOKS_S) == "inconnu"
    assert age_flux > SEUIL_FRAICHEUR_BOOKS_FLUX_S
    assert fraicheur(age_flux, SEUIL_FRAICHEUR_BOOKS_FLUX_S) == "perime"


def test_seuil_stats_est_epingle():
    assert SEUIL_FRAICHEUR_STATS_S == 900.0


def test_seuil_stats_couvre_le_p95_mesure_avec_marge():
    """Mesure directe (agent, 2026-08-03, NDJSON stats-2026-08-0*.ndjson.gz,
    3 064 lignes / 164 matchs / 2 896 ecarts) : p95 = 512,7 s -- un ordre de
    grandeur plus lent que le score, les statistiques de match se mettant a
    jour bien moins souvent que le score lui-meme."""
    p95_mesure = 512.7
    assert SEUIL_FRAICHEUR_STATS_S > p95_mesure
    assert fraicheur(p95_mesure, SEUIL_FRAICHEUR_STATS_S) == "frais"


def test_seuil_stats_detecte_des_stats_reellement_figees():
    assert fraicheur(SEUIL_FRAICHEUR_STATS_S + 1.0, SEUIL_FRAICHEUR_STATS_S) == "perime"


def test_ligne_reelle_mi_cycle_les_quatre_flux_sont_frais_avec_les_seuils_par_flux():
    """Preuve centrale du tour 2, sur donnees REELLES (LIGNE_REELLE_MI_CYCLE,
    prelevee le 2026-08-03, event_id 3798175) : un match SAIN dont les
    quatre ages depassent TOUS l'ancien seuil unique de 30 s. Sous l'ancien
    regime, les QUATRE pastilles rougissaient malgre un flux sain -- avec un
    seuil propre a chaque flux, aucune ne doit lire "perime"."""
    paires = [
        ("score", LIGNE_REELLE_MI_CYCLE["age_score_s"], SEUIL_FRAICHEUR_SCORE_S),
        ("exchange", LIGNE_REELLE_MI_CYCLE["age_exchange_s"], SEUIL_FRAICHEUR_EXCHANGE_S),
        ("books", LIGNE_REELLE_MI_CYCLE["age_books_s"], SEUIL_FRAICHEUR_BOOKS_S),
        ("stats", LIGNE_REELLE_MI_CYCLE["age_stats_s"], SEUIL_FRAICHEUR_STATS_S),
    ]
    for nom, age, seuil in paires:
        assert age > 30.0, f"{nom} : la demonstration exige un age reel > l'ancien seuil unique"
        assert fraicheur(age, seuil) == "frais", f"{nom} : devrait etre frais avec son seuil propre"


# --- publieur_arrete : le signalement en tete de page -----------------------
#
# NOTE : `lire_battement=lambda: None` (battement illisible) est passe
# explicitement dans les tests qui exercent le REPLI sur `updated_ts`, pour
# ne jamais toucher le vrai fichier /home/ubuntu/tennet_live_data/
# heartbeat-publish.json depuis une suite qui doit rester deterministe (son
# etat depend du publieur reellement en service sur la machine, hors du
# controle de ce test).
#
# Depuis le tour 3 (I1a), le battement est AUTORITAIRE des qu'il est
# lisible : `updated_ts` n'est plus consulte QUE quand `lire_battement`
# rend un battement illisible. Les tests ci-dessous exercent donc les DEUX
# chemins separement.


def test_publieur_arrete_quand_aucune_ligne_touchee_depuis_le_seuil():
    """Repli sur updated_ts (battement illisible)."""
    maintenant = 1_000_000.0
    df = pd.DataFrame([
        {"event_id": "1", "updated_ts": maintenant - SEUIL_PUBLIEUR_ARRETE_S - 1},
    ])
    assert publieur_arrete(df, maintenant=maintenant, lire_battement=lambda: None) is True


def test_publieur_pas_arrete_quand_une_ligne_est_recente():
    """Repli sur updated_ts (battement illisible)."""
    maintenant = 1_000_000.0
    df = pd.DataFrame([
        {"event_id": "1", "updated_ts": maintenant - SEUIL_PUBLIEUR_ARRETE_S - 1},
        {"event_id": "2", "updated_ts": maintenant - 1.0},
    ])
    assert publieur_arrete(df, maintenant=maintenant, lire_battement=lambda: None) is False


def test_publieur_arrete_ne_fabrique_pas_de_fausse_alerte_sans_aucun_signal():
    """Aucun match en cours ET aucun battement lisible : ni l'un ni l'autre
    des deux signaux ne prouve quoi que ce soit sur la sante du publieur --
    pas de fausse alerte plutot qu'un signal invente."""
    assert publieur_arrete(pd.DataFrame(), maintenant=1_000_000.0, lire_battement=lambda: None) is False
    assert publieur_arrete(pd.DataFrame({"autre": [1]}), maintenant=1_000_000.0, lire_battement=lambda: None) is False


def test_publieur_arrete_couvre_le_pire_intervalle_mesure_avec_marge():
    """Le pire intervalle reellement observe entre deux cycles du publieur
    EN SERVICE (10,19 s, mesure independante sur 78 cycles / 9 min, voir le
    commentaire de SEUIL_PUBLIEUR_ARRETE_S) doit rester tres en dessous du
    seuil, avec une marge large pour la derive documentee (l'intervalle
    grossit avec le nombre de matchs suivis).

    Remplace l'ancien garde-fou (`> 5.0`, dans tests/test_pages_live.py) qui
    n'assertait rien de reel : son nom promettait un lien avec la cadence du
    publieur qu'il ne verifiait pas (mutation SEUIL_PUBLIEUR_ARRETE_S = 5.1
    le laissait passer au vert)."""
    pire_intervalle_mesure_en_service = 10.19
    assert SEUIL_PUBLIEUR_ARRETE_S > 3 * pire_intervalle_mesure_en_service


def test_publieur_arrete_ne_fausse_pas_alarme_sur_le_pire_cycle_mesure():
    """Un cycle aussi lent que le pire mesure en service (10,19 s) est un
    hoquet, pas un deces : ne doit PAS declencher le signalement. Repli sur
    updated_ts (battement illisible)."""
    maintenant = 1_000_000.0
    df = pd.DataFrame([{"updated_ts": maintenant - 10.19}])
    assert publieur_arrete(df, maintenant=maintenant, lire_battement=lambda: None) is False


# --- publieur_arrete : repli sur updated_ts UNIQUEMENT si le battement est
# illisible (I2, complete par I1a au tour 3) ---------------------------------


def test_publieur_arrete_retombe_sur_le_battement_si_aucun_match_en_cours():
    """Sans match en cours, live_now ne peut rien attester par elle-meme :
    le repli est le battement de vie du process (heartbeat-publish.json
    cote PoC), qui existe independamment de la presence d'un match."""
    maintenant = 1_000_000.0
    battement_mort = {"ts": maintenant - SEUIL_BATTEMENT_ARRETE_S - 1}
    assert publieur_arrete(
        pd.DataFrame(), maintenant=maintenant, lire_battement=lambda: battement_mort,
    ) is True

    battement_vivant = {"ts": maintenant - 1.0}
    assert publieur_arrete(
        pd.DataFrame(), maintenant=maintenant, lire_battement=lambda: battement_vivant,
    ) is False


def test_publieur_arrete_ignore_les_matchs_termines_meme_tres_vieux_quand_le_battement_est_illisible():
    """Preuve de I4 (tour 1) dans son perimetre reduit depuis le tour 3 :
    depuis que le battement, quand il est LISIBLE, est devenu autoritaire
    (I1a), la distinction `en_cours` vs `matchs` ne peut plus changer la
    reponse QUE quand le battement est illisible -- c'est le seul cas
    restant ou ce test a un sens.

    Avec LIGNE_REELLE_FINISHED (prelevee le 2026-08-04, live_now jamais
    purgee avant 6h) comme SEULE ligne, en_cours (vide) et matchs (une
    ligne tres vieille) doivent rendre des reponses DIFFERENTES quand le
    battement est illisible."""
    matchs = pd.DataFrame([LIGNE_REELLE_FINISHED])
    en_cours = matchs[matchs["status"] == "InPlay"]
    assert en_cours.empty

    # en_cours (vide) : rien a lire, pas de fausse alerte.
    assert publieur_arrete(
        en_cours, maintenant=CAPTURE_TS_FINISHED, lire_battement=lambda: None,
    ) is False
    # matchs (la ligne terminee tres vieille) : lit a tort l'age de la
    # ligne terminee (~5 631 s > seuil) -> arrete a tort.
    assert publieur_arrete(
        matchs, maintenant=CAPTURE_TS_FINISHED, lire_battement=lambda: None,
    ) is True


# --- publieur_arrete : le battement AUTORITAIRE, veto compris (I1a, tour 3) -


def test_seuil_battement_arrete_est_epingle():
    assert SEUIL_BATTEMENT_ARRETE_S == 300.0


def test_seuil_battement_arrete_a_une_marge_confortable_sur_la_cadence_decriture():
    """Pas seulement la valeur relue (test ci-dessus) : Live/config.py::
    HEARTBEAT_SECONDS = 30.0 (documente, lu directement) est la cadence
    d'ECRITURE du fichier de battement lui-meme (Live.supervise.Heartbeat,
    cote PoC) -- le seuil D'INTERPRETATION doit rester tres au-dessus, sans
    quoi un battement simplement pas-encore-reecrit (jitter normal autour
    de cette cadence) declencherait une fausse alerte."""
    cadence_ecriture_documentee = 30.0
    assert SEUIL_BATTEMENT_ARRETE_S > 5 * cadence_ecriture_documentee


def test_battement_frais_oppose_son_veto_a_un_updated_ts_perime():
    """Correctif central de I1a : un battement FRAIS emporte un VETO sur ce
    que updated_ts pourrait dire, meme quand updated_ts, seul, aurait dit
    "arrete". Scenario mesure en service : une ligne InPlay dont updated_ts
    est vieux de 90s (au-dela de SEUIL_PUBLIEUR_ARRETE_S=45s, dans la
    fenetre de ~75s ou le publieur n'a pas encore reetiquete "Finished",
    LIVE_STALE_SECONDS=120 cote publieur) alors que le battement, lui, n'a
    qu'1s -- publieur clairement vivant."""
    maintenant = 1_000_000.0
    df = pd.DataFrame([{"updated_ts": maintenant - 90.0}])
    battement_frais = {"ts": maintenant - 1.0}
    # Sans veto (ancien comportement), updated_ts seul aurait dit "arrete" :
    assert publieur_arrete(df, maintenant=maintenant, lire_battement=lambda: None) is True
    # Avec le battement frais, le verdict est oppose :
    assert publieur_arrete(df, maintenant=maintenant, lire_battement=lambda: battement_frais) is False


def test_battement_interprete_avec_son_propre_seuil_pas_celui_dupdated_ts():
    """publieur_arrete() prend DEUX seuils distincts (`seuil` pour le repli
    updated_ts=45s, `seuil_battement` pour le battement=300s) : une confusion
    entre les deux (ex. le battement compare a 45s au lieu de 300s) ne serait
    PAS attrapee par des batttements tres frais (~1s, sous les deux seuils)
    ou tres vieux (des heures, au-dessus des deux) -- seule une valeur ENTRE
    45 et 300s distingue laquelle des deux constantes est reellement
    utilisee. 100s : au-dela de `seuil` (45), en-deca de `seuil_battement`
    (300)."""
    maintenant = 1_000_000.0
    battement_entre_les_deux_seuils = {"ts": maintenant - 100.0}
    assert publieur_arrete(
        pd.DataFrame(), maintenant=maintenant,
        lire_battement=lambda: battement_entre_les_deux_seuils,
    ) is False, "100s est sous SEUIL_BATTEMENT_ARRETE_S (300s) : pas arrete"


def test_battement_perime_conclut_a_larret_sans_consulter_updated_ts():
    """Symetrique : un battement PERIME suffit a conclure "arrete", meme si
    (improbablement) updated_ts semblait frais -- le battement mesure
    directement la sante du process, updated_ts n'est qu'un proxy."""
    maintenant = 1_000_000.0
    df = pd.DataFrame([{"updated_ts": maintenant - 1.0}])  # updated_ts FRAIS
    battement_perime = {"ts": maintenant - SEUIL_BATTEMENT_ARRETE_S - 1}
    assert publieur_arrete(df, maintenant=maintenant, lire_battement=lambda: battement_perime) is True


# --- publieur_ecritures_refusees : "vivant mais n'ecrit plus" (IMPORTANT 1,
# tour 5) -- regression introduite PAR le veto du battement (I1a, tour 3) ---
#
# Sonde du relecteur qui a REVELE le defaut : ligne InPlay gelee depuis 1h +
# battement {"ts": now-1, "state": {"n_echecs": 12}} -> avant ce correctif,
# publieur_arrete() rendait False (correctement : le PROCESS n'est pas mort)
# mais RIEN d'autre ne signalait que les ecritures, elles, echouaient --
# alors que n_echecs est dans le battement qu'on vient de lire.


def test_publieur_ecritures_refusees_quand_n_echecs_positif():
    """Signal PRIORITAIRE et suffisant : state.n_echecs > 0 dans un
    battement par ailleurs frais."""
    maintenant = 1_000_000.0
    battement = {"ts": maintenant - 1.0, "state": {"n_echecs": 12}}
    df = pd.DataFrame([{"updated_ts": maintenant - 3600.0}])
    assert publieur_ecritures_refusees(df, maintenant=maintenant, lire_battement=lambda: battement) is True


def test_publieur_ecritures_pas_refusees_quand_n_echecs_documente_a_zero():
    """CONTRE-PREUVE, la plus importante de cette section : un VRAI
    battement documente n_echecs a CHAQUE cycle, y compris quand il vaut 0
    (Publieur.tick() l'inclut toujours). n_echecs=0 est une reponse
    DEFINITIVE ("aucun echec ce cycle"), pas une absence d'information --
    ne doit PAS retomber sur updated_ts par-dessus, meme si une ligne EN
    COURS semble tres perimee (elle peut l'etre pour une raison benigne,
    ex. le match vient de finir -- exactement le cas qu'I1a distingue deja).
    Premiere version de cette fonction : cette assertion cassait (le repli
    sur updated_ts se declenchait quand meme), regression trouvee en
    corrigeant deux tests AppTest devenus rouges (voir test_pages_live.py)."""
    maintenant = 1_000_000.0
    battement = {"ts": maintenant - 1.0, "state": {"n_echecs": 0}}
    df = pd.DataFrame([{"updated_ts": maintenant - 3600.0}])  # tres perimee
    assert publieur_ecritures_refusees(df, maintenant=maintenant, lire_battement=lambda: battement) is False


def test_publieur_ecritures_refusees_retombe_sur_updated_ts_si_n_echecs_non_documente():
    """Repli, SEULEMENT si le battement ne documente pas n_echecs du tout
    (format degrade) : updated_ts redevient le meilleur signal disponible,
    avec le meme seuil (45s) que le repli de publieur_arrete()."""
    maintenant = 1_000_000.0
    battement_sans_state = {"ts": maintenant - 1.0}
    df_perime = pd.DataFrame([{"updated_ts": maintenant - SEUIL_PUBLIEUR_ARRETE_S - 1}])
    df_frais = pd.DataFrame([{"updated_ts": maintenant - 1.0}])
    assert publieur_ecritures_refusees(
        df_perime, maintenant=maintenant, lire_battement=lambda: battement_sans_state,
    ) is True
    assert publieur_ecritures_refusees(
        df_frais, maintenant=maintenant, lire_battement=lambda: battement_sans_state,
    ) is False


def test_publieur_ecritures_refusees_ne_chevauche_pas_publieur_arrete():
    """Quand le battement est illisible ou perime, c'est le domaine de
    publieur_arrete(), pas de celui-ci : doit rendre False, meme avec des
    lignes tres perimees, pour ne jamais afficher DEUX bandeaux
    contradictoires en meme temps."""
    maintenant = 1_000_000.0
    df = pd.DataFrame([{"updated_ts": maintenant - 3600.0}])
    assert publieur_ecritures_refusees(df, maintenant=maintenant, lire_battement=lambda: None) is False
    battement_perime = {"ts": maintenant - SEUIL_BATTEMENT_ARRETE_S - 1, "state": {"n_echecs": 12}}
    assert publieur_ecritures_refusees(df, maintenant=maintenant, lire_battement=lambda: battement_perime) is False


# --- IMPORTANT 2 (tour 5) : epingler quel FICHIER porte quel diagnostic ----
#
# Mutation du relecteur : CHEMIN_BATTEMENT_PUBLIEUR <-> heartbeat-score.json
# (ou l'inverse) survivait a 89/89 -- tous les tests injectent lire_battement,
# rien n'epinglait le nom de fichier reel derriere chaque chemin par defaut.
# Un mot echange fait accuser le publieur quand c'est le capteur de score
# qui meurt (ou l'inverse) : exactement I1b, rouvert silencieusement.


def test_chemin_battement_publieur_pointe_vers_heartbeat_publish():
    assert CHEMIN_BATTEMENT_PUBLIEUR.name == "heartbeat-publish.json"


def test_chemin_battement_score_pointe_vers_heartbeat_score():
    assert CHEMIN_BATTEMENT_SCORE.name == "heartbeat-score.json"


# --- capteur_score_mort : distinguer "publieur arrete" de "capteur de
# score muet" (I1b, tour 3) ---------------------------------------------------


def test_capteur_score_mort_quand_le_battement_score_est_perime():
    """Battement PRESENT mais vieux (le capteur a plante, le fichier n'est
    plus reecrit) : df n'est meme pas consulte, l'age du battement suffit."""
    maintenant = 1_000_000.0
    battement_mort = {"ts": maintenant - SEUIL_BATTEMENT_ARRETE_S - 1}
    assert capteur_score_mort(
        pd.DataFrame(), maintenant=maintenant, lire_battement=lambda: battement_mort,
    ) is True


def test_capteur_score_pas_mort_quand_le_battement_score_est_frais():
    maintenant = 1_000_000.0
    battement_vivant = {"ts": maintenant - 1.0}
    assert capteur_score_mort(
        pd.DataFrame(), maintenant=maintenant, lire_battement=lambda: battement_vivant,
    ) is False


def test_capteur_score_mort_ne_fabrique_pas_de_fausse_alerte_si_present_mais_illisible():
    """Battement PRESENT mais illisible (JSON corrompu, permissions) :
    reste ambigu, aucune semantique documentee pour ce cas -- contrairement
    a l'absence (voir les tests ci-dessous). Pas de fausse alerte."""
    assert capteur_score_mort(
        pd.DataFrame([{"updated_ts": 1_000_000.0 - 10_000.0}]),
        maintenant=1_000_000.0, lire_battement=lambda: None,
        est_absent=lambda: False,  # present, mais lire_battement echoue quand meme
    ) is False


# --- capteur_score_mort : l'ABSENCE d'un battement (tour 6) -----------------
#
# Live/supervise.py::Heartbeat.clear() (depot TeNNetPy) retire le fichier a
# l'arret PROPRE d'un capteur -- l'absence est un troisieme etat documente
# ("arrete proprement"), pas un synonyme d'"illisible". Premiere version de
# cette fonction (tours 3-5) ne le distinguait pas : un capteur de score
# arrete proprement (le mode d'ARRET NORMAL, pas un cas de bord) ne
# declenchait donc jamais aucun bandeau -- trouve par la revue de cloture en
# sondant `capteur_score_mort(lire_battement=lambda: None)` directement.


def test_capteur_score_mort_absent_et_corrobore_par_updated_ts_gele():
    """Battement ABSENT + lignes EN COURS gelees (le symptome exact d'I1b :
    Publieur._marquer_termines refuse de reetiqueter tant que le capteur de
    score est mort) -> arret propre CONFIRME."""
    maintenant = 1_000_000.0
    en_cours_figees = pd.DataFrame([{"updated_ts": maintenant - 10_000.0}])
    assert capteur_score_mort(
        en_cours_figees, maintenant=maintenant,
        lire_battement=lambda: None, est_absent=lambda: True,
    ) is True


def test_capteur_score_mort_absent_mais_sans_corroboration_reste_indetermine():
    """PREUVE CENTRALE du tour 6 : battement ABSENT mais AUCUNE ligne en
    cours pour corroborer (ex. tout premier demarrage du systeme, avant que
    le tout premier battement n'ait jamais ete ecrit -- le fichier est
    absent sans qu'aucun capteur ne soit jamais tombe). Ne doit PAS hurler :
    l'absence seule, sans second signal, reste indeterminee -- exactement
    la nuance demandee ("absence + rien du tout = indetermine")."""
    assert capteur_score_mort(
        pd.DataFrame(), maintenant=1_000_000.0,
        lire_battement=lambda: None, est_absent=lambda: True,
    ) is False


def test_capteur_score_mort_absent_avec_lignes_encore_fraiches_reste_indetermine():
    """Meme id que ci-dessus avec une nuance : des lignes EN COURS existent
    mais sont encore fraiches (le capteur vient peut-etre de demarrer, ou le
    fichier n'a pas encore ete ecrit une premiere fois) -- pas de
    corroboration, pas de fausse alerte."""
    maintenant = 1_000_000.0
    en_cours_fraiches = pd.DataFrame([{"updated_ts": maintenant - 1.0}])
    assert capteur_score_mort(
        en_cours_fraiches, maintenant=maintenant,
        lire_battement=lambda: None, est_absent=lambda: True,
    ) is False


def test_publieur_vivant_et_capteur_score_mort_sont_bien_deux_diagnostics_distincts():
    """Preuve directe du scenario I1b : le publieur bat normalement
    (heartbeat-publish frais) PENDANT que le capteur de score s'est tu
    (heartbeat-score perime -- ici, present mais vieux) -- publieur_arrete()
    doit rester False (le publieur n'est pas coupable) et
    capteur_score_mort() doit devenir True (lui, si) : deux diagnostics
    simultanement vrais dans des sens opposes, pas un seul booleen qui les
    confondrait."""
    maintenant = 1_000_000.0
    battement_publieur_frais = {"ts": maintenant - 1.0}
    battement_score_mort = {"ts": maintenant - SEUIL_BATTEMENT_ARRETE_S - 1}
    # Des lignes InPlay figees depuis longtemps (le symptome visible cote
    # page), qui a elles seules auraient pu faire accuser le publieur.
    en_cours_figees = pd.DataFrame([{"updated_ts": maintenant - 10_000.0}])

    assert publieur_arrete(
        en_cours_figees, maintenant=maintenant,
        lire_battement=lambda: battement_publieur_frais,
    ) is False
    assert capteur_score_mort(
        en_cours_figees, maintenant=maintenant,
        lire_battement=lambda: battement_score_mort,
    ) is True


# --- battement_absent -------------------------------------------------------


def test_battement_absent_vrai_si_aucun_fichier(tmp_path):
    assert battement_absent(tmp_path / "n_existe_pas.json") is True


def test_battement_absent_faux_si_le_fichier_existe(tmp_path):
    chemin = tmp_path / "heartbeat-score.json"
    chemin.write_text("{}", encoding="utf-8")
    assert battement_absent(chemin) is False


def test_battement_absent_faux_meme_si_le_contenu_est_illisible(tmp_path):
    """Distinction centrale du tour 6 : un fichier PRESENT mais corrompu
    n'est PAS "absent" -- battement_absent() ne detecte que l'ABSENCE de
    fichier, pas l'echec de lecture de son contenu."""
    chemin = tmp_path / "casse.json"
    chemin.write_text("pas du json valide {{{", encoding="utf-8")
    assert battement_absent(chemin) is False
    assert lire_battement_publieur(chemin) is None  # illisible, mais present


# --- lire_battement_publieur / age_du_battement ------------------------------


def test_lire_battement_publieur_rend_none_si_fichier_absent(tmp_path):
    assert lire_battement_publieur(tmp_path / "n_existe_pas.json") is None


def test_lire_battement_publieur_rend_none_si_json_illisible(tmp_path):
    chemin = tmp_path / "casse.json"
    chemin.write_text("pas du json valide {{{", encoding="utf-8")
    assert lire_battement_publieur(chemin) is None


def test_lire_battement_publieur_lit_un_battement_valide(tmp_path):
    """Le contenu vient du VRAI fichier ecrit par Live.supervise.Heartbeat
    sur cette machine (BATTEMENT_REEL_PUBLIEUR, fige le 2026-08-03), rejoue
    depuis un fichier temporaire pour rester deterministe."""
    import json
    chemin = tmp_path / "heartbeat-publish.json"
    chemin.write_text(json.dumps(BATTEMENT_REEL_PUBLIEUR), encoding="utf-8")
    battement = lire_battement_publieur(chemin)
    assert battement == BATTEMENT_REEL_PUBLIEUR


def test_age_du_battement_reel_est_positif_et_fini():
    age = age_du_battement(BATTEMENT_REEL_PUBLIEUR, maintenant=BATTEMENT_REEL_PUBLIEUR["ts"] + 12.5)
    assert age == 12.5


def test_age_du_battement_absent_ou_sans_ts_reste_inconnu():
    assert age_du_battement(None) is None
    assert age_du_battement({}) is None
    assert age_du_battement({"ts": "pas-un-nombre"}) is None


def test_age_du_battement_ts_nan_reste_inconnu():
    """`json.loads`/`json.dumps` de la stdlib acceptent NaN comme extension
    non standard (`json.dumps(float("nan"))` ecrit litteralement `NaN`) :
    un `ts` NaN est donc atteignable depuis un vrai heartbeat-publish.json,
    pas seulement en theorie. `float(float("nan"))` ne leve PAS -- seul
    `pd.isna` l'attrape ; la moitie `is None` du garde-fou ne suffit pas."""
    assert age_du_battement({"ts": float("nan")}) is None


def test_age_du_battement_futur_ne_devient_pas_negatif():
    maintenant = 1_000_000.0
    assert age_du_battement({"ts": maintenant + 50.0}, maintenant) == 0.0


def test_le_tableau_des_matchs_separe_en_cours_et_termines():
    """Verifie l'association LIGNE A LIGNE, pas seulement que les deux valeurs
    existent quelque part : `set(...) == {True, False}` passerait encore si
    le sens de l'association etait inverse (le match en cours marque
    termine et inversement) -- une inversion pourtant visible a l'ecran."""
    lignes = pd.DataFrame([
        {"event_id": "1", "status": "InPlay", "updated_ts": 1000.0},
        {"event_id": "2", "status": "Finished", "updated_ts": 999.0},
    ])
    df = charger_matchs(lecteur=lambda schema, query: lignes)
    assert df.set_index("event_id")["en_cours"].to_dict() == {
        "1": True, "2": False,
    }


def test_une_base_vide_rend_un_tableau_vide_et_ne_leve_pas():
    df = charger_matchs(lecteur=lambda schema, query: pd.DataFrame())
    assert df.empty


# --- ORDER BY : promesses non couvertes (MINEUR 2, tour 5) -----------------
#
# charger_matchs() promet "les plus recemment mis a jour d'abord" et
# charger_serie() promet "dans l'ordre du temps" -- deux promesses tenues
# par le texte SQL envoye au lecteur, jamais verifiees directement : les
# fixtures des autres tests sont deja pre-triees a la main, donc une
# mutation qui retirerait l'ORDER BY de la requete SQL ne casserait rien
# d'observable dans cette suite (le faux lecteur ignore de toute facon
# l'ordre demande). On capture ici la requete ELLE-MEME.


def test_charger_matchs_demande_lordre_du_plus_recent_au_plus_ancien():
    captures = {}

    def lecteur(schema, query):
        captures["query"] = query
        return pd.DataFrame()

    charger_matchs(lecteur=lecteur)
    assert "ORDER BY updated_ts DESC" in captures["query"]


def test_charger_serie_demande_lordre_du_temps():
    captures = {}

    def lecteur(schema, query):
        captures["query"] = query
        return pd.DataFrame()

    charger_serie("123", lecteur=lecteur)
    assert "ORDER BY ts" in captures["query"]


def test_la_serie_est_mise_en_forme_longue_pour_le_graphique():
    """Altair superpose des series : il lui faut une colonne « serie » et une
    colonne « cote », pas six colonnes cote a cote."""
    large = pd.DataFrame([{
        "ts": 1000.0, "back_odds_a": 1.4, "lay_odds_a": 1.42,
        "back_odds_b": 3.3, "lay_odds_b": 3.4,
        "book_odds_a": 1.45, "book_odds_b": 3.2,
    }])
    longue = serie_longue(large)
    assert set(longue.columns) >= {"ts", "serie", "cote"}
    assert len(longue) == 6


def test_les_cotes_absentes_ne_produisent_pas_de_point():
    """Un match sans marche s'affiche quand meme, avec son score : l'absence
    de cote est un fait, pas une erreur -- mais elle ne doit pas dessiner un
    point a zero."""
    large = pd.DataFrame([{
        "ts": 1000.0, "back_odds_a": None, "lay_odds_a": None,
        "back_odds_b": None, "lay_odds_b": None,
        "book_odds_a": 1.45, "book_odds_b": None,
    }])
    assert len(serie_longue(large)) == 1


def test_seuls_les_instants_marques_deviennent_des_reperes():
    df = pd.DataFrame([
        {"ts": 1.0, "evenement": None},
        {"ts": 2.0, "evenement": "fin_de_jeu"},
        {"ts": 3.0, "evenement": "fin_de_set"},
    ])
    ev = evenements(df)
    assert list(ev["ts"]) == [2.0, 3.0]


def test_aucun_repere_de_break_n_est_jamais_produit():
    """Le champ serveur de la source se contredit dans 13 % des jeux : le
    publieur ne marque jamais de break, et la page n'en invente pas."""
    df = pd.DataFrame([{"ts": 1.0, "evenement": "break"}])
    assert "break" not in set(evenements(df)["evenement"])


def test_serie_longue_sans_colonne_ts_degrade_au_lieu_de_lever():
    """`ts` est garanti par le ORDER BY de charger_serie en usage normal,
    mais l'interface ne doit jamais dependre de cette garantie pour rester
    debout : point du registre, deja releve en CRITIQUE sur la tache 8."""
    df = pd.DataFrame([{"back_odds_a": 1.5}])
    resultat = serie_longue(df)
    assert resultat.empty
    assert list(resultat.columns) == ["ts", "serie", "cote"]


def test_evenements_sans_colonne_ts_degrade_au_lieu_de_lever():
    df = pd.DataFrame([{"evenement": "fin_de_jeu"}])
    resultat = evenements(df)
    assert resultat.empty
    assert list(resultat.columns) == ["ts", "evenement"]


# --- en_datetime : l'axe temporel en secondes epoch brutes (I4, tour 3) ----


def test_en_datetime_convertit_les_secondes_epoch():
    """1785794036.9001677 (vu litteralement dans le tableau point par point
    avant ce correctif) doit devenir un timestamp lisible, pas rester un
    flottant a 10 chiffres."""
    df = pd.DataFrame([{"ts": 1785794036.9001677, "score": "6-4"}])
    resultat = en_datetime(df)
    assert pd.api.types.is_datetime64_any_dtype(resultat["ts"])
    # 23:53 et non 21:53 : cette colonne est AFFICHEE, donc elle est a
    # l'heure de PARIS depuis le 2026-08-11. L'ancienne valeur etait de
    # l'UTC -- le defaut, epingle par son propre test.
    assert resultat["ts"].iloc[0] == pd.Timestamp("2026-08-03 23:53:56.900167704")


def test_en_datetime_naltere_pas_loriginal():
    """Copie, pas mutation en place : serie_longue()/evenements() restent
    utilisables sur les donnees BRUTES ailleurs dans la page (le graphique
    et le tableau appellent chacun en_datetime() separement sur leur propre
    DataFrame)."""
    original = pd.DataFrame([{"ts": 1785794036.9001677}])
    en_datetime(original)
    assert original["ts"].iloc[0] == 1785794036.9001677


def test_en_datetime_degrade_sans_colonne_ts_ou_dataframe_vide():
    assert en_datetime(pd.DataFrame(), "ts").empty
    sans_ts = pd.DataFrame([{"score": "6-4"}])
    resultat = en_datetime(sans_ts)
    assert "ts" not in resultat.columns
    assert list(resultat["score"]) == ["6-4"]


# --- charger_serie : nettoyage du litteral SQL (mineur #3, tour 3) ---------


def test_charger_serie_retire_les_antislashs_de_levent_id():
    """`event_id` vient de st.query_params : modifiable par n'importe qui
    dans l'URL. Un event_id finissant par un antislash echappait la quote
    fermante (`'...\\' ORDER BY...`) et produisait une erreur de syntaxe SQL
    -- pas une injection, mais une erreur affichee comme "Base de donnees
    injoignable" pour une cause qui n'est pas celle-la. Verifie que la
    requete envoyee au lecteur ne porte plus l'antislash."""
    captures = {}

    def lecteur(schema, query):
        captures["query"] = query
        return pd.DataFrame()

    charger_serie("123\\", lecteur=lecteur)
    assert "\\" not in captures["query"]
    # La requete est passee de `= 'x'` a `IN ('x', ...)` pour lire d'un coup
    # les series des PLUSIEURS event_id d'un meme match. L'intention du test
    # ne change pas : l'identifiant nettoye doit apparaitre, l'antislash non.
    assert "IN ('123')" in captures["query"]


def test_le_lecteur_par_defaut_restaure_vraiment_le_repertoire_courant(
    monkeypatch, tmp_path
):
    """db_utils/db_utils.py fait un os.chdir(project_path) A L'IMPORT
    (ligne 34). _lecteur_par_defaut() doit rendre la main SANS avoir deplace
    le repertoire courant de son appelant.

    DEUX faux departs deja payes sur ce test, tous deux VERTS ET VIDES :

    1. commit 145b76d : il injectait un FAUX `db_utils.db_utils` deja present
       dans sys.modules, donc `from db_utils.db_utils import read_sql_query`
       ne declenchait AUCUN import reel -- ni chdir, ni rien a restaurer.
    2. version suivante : elle forcait bien une reimportation fraiche, mais
       partait du repertoire courant de pytest -- la RACINE DU PROJET, qui
       est exactement la destination du chdir. Le repertoire ne bougeait donc
       jamais, et l'assertion ne pouvait pas echouer. Verifie par mutation :
       le test restait vert avec le try/finally de _lecteur_par_defaut()
       entierement retire.

    D'ou le `os.chdir(tmp_path)` ci-dessous : en partant d'AILLEURS que la
    racine, l'import deplace reellement le repertoire, et l'assertion
    discrimine. Sans le try/finally, ce test rougit."""
    import os
    import sys

    import live_data

    origine = os.getcwd()
    for nom in ("db_utils.globals", "db_utils.db_utils", "db_utils"):
        monkeypatch.delitem(sys.modules, nom, raising=False)

    try:
        # Partir d'ailleurs que la racine : c'est CE detail qui rend le test
        # capable de rougir.
        os.chdir(tmp_path)
        depart = os.getcwd()

        lire = live_data._lecteur_par_defaut()

        assert os.getcwd() == depart, (
            "le repertoire courant n'a pas ete restaure apres l'import reel "
            "de db_utils.db_utils (qui chdir vers la racine du projet a "
            f"l'import) : attendu {depart}, obtenu {os.getcwd()}"
        )
        assert callable(lire)
    finally:
        os.chdir(origine)


# --- points_uniques : le tableau point par point ne montre plus de doublons ---
#
# Constate a l'usage sur un export du 2026-08-04 : le tableau affichait
# plusieurs fois de suite le meme score et les memes points. Ce ne sont PAS
# des doublons en base -- ces lignes portent des cotes differentes, et
# live_series existe pour tracer les prix -- mais le tableau n'affiche pas
# les cotes, donc elles s'y lisent comme des repetitions pures.


def _serie(lignes):
    return pd.DataFrame(
        lignes, columns=["ts", "score", "points", "evenement"]
    )


def test_les_repetitions_a_score_inchange_sont_repliees():
    df = _serie([
        (10.0, "1-0", "15-0", None),
        (20.0, "1-0", "15-0", None),   # un prix a bouge, le jeu non
        (30.0, "1-0", "15-0", None),
        (40.0, "1-0", "30-0", None),
    ])
    out = points_uniques(df)
    assert list(out["ts"]) == [10.0, 40.0], out.to_dict("records")


def test_c_est_la_PREMIERE_occurrence_qui_date_le_point():
    """Garder la derniere daterait le point de plusieurs minutes apres qu'il
    a ete joue : sur l'export reel, un etat reste affiche pendant que seuls
    les prix bougent."""
    df = _serie([
        (100.0, "2-1", "0-0", "fin_de_jeu"),
        (250.0, "2-1", "0-0", None),
    ])
    out = points_uniques(df)
    assert list(out["ts"]) == [100.0]


def test_un_evenement_porte_par_une_ligne_suivante_n_est_pas_perdu():
    """Le publieur pose le marqueur sur la ligne ou le score a change ; rien
    ne garantit que ce soit la premiere de la suite, et le perdre effacerait
    une fin de jeu du tableau."""
    df = _serie([
        (10.0, "2-1", "0-0", None),
        (20.0, "2-1", "0-0", "fin_de_jeu"),
    ])
    out = points_uniques(df)
    assert len(out) == 1
    assert out.iloc[0]["evenement"] == "fin_de_jeu"


def test_deux_scores_absents_de_suite_ne_font_pas_deux_lignes():
    """NaN n'est pas egal a lui-meme : sans normalisation, chaque ligne a
    score NULL formerait sa propre suite et le repliement ne servirait a
    rien la ou il sert le plus."""
    df = _serie([
        (10.0, float("nan"), float("nan"), None),
        (20.0, float("nan"), float("nan"), None),
        (30.0, "1-0", "0-0", None),
    ])
    out = points_uniques(df)
    assert list(out["ts"]) == [10.0, 30.0], out.to_dict("records")


def test_un_etat_qui_revient_plus_tard_reste_une_ligne_distincte():
    """Le repliement porte sur les suites CONSECUTIVES : un meme score revu
    apres un autre etat est un fait de la source (score qui recule), pas une
    repetition d'affichage -- l'effacer masquerait l'anomalie."""
    df = _serie([
        (10.0, "1-1", "40-30", None),
        (20.0, "2-1", "0-0", "fin_de_jeu"),
        (30.0, "1-1", "40-30", None),
        (40.0, "2-1", "0-0", "fin_de_jeu"),
    ])
    out = points_uniques(df)
    assert list(out["ts"]) == [10.0, 20.0, 30.0, 40.0]


def test_serie_vide_ou_sans_colonnes_ne_leve_pas():
    assert points_uniques(pd.DataFrame()).empty
    assert points_uniques(None).empty
    # Sans score ni points il n'y a rien a replier : la vue est rendue telle
    # quelle, pas fondue en une seule ligne.
    seul = pd.DataFrame({"ts": [1.0, 2.0]})
    assert len(points_uniques(seul)) == 2


# --- fusionner_doublons : la source emet parfois plusieurs event_id ---
#
# Constate a l'usage sur la page « En direct » : le meme match apparaissait
# deux fois. Mesure du 2026-08-04 : 5 groupes en doublon sur 16 lignes de
# live_now, dont un a TROIS identifiants -- toutes les lignes d'un groupe
# partageant le meme id_market, donc le meme match selon l'exchange.


def _ligne(**kw):
    base = {
        "event_id": "1", "id_market": "1.2600", "participant1": "A",
        "participant2": "B", "league": "Test Open", "status": "InPlay",
        "score": "1-0", "points": "0-0", "back_odds_a": None,
        "lay_odds_a": None, "book_odds_a": None, "age_score_s": 10.0,
        "age_exchange_s": None, "age_books_s": None, "age_stats_s": None,
        "updated_ts": 1000.0,
    }
    base.update(kw)
    return base


def test_deux_event_id_du_meme_match_ne_font_plus_qu_une_ligne():
    df = pd.DataFrame([_ligne(event_id="1"), _ligne(event_id="2")])
    out = fusionner_doublons(df)
    assert len(out) == 1
    assert set(out.iloc[0]["event_ids"].split(",")) == {"1", "2"}


def test_la_fusion_prend_CHAQUE_flux_a_sa_ligne_la_plus_fraiche():
    """Mesure sur deux matchs en direct : aucune des deux lignes ne domine
    l'autre -- l'une portait le score le plus frais, l'autre les cotes
    bookmakers et les stats. En choisir une seule perdrait de la donnee."""
    df = pd.DataFrame([
        _ligne(event_id="1", age_score_s=2.0, score="1-0", points="40-40",
               back_odds_a=1.56, age_exchange_s=6.0),
        _ligne(event_id="2", age_score_s=33.0, score="1-0", points="30-30",
               back_odds_a=1.56, age_exchange_s=6.0,
               book_odds_a=1.37, age_books_s=70.0, age_stats_s=69.0),
    ])
    out = fusionner_doublons(df)
    assert len(out) == 1
    r = out.iloc[0]
    assert r["points"] == "40-40", "le score doit venir de la ligne la plus fraiche"
    assert r["age_score_s"] == 2.0
    assert r["book_odds_a"] == 1.37, "les cotes books ne doivent pas etre perdues"
    assert r["age_books_s"] == 70.0
    assert r["age_stats_s"] == 69.0


def test_un_age_ABSENT_ne_gagne_jamais_contre_un_age_renseigne():
    """« ce flux n'a jamais parle » n'est pas « il a parle il y a zero
    seconde » : la confusion que tout ce paquet combat, et qui ferait ici
    preferer une ligne muette a une ligne renseignee."""
    df = pd.DataFrame([
        _ligne(event_id="1", book_odds_a=None, age_books_s=None),
        _ligne(event_id="2", book_odds_a=2.5, age_books_s=90.0),
    ])
    out = fusionner_doublons(df)
    assert out.iloc[0]["book_odds_a"] == 2.5
    assert out.iloc[0]["age_books_s"] == 90.0


def test_deux_matchs_DIFFERENTS_ne_sont_jamais_fusionnes():
    df = pd.DataFrame([
        _ligne(event_id="1", id_market="1.2600", participant1="A", participant2="B"),
        _ligne(event_id="2", id_market="1.2601", participant1="C", participant2="D"),
    ])
    assert len(fusionner_doublons(df)) == 2


def test_deux_lignes_SANS_identite_restent_separees():
    """Sans marche apparie NI paire de joueurs, on ne sait pas de quel match
    il s'agit : deux lignes anonymes partageraient une cle vide et seraient
    fusionnees -- deux rencontres reduites a une. Defaut attrape par la suite
    existante le 2026-08-04."""
    df = pd.DataFrame([
        _ligne(event_id="1", id_market=None, participant1=None,
               participant2=None, league=None, status="InPlay"),
        _ligne(event_id="2", id_market=None, participant1=None,
               participant2=None, league=None, status="Finished"),
    ])
    out = fusionner_doublons(df)
    assert len(out) == 2, out.to_dict("records")


def test_meme_marche_mais_joueurs_differents_ne_fusionne_pas():
    """Un marche peut etre reutilise d'un jour a l'autre (cf.
    _flag_reused_markets cote PoC) : les noms sont le second garde-fou."""
    df = pd.DataFrame([
        _ligne(event_id="1", id_market="1.2600", participant1="A", participant2="B"),
        _ligne(event_id="2", id_market="1.2600", participant1="C", participant2="D"),
    ])
    assert len(fusionner_doublons(df)) == 2


def test_charger_serie_lit_plusieurs_event_id_dans_l_ordre_du_temps():
    captures = {}

    def lecteur(schema, query):
        captures["query"] = query
        return pd.DataFrame()

    charger_serie("1,2", lecteur=lecteur)
    assert "IN ('1', '2')" in captures["query"], captures["query"]
    # ORDER BY sur `ts` SEUL : les series de deux identifiants d'un meme match
    # doivent s'entrelacer dans le temps, pas se suivre bout a bout -- sans
    # quoi la courbe reviendrait en arriere au milieu du graphique.
    assert captures["query"].rstrip().endswith("ORDER BY ts")
    charger_serie(["3", "4"], lecteur=lecteur)
    assert "IN ('3', '4')" in captures["query"], captures["query"]


def test_charger_matchs_FUSIONNE_reellement(monkeypatch):
    """Le cablage, pas seulement la fonction : desactiver l'appel a
    `fusionner_doublons` dans `charger_matchs` laissait la suite verte
    (mutation Q1, 2026-08-04). C'est pourtant ce chemin-la que les deux pages
    empruntent."""
    brut = pd.DataFrame([_ligne(event_id="1"), _ligne(event_id="2")])
    out = charger_matchs(lecteur=lambda schema, query: brut)
    assert len(out) == 1, out.to_dict("records")
    assert "event_ids" in out.columns
    assert set(out.iloc[0]["event_ids"].split(",")) == {"1", "2"}
    # `en_cours` doit etre calcule APRES la fusion, sur le statut retenu.
    assert bool(out.iloc[0]["en_cours"]) is True


def test_l_identifiant_retenu_est_celui_au_score_le_plus_frais():
    """C'est lui que « Voir le detail » ouvre en premier et qui s'affiche
    dans la liste : le prendre au hasard dans le groupe designerait la vue
    la plus perimee du match (mutation Q4, 2026-08-04)."""
    # Les DEUX ordres, sans quoi « prendre la premiere » ou « prendre la
    # derniere » tomberait juste par accident et la mutation survivrait --
    # exactement ce qui s'est produit au premier passage.
    for ordre in (("frais", 3.0), ("vieux", 300.0)), (("vieux", 300.0), ("frais", 3.0)):
        df = pd.DataFrame([_ligne(event_id=e, age_score_s=a) for e, a in ordre])
        out = fusionner_doublons(df)
        assert out.iloc[0]["event_id"] == "frais", out.iloc[0].to_dict()


# --- duree_courte : le temps effectif a cote de la pastille ---
#
# Demande a l'usage. La pastille dit le VERDICT, pas la mesure : deux flux
# verts peuvent avoir 2 s et 400 s d'age (leurs seuils different d'un facteur
# 5) et rien a l'ecran ne le disait.


def test_duree_courte_lit_les_trois_echelles():
    assert duree_courte(0) == "0s"
    assert duree_courte(6.4) == "6s"
    assert duree_courte(59.6) == "60s"
    assert duree_courte(90) == "1m30"
    assert duree_courte(605) == "10m05"
    assert duree_courte(3600) == "1h00"
    assert duree_courte(7565) == "2h06"


def test_un_age_inconnu_rend_un_point_d_interrogation_jamais_zero():
    """Meme regle que partout ici : confondre « je ne sais pas » avec « a
    l'instant » ferait passer un flux muet pour le plus vivant des quatre."""
    for absent in (None, float("nan"), "n'importe quoi"):
        assert duree_courte(absent) == "?", absent
    assert duree_courte(None) != "0s"


def test_une_derive_d_horloge_ne_rend_jamais_une_duree_negative():
    assert duree_courte(-5) == "0s"


# --- fusionner_series : deux event_id ecrivent au MEME horodatage ---
#
# Constate a l'usage sur un export du 2026-08-04 : le tableau point par point
# montrait deux lignes par instant, avec des scores en desaccord. Mesure sur
# les deux matchs concernes : les deux vues s'accordent sur les cotes de
# l'exchange dans 100 % des cas (meme marche) mais divergent sur le score dans
# 77 % des instants doubles, dont un JEU ENTIER 5 et 30 fois. La cote du
# bookmaker n'est presente que d'UN cote (45 et 77 fois) -- c'est pour elle
# qu'on lit les deux identifiants.


def test_avancement_ordonne_les_jeux_avant_les_points():
    assert avancement("2-4", "0-0") < avancement("3-4", "0-15")
    assert avancement("2-3", "0-0") < avancement("2-3", "0-15")
    assert avancement("2-4", "40-40") < avancement("3-4", "0-0")
    # « A » (avantage) vient apres 40.
    assert avancement("1-1", "40-40") < avancement("1-1", "A-40")
    # Illisible perd contre lisible : on ne prefere jamais une vue qu'on ne
    # sait pas lire.
    assert avancement("???", "0-0") < avancement("0-0", "0-0")
    assert avancement("1-0", "???") < avancement("1-0", "0-0")


def _pt(ts, score, points, **kw):
    base = {"ts": ts, "score": score, "points": points, "evenement": None,
            "back_odds_a": 2.0, "lay_odds_a": 2.1, "book_odds_a": None}
    base.update(kw)
    return base


def test_deux_vues_du_meme_instant_gardent_la_PLUS_AVANCEE():
    df = pd.DataFrame([
        _pt(100.0, "2-4", "0-0"),
        _pt(100.0, "3-4", "0-15"),
    ])
    out = fusionner_series(df)
    assert len(out) == 1
    assert out.iloc[0]["score"] == "3-4"
    assert out.iloc[0]["points"] == "0-15"


def test_la_cote_bookmaker_presente_d_UN_SEUL_cote_est_conservee():
    """Elle n'existe que sur un des deux identifiants (45 et 77 fois sur les
    deux matchs mesures) : la perdre reviendrait a annuler l'interet meme de
    lire les deux."""
    df = pd.DataFrame([
        _pt(100.0, "3-4", "0-15", book_odds_a=None),
        _pt(100.0, "2-4", "0-0", book_odds_a=1.85),
    ])
    out = fusionner_series(df)
    assert len(out) == 1
    assert out.iloc[0]["score"] == "3-4", "le score le plus avance"
    assert out.iloc[0]["book_odds_a"] == 1.85, "la cote book de l'AUTRE vue"


def test_une_serie_a_un_seul_identifiant_est_rendue_intacte():
    df = pd.DataFrame([_pt(100.0, "1-0", "0-0"), _pt(200.0, "1-0", "15-0")])
    out = fusionner_series(df)
    assert len(out) == 2
    assert list(out["ts"]) == [100.0, 200.0]


def test_l_ordre_des_lignes_ne_decide_de_rien():
    """Ni « la premiere » ni « la derniere » ne doit pouvoir passer pour la
    bonne reponse -- le piege deja rencontre sur fusionner_doublons."""
    for ordre in ((("2-4", "0-0"), ("3-4", "0-15")),
                  (("3-4", "0-15"), ("2-4", "0-0"))):
        df = pd.DataFrame([_pt(100.0, s, p) for s, p in ordre])
        assert fusionner_series(df).iloc[0]["score"] == "3-4", ordre


def test_charger_serie_replie_les_horodatages_doubles():
    doubles = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", book_odds_a=1.85),
        _pt(100.0, "3-4", "0-15"),
        _pt(200.0, "3-4", "30-15"),
    ])
    out = charger_serie("1,2", lecteur=lambda schema, query: doubles)
    assert len(out) == 2, out.to_dict("records")
    assert out.iloc[0]["score"] == "3-4"
    assert out.iloc[0]["book_odds_a"] == 1.85


def test_deux_MATCHS_au_meme_instant_ne_se_replient_PAS():
    """Le defaut du 2026-08-10, mesure contre TeNNet_test : la liste passait
    les six matchs en cours a `charger_serie`, le publieur les ecrit tous
    dans le meme cycle donc au MEME `ts`, et la fusion -- qui groupait sur
    `ts` seul -- n'en gardait qu'un. 342 horodatages sur 439 etaient
    partages, 62 % des lignes ecrasees, et la survivante empruntait ses
    colonnes vides aux AUTRES matchs. Trois matchs sur six perdaient leur
    fleche de mouvement, et l'une des trois restantes pointait a l'envers.
    """
    df = pd.DataFrame([
        _pt(100.0, "0-0", "0-0", event_id="A", back_odds_a=3.10),
        _pt(100.0, "1-6,1-2", "40-40", event_id="B", back_odds_a=10.00),
        _pt(100.0, "6-4,0-1", "0-0", event_id="C", back_odds_a=1.34),
    ])
    out = fusionner_series(df)
    assert len(out) == 3, "aucun match n'a le droit d'en absorber un autre"
    assert set(out["event_id"]) == {"A", "B", "C"}
    # Chacun garde SES cotes : le comblement des colonnes vides ne doit
    # jamais traverser la frontiere d'un match.
    par_id = out.set_index("event_id")["back_odds_a"].to_dict()
    assert par_id == {"A": 3.10, "B": 10.00, "C": 1.34}


def test_une_FAMILLE_declaree_se_replie_toujours():
    """Le comportement du 2026-08-04 doit survivre : la source attribue
    parfois deux `event_id` a une seule rencontre, l'un portant la cote
    bookmaker que l'autre n'a pas. On garde le score le PLUS AVANCE et on
    comble les trous avec l'autre vue -- mais seulement entre identifiants
    qu'on a explicitement declares parents."""
    df = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", event_id="1", book_odds_a=1.85),
        _pt(100.0, "3-4", "0-15", event_id="2"),
    ])
    out = fusionner_series(df, famille=["1", "2"])
    assert len(out) == 1
    assert out.iloc[0]["score"] == "3-4", "le score le plus avance"
    assert out.iloc[0]["book_odds_a"] == 1.85, "la cote book de l'AUTRE vue"


def test_un_identifiant_HORS_famille_reste_a_part():
    """Declarer une famille n'ouvre pas la porte a tout le reste : un match
    etranger present dans le meme tableau garde ses lignes."""
    df = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", event_id="1"),
        _pt(100.0, "3-4", "0-15", event_id="2"),
        _pt(100.0, "6-0", "40-0", event_id="etranger"),
    ])
    out = fusionner_series(df, famille=["1", "2"])
    assert len(out) == 2, out.to_dict("records")
    assert set(out["event_id"]) == {"2", "etranger"}


def test_sans_colonne_event_id_la_fusion_groupe_sur_le_temps():
    """Une serie sans identifiant ne permet PAS de distinguer deux matchs :
    on ne peut alors que grouper sur l'instant. C'est le seul cas ou le
    comportement d'avant subsiste, et il ne se produit jamais en service --
    `charger_serie` et `charger_mouvements` lisent toujours `event_id`."""
    df = pd.DataFrame([_pt(100.0, "2-4", "0-0"), _pt(100.0, "3-4", "0-15")])
    out = fusionner_series(df)
    assert len(out) == 1
    assert out.iloc[0]["score"] == "3-4"


def test_charger_serie_declare_la_famille_qu_il_a_demandee():
    """`charger_serie` promet « la serie d'UN match » : les identifiants
    qu'il recoit sont, par construction, une famille."""
    doubles = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", event_id="1", book_odds_a=1.85),
        _pt(100.0, "3-4", "0-15", event_id="2"),
        _pt(200.0, "3-4", "30-15", event_id="1"),
    ])
    out = charger_serie("1,2", lecteur=lambda schema, query: doubles)
    assert len(out) == 2, out.to_dict("records")
    assert out.iloc[0]["score"] == "3-4"
    assert out.iloc[0]["book_odds_a"] == 1.85
    assert list(out["ts"]) == [100.0, 200.0], "la serie reste dans l'ordre du temps"


# --- La liste : circuit, tournoi, heure, et seulement les matchs commences ---


def test_competition_distingue_le_circuit_ET_le_niveau():
    assert competition("atp", "National Bank Open - Montreal") == "ATP"
    assert competition("wta", "Polish Open - Warsaw") == "WTA"
    # Le circuit reste visible sur un Challenger : ATP et WTA Challenger ne
    # sont pas la meme population, et la liste sert a choisir ou regarder.
    assert competition("atp", "Hagen Challenger") == "ATP CHALLENGER"
    assert competition("wta", "Some WTA Challenger") == "WTA CHALLENGER"
    assert competition("atp", "M15 Eupen ITF") == "ATP ITF"
    # Un circuit inconnu ne devient pas ATP par defaut.
    assert competition(None, "Hagen Challenger") == "? CHALLENGER"


def test_a_joue_ne_retient_que_les_matchs_commences():
    assert a_joue("0-0", "15-0") is True
    assert a_joue("1-0", "0-0") is True
    assert a_joue("0-0", "0-0") is False
    # Un score illisible rend FAUX : sans savoir lire, on ne peut pas
    # affirmer qu'un point a ete joue.
    assert a_joue("???", "???") is False
    assert a_joue(None, None) is False


# --- L'ecart en ticks et la probabilite implicite ---


def test_l_ecart_se_compte_en_CRANS_et_non_en_valeur_absolue():
    """0,05 vaut cinq crans a 1,50 et un seul a 3,50 : en valeur absolue on
    melangerait des situations sans rapport. Le tick est la seule unite ou
    « un cran de carnet » signifie la meme chose partout -- et la mesure du
    PoC le confirme, l'ecart en ticks est independant de la cote (pearson
    0,000) la ou l'ecart absolu la suit (+0,292)."""
    assert ecart_en_ticks(1.50, 1.55) == 5      # pas de 0,01 sous 2,00
    assert ecart_en_ticks(3.50, 3.55) == 1      # pas de 0,05 entre 3 et 4
    # Meme ecart ABSOLU, nombre de crans different : c'est tout le sujet.
    assert ecart_en_ticks(1.50, 1.55) != ecart_en_ticks(3.50, 3.55)
    # Traversee de bande : 2,92 -> 3,00 fait 4 crans a 0,02, puis 3,00 -> 3,65
    # en fait 13 a 0,05.
    assert ecart_en_ticks(2.92, 3.65) == 17
    assert ecart_en_ticks(1.38, 1.53) == 15


def test_un_carnet_CROISE_ne_rend_pas_un_ecart_nul():
    """Lay sous back ne decrit pas un ecart mais une incoherence : l'afficher
    comme un zero le ferait passer pour le marche le plus serre possible."""
    assert ecart_en_ticks(2.00, 1.50) is None
    assert ecart_en_ticks(2.00, 2.00) == 0, "back = lay est un ecart nul, lui"


def test_un_prix_absent_ou_hors_echelle_ne_donne_aucun_ecart():
    for mauvais in ((None, 1.5), (1.5, None), (None, None),
                    (0.5, 1.5), (1.5, 2000.0), ("x", 1.5)):
        assert ecart_en_ticks(*mauvais) is None, mauvais


def test_la_probabilite_retire_la_MARGE_du_marche():
    """Une cote se lit mal pour juger : 1,38 contre 2,92 ne dit pas
    spontanement « 69 % »."""
    p = probabilite_implicite(1.38, 1.53, 2.92, 3.65)
    assert 0.65 < p < 0.75, p
    # Deux cotes egales donnent exactement 50 % : la marge est bien retiree.
    assert probabilite_implicite(2.0, 2.0, 2.0, 2.0) == 0.5
    # Sans demarginalisation, 1/1,90 vaudrait 0,526 et non 0,5.
    assert abs(probabilite_implicite(1.90, 1.90, 1.90, 1.90) - 0.5) < 1e-9


def test_une_probabilite_tiree_d_UN_SEUL_joueur_est_refusee():
    """Elle serait la marge du bookmaker deguisee en pronostic."""
    assert probabilite_implicite(1.38, 1.53, None, None) is None
    assert probabilite_implicite(None, None, 2.92, 3.65) is None
    # Une cote <= 1 n'est pas un prix et ne doit pas entrer dans le calcul.
    assert probabilite_implicite(1.0, 1.0, 2.0, 2.0) is None


def test_la_chronologie_illisible_rend_une_liste_vide_sans_lever():
    """C'est un ornement utile, pas la donnee dont depend l'affichage du
    score : elle ne doit jamais faire tomber la page."""
    assert chronologie('[{"jeu":1,"serveur":0,"break":true}]')[0]["jeu"] == 1
    for mauvais in (None, "", "   ", "pas du json", "{}", "[1,2]", 42):
        assert chronologie(mauvais) == [] or all(
            isinstance(x, dict) for x in chronologie(mauvais)), mauvais


# ══════════════════════════════════════════════════════════════════════
# Les trois lecteurs des tables du PASSE (bilan, matchs joues, points)
# ══════════════════════════════════════════════════════════════════════
#
# Meme motif que charger_matchs()/charger_serie() : SCHEMA du PoC, lecteur
# injectable, import differe. Le faux lecteur distingue les tables par leur
# nom dans la requete, comme le fait deja tests/test_pages_match.py.


def _capture(retour=None):
    """Un faux lecteur qui retient (schema, requete) et rend `retour`."""
    vu = {"appels": 0}

    def lecteur(schema, query):
        vu["appels"] += 1
        vu["schema"] = schema
        vu["query"] = query
        return pd.DataFrame() if retour is None else retour

    return vu, lecteur


# --- Le schema interroge : TeNNet_test, JAMAIS la production ------------
#
# Le PoC s'interdit d'ECRIRE dans `TeNNet` (un robot en argent reel y vit) ;
# la viz, elle, lit les deux schemas -- `TeNNet` pour les paris, ailleurs
# dans l'application. Ces trois lecteurs-la sont ceux du PoC : ils doivent
# viser `TeNNet_test` et rien d'autre. Une requete `live_qa_daily` envoyee
# a `TeNNet` ne leverait pas forcement une erreur visible (table absente ->
# « Base de donnees injoignable »), donc rien a l'ecran ne le dirait.


def test_les_trois_lecteurs_du_passe_interrogent_le_schema_du_poc():
    for appel in (
        lambda lecteur: charger_bilan_qa(lecteur=lecteur),
        lambda lecteur: charger_matchs_passes(lecteur=lecteur),
        lambda lecteur: charger_points("3807291", lecteur=lecteur),
    ):
        vu, lecteur = _capture()
        appel(lecteur)
        assert vu["schema"] == SCHEMA, vu["schema"]
        assert vu["schema"] == "TeNNet_test", vu["schema"]


def test_chaque_lecteur_du_passe_vise_SA_table_et_aucune_autre():
    """Trois tables aux colonnes proches (`day`, `event_id`) : confondre
    `live_matches` et `live_points` rendrait un tableau plausible et faux."""
    autres = {"live_qa_daily", "live_matches", "live_points",
              "live_series", "live_now", "live_inplay_markets"}
    for appel, attendue in (
        (lambda lecteur: charger_bilan_qa(lecteur=lecteur), "live_qa_daily"),
        (lambda lecteur: charger_matchs_passes(lecteur=lecteur), "live_matches"),
        (lambda lecteur: charger_points("3807291", lecteur=lecteur), "live_points"),
    ):
        vu, lecteur = _capture()
        appel(lecteur)
        assert attendue in vu["query"], (attendue, vu["query"])
        for interdite in autres - {attendue}:
            assert interdite not in vu["query"], (interdite, vu["query"])


# --- charger_bilan_qa : les dix jours du bilan --------------------------


def test_charger_bilan_qa_demande_lordre_chronologique():
    """Le bilan se lit dans le sens du temps -- c'est ce qui rend la
    tendance lisible (le trou passe de 97 % a 51 % entre le 3 et le 5 aout).
    Sans ORDER BY, MySQL ne promet aucun ordre."""
    vu, lecteur = _capture()
    charger_bilan_qa(lecteur=lecteur)
    assert "ORDER BY day" in vu["query"], vu["query"]


def test_charger_bilan_qa_rend_les_dix_jours_sans_toucher_aux_absences():
    """Les quatre premiers jours n'ont AUCUNE mesure de `match_rate`
    (n_markets = 0) : le lecteur doit les rendre absents, pas a zero. Les
    convertir ici ferait mentir tout ce qui les lit ensuite."""
    reel = pd.DataFrame(LIGNES_REELLES_QA)
    df = charger_bilan_qa(lecteur=lambda schema, query: reel)
    assert len(df) == 10
    par_jour = df.set_index("day")
    assert pd.isna(par_jour.loc[date(2026, 7, 28), "match_rate"])
    assert par_jour.loc[date(2026, 8, 6), "match_rate"] == 0.6531
    # Et le 31 juillet garde SA mesure de coherence pbp, alors meme que son
    # `match_rate` est absent : les deux ne se tiennent pas la main.
    assert par_jour.loc[date(2026, 7, 31), "pbp_coherence"] == 0.5518


def test_charger_bilan_qa_sur_une_table_vide_rend_un_tableau_vide():
    assert charger_bilan_qa(lecteur=lambda s, q: pd.DataFrame()).empty
    assert charger_bilan_qa(lecteur=lambda s, q: None).empty


# --- charger_matchs_passes : les matchs identifies ----------------------


def test_charger_matchs_passes_demande_le_plus_recent_dabord():
    """La liste s'ouvre sur hier, pas sur le 28 juillet."""
    vu, lecteur = _capture()
    charger_matchs_passes(lecteur=lecteur)
    assert "ORDER BY day DESC" in vu["query"], vu["query"]


def test_charger_matchs_passes_rend_les_lignes_reelles_apparie_ou_non():
    """Les deux etats coexistent en base (416 apparies sur 1 153) et la
    liste doit pouvoir les distinguer : un lecteur qui filtrerait les non
    apparies -- ou qui rendrait `matched` en booleen perdu -- casserait le
    filtre de la page."""
    reel = pd.DataFrame(LIGNES_REELLES_MATCHS)
    df = charger_matchs_passes(lecteur=lambda schema, query: reel)
    assert len(df) == 6
    par_id = df.set_index("id")
    assert par_id.loc[1272, "matched"] == 1
    assert par_id.loc[1277, "matched"] == 0
    # Les valeurs des filtres viennent des donnees, donc elles doivent
    # survivre au lecteur intactes.
    assert set(df["tour_type"]) == {"atp", "wta"}
    assert len(set(df["league"])) == 4, sorted(set(df["league"]))


def test_charger_matchs_passes_sur_une_table_vide_rend_un_tableau_vide():
    assert charger_matchs_passes(lecteur=lambda s, q: pd.DataFrame()).empty
    assert charger_matchs_passes(lecteur=lambda s, q: None).empty


# --- charger_points : le point par point, et le litteral SQL ------------
#
# MEME PIEGE que charger_serie (live_data.py:754) : `event_id` vient de
# l'URL (st.query_params), donc de n'importe qui. read_sql_query n'expose
# aucune API de parametres bindes : l'identifiant entre dans un litteral
# entre quotes, et c'est le retrait de TOUTES les apostrophes -- pas un
# nettoyage cosmetique -- qui empeche d'en sortir.


def test_charger_points_demande_lordre_de_reception():
    vu, lecteur = _capture()
    charger_points("3807291", lecteur=lecteur)
    assert "ORDER BY recv_ts" in vu["query"], vu["query"]


def test_charger_points_ne_lit_que_le_match_demande():
    """176 208 lignes en base : sans le WHERE, la page tirerait la table
    entiere pour afficher un match."""
    vu, lecteur = _capture()
    charger_points("3807291", lecteur=lecteur)
    assert "WHERE event_id IN ('3807291')" in vu["query"], vu["query"]


def test_charger_points_retire_les_apostrophes_de_levent_id():
    """L'apostrophe est la SEULE facon de sortir du litteral. Sans ce
    retrait, `3807291' OR '1'='1` refermerait la quote et la condition
    deviendrait vraie pour toute la table."""
    vu, lecteur = _capture()
    charger_points("3807291' OR '1'='1", lecteur=lecteur)
    # Exactement deux apostrophes dans la requete : celles qui ouvrent et
    # ferment le SEUL litteral. Compter est plus dur a contourner que
    # chercher un motif precis.
    assert vu["query"].count("'") == 2, vu["query"]
    assert "'1'='1'" not in vu["query"], vu["query"]


def test_charger_points_retire_les_antislashs_de_levent_id():
    """Meme raison que sur charger_serie : un identifiant finissant par un
    antislash echappe la quote fermante et produit une erreur SQL, affichee
    a l'ecran comme « Base de donnees injoignable » -- un message qui
    designe la mauvaise cause."""
    vu, lecteur = _capture()
    charger_points("3807291\\", lecteur=lecteur)
    assert "\\" not in vu["query"], vu["query"]
    assert "IN ('3807291')" in vu["query"], vu["query"]


def test_charger_points_lit_TOUS_les_identifiants_dun_meme_match():
    """En base, 3799286 et 3802032 sont la MEME rencontre (meme match_id) et
    portent 2 et 105 points : n'en lire qu'un rendrait le match a moitie,
    sans le dire."""
    vu, lecteur = _capture()
    charger_points("3799286,3802032", lecteur=lecteur)
    assert "IN ('3799286', '3802032')" in vu["query"], vu["query"]
    vu, lecteur = _capture()
    charger_points(["3799286", "3802032"], lecteur=lecteur)
    assert "IN ('3799286', '3802032')" in vu["query"], vu["query"]


def test_charger_points_sans_identifiant_ninterroge_meme_pas_la_base():
    """`IN ()` est une erreur de syntaxe MySQL : la page l'afficherait comme
    une base injoignable. Et une requete sans WHERE tirerait tout."""
    for vide in ("", "   ", ",,", None, []):
        vu, lecteur = _capture()
        assert charger_points(vide, lecteur=lecteur).empty, vide
        assert vu["appels"] == 0, vide


def test_charger_points_rend_les_lignes_reelles_dans_lordre_recu():
    reel = pd.DataFrame(LIGNES_REELLES_POINTS)
    df = charger_points("3799286,3802032", lecteur=lambda s, q: reel)
    assert len(df) == 5
    assert list(df["recv_ts"]) == sorted(df["recv_ts"])
    assert df.iloc[0]["event_id"] == "3799286"
    assert df.iloc[-1]["points"] == "30-0"


def test_charger_points_sur_un_match_sans_point_rend_un_tableau_vide():
    assert charger_points("3807291", lecteur=lambda s, q: pd.DataFrame()).empty
    assert charger_points("3807291", lecteur=lambda s, q: None).empty


def test_charger_mouvements_ne_lit_que_les_colonnes_du_MOUVEMENT():
    """341 ms mesurees pour la liste, dont 289 en fusion et 48 en SQL. La
    liste n'a besoin que du sens des prix : six colonnes, aucune fusion.
    Mesure du 2026-08-10 : 16 ms au lieu de 341."""
    vues = {}
    def lecteur(schema, query):
        vues["query"] = query
        return pd.DataFrame()
    charger_mouvements("1,2", lecteur=lecteur)
    q = vues["query"]
    assert "SELECT *" not in q, "la liste ne lit pas quatorze colonnes pour six"
    for colonne in ("event_id", "ts", "back_odds_a", "lay_odds_a",
                    "back_odds_b", "lay_odds_b"):
        assert colonne in q, colonne
    assert "'1', '2'" in q, q
    assert q.rstrip().endswith("ORDER BY ts"), q


def test_charger_mouvements_ne_replie_RIEN():
    """C'est tout l'objet de ce lecteur : `mouvements_de_prix` regroupe par
    `event_id`, et `lignes()` refusionne ensuite les identifiants d'un match.
    Replier ici couterait 289 ms pour detruire l'information."""
    brut = pd.DataFrame([
        {"event_id": "A", "ts": 100.0, "back_odds_a": 3.10, "lay_odds_a": 3.2,
         "back_odds_b": 1.46, "lay_odds_b": 1.5},
        {"event_id": "B", "ts": 100.0, "back_odds_a": 10.0, "lay_odds_a": 11.0,
         "back_odds_b": 1.07, "lay_odds_b": 1.1},
    ])
    out = charger_mouvements("A,B", lecteur=lambda schema, query: brut)
    assert len(out) == 2, "deux matchs au meme instant restent deux lignes"


def test_charger_mouvements_n_interroge_pas_la_base_pour_rien():
    """`IN ()` est une erreur de syntaxe MySQL : sans identifiant
    exploitable, on ne pose pas la question. Meme regle que `charger_serie`."""
    appels = []
    charger_mouvements("", lecteur=lambda s, q: appels.append(q))
    charger_mouvements(None, lecteur=lambda s, q: appels.append(q))
    assert appels == [], appels


def test_charger_mouvements_partage_la_regle_de_surete_SQL():
    """La regle qui rend la ligne SQL sure est ecrite UNE fois
    (`_identifiants_surs`). Pour une regle de SECURITE, le cote oublie serait
    celui qu'on ne verrait jamais."""
    vues = {}
    charger_mouvements("1' OR '1'='1", lecteur=lambda s, q: vues.setdefault("q", q))
    entre_parentheses = vues["q"].split("IN (")[1].split(")")[0]
    # Une seule valeur, entre deux quotes, et pas une quote de plus : le
    # litteral ne peut pas se refermer.
    assert entre_parentheses.count("'") == 2, entre_parentheses


# ── Une ligne sans SCORE mais avec des COTES ─────────────────────────────
#
# Signale le 2026-08-10 : les matchs du Challenger de Hambourg n'apparaissent
# pas. Aucune source ne donne leur score -- ni l'API, ni le canal `general`
# d'OrbitX -- alors que leur carnet arrive a quatre secondes. Le PoC les publie
# desormais avec `source_score = "exchange_seul"` ; encore faut-il que la page
# ne les jette pas.


def test_a_joue_laisse_passer_une_ligne_dont_les_COTES_bougent():
    """Le filtre vise le match « annonce mais pas commence » -- celui qui n'a
    « ni score, ni points, ET dont les cotes ne bougent pas ». Une ligne sans
    score mais dont le marche est EN JEU apprend quelque chose : elle reste."""
    from live_data import a_joue

    assert a_joue(None, None) is False
    assert a_joue(None, None, cotes_bougent=True) is True
    # Un vrai score reste suffisant, cotes ou pas.
    assert a_joue("1-0", "15-0") is True
    assert a_joue("1-0", "15-0", cotes_bougent=False) is True


def test_en_datetime_rend_l_heure_de_PARIS():
    """`live_series.ts` circule en secondes epoch ; sa mise en forme pour
    l'affichage rendait de l'UTC. Meme defaut que `liste_dense._heure`,
    signale le 2026-08-11."""
    import pandas as pd

    from live_data import en_datetime

    df = pd.DataFrame({"ts": [1786449600, 1800014400]})
    got = en_datetime(df)["ts"].dt.strftime("%H:%M").tolist()
    assert got == ["14:00", "13:00"]
