"""Le bilan de collecte : trois indicateurs, trois seuils, et deux pieges.

Ce que cette page existe pour montrer : les seuils de sante sont definis
dans le code du PoC, les trois sont franchis TOUS LES JOURS depuis dix
jours, et personne ne les voit. Les tests ci-dessous protegent d'abord ce
constat -- puis les deux facons de le rendre faux :

1. le SENS du seuil. `match_rate` et `pbp_coherence` sont des MINIMA (en
   dessous = mauvais), `gap_ratio` est un MAXIMUM (au-dessus = mauvais).
   Se tromper de sens inverse le verdict et rend la page menteuse.
2. le DENOMINATEUR NUL. Quatre journees n'ont vu aucun marche : leur
   `match_rate` est absent, pas nul. Les afficher a 0 % en ferait quatre
   jours catastrophiques la ou il n'y a rien a mesurer -- et noierait
   l'information vraie sous une fausse.
"""

from datetime import date

import pandas as pd

from live_data import (
    CONFORME,
    HORS_SEUIL,
    INDICATEURS_QA,
    SANS_MESURE,
    SEUIL_QA_GAP_RATIO_MAX,
    SEUIL_QA_MATCH_RATE_MIN,
    SEUIL_QA_PBP_COHERENCE_MIN,
    bilan_juge,
    juger_qa,
    tendance_qa,
)
from fixtures_reelles import LIGNES_REELLES_QA

BILAN_REEL = pd.DataFrame(LIGNES_REELLES_QA)


def _jour(jour: date) -> pd.Series:
    return BILAN_REEL.set_index("day").loc[jour]


# ── Le denominateur nul : « pas de mesure », jamais « 0 % » ───────────


def test_un_jour_sans_marche_ne_rend_PAS_un_verdict_hors_seuil():
    """Les 28, 29, 30 et 31 juillet ont `n_markets = 0`, donc `match_rate`
    NULL -- relu en NaN par pandas.

    NaN echoue TOUTES les comparaisons : `nan < 0.90` est faux, donc un
    jugement naif le declarerait conforme ; le convertir en zero d'abord le
    declarerait hors seuil. Les deux mentent. Le PoC lui-meme refuse cette
    division a la source (`Live/qa_report.py::_ratio`, "une journee creuse
    n'est pas un echec de collecte") -- on ne la reintroduit pas ici.
    """
    for jour in (date(2026, 7, 28), date(2026, 7, 29),
                 date(2026, 7, 30), date(2026, 7, 31)):
        ligne = _jour(jour)
        assert ligne["n_markets"] == 0, jour
        verdict = juger_qa("match_rate", ligne["match_rate"])
        assert verdict == SANS_MESURE, (jour, verdict)
        assert verdict != HORS_SEUIL, jour
        assert verdict != CONFORME, jour


def test_une_absence_se_juge_par_INDICATEUR_pas_par_journee():
    """Le 31 juillet est le cas qui les separe : aucun marche vu en jeu
    (donc pas de taux d'appariement, pas de taux de trou) MAIS 868 jeux
    communs avec le `pbp`, donc une coherence de 55,18 % bel et bien
    mesuree -- et hors seuil.

    Un code qui declarerait « pas de mesure » au niveau du JOUR effacerait
    cette mesure-la. Aucune autre journee des dix ne le revele.
    """
    ligne = _jour(date(2026, 7, 31))
    assert juger_qa("match_rate", ligne["match_rate"]) == SANS_MESURE
    assert juger_qa("gap_ratio", ligne["gap_ratio"]) == SANS_MESURE
    assert ligne["pbp_coherence"] == 0.5518
    assert juger_qa("pbp_coherence", ligne["pbp_coherence"]) == HORS_SEUIL


def test_une_mesure_a_zero_reste_une_mesure():
    """« Aucun marche rattache » (0,0 sur des marches vus) et « aucun marche
    vu » (absence) ne sont pas la meme chose : le premier est un echec
    mesure, le second n'est pas une mesure. `count_reliable_matches` cote
    PoC produit bien 0.0 dans le premier cas."""
    assert juger_qa("match_rate", 0.0) == HORS_SEUIL
    assert juger_qa("gap_ratio", 0.0) == CONFORME


def test_les_formes_dabsence_sont_toutes_reconnues():
    """NULL relu depuis MySQL arrive en NaN flottant, mais un appelant peut
    aussi passer None (pandas rend None sur une colonne entierement NULL,
    comme `n_inversions` sur une seule ligne)."""
    for absente in (None, float("nan"), pd.NA, pd.NaT):
        assert juger_qa("match_rate", absente) == SANS_MESURE, absente
        assert juger_qa("gap_ratio", absente) == SANS_MESURE, absente


# ── Les deux SENS de seuil ────────────────────────────────────────────


def test_les_deux_sens_de_seuil_sur_la_journee_du_6_aout():
    """La journee la plus recente, ses trois valeurs reelles :

    - `match_rate` 65,31 % pour un MINIMUM de 90 % -> hors seuil. Lu comme
      un maximum, 0,6531 > 0,90 est faux : la page dirait « conforme ».
    - `pbp_coherence` 39,31 % pour un MINIMUM de 95 % -> hors seuil. Meme
      inversion possible.
    - `gap_ratio` 51,59 % pour un MAXIMUM de 5 % -> hors seuil, dix fois le
      seuil. Lu comme un minimum, 0,5159 < 0,05 est faux : « conforme »
      encore.

    Les trois valeurs sont DIFFERENTES entre elles (0,6531 / 0,3931 /
    0,5159), donc une permutation entre indicateurs se verrait aussi.
    """
    ligne = _jour(date(2026, 8, 6))
    assert ligne["match_rate"] == 0.6531
    assert ligne["pbp_coherence"] == 0.3931
    assert ligne["gap_ratio"] == 0.5159
    assert juger_qa("match_rate", ligne["match_rate"]) == HORS_SEUIL
    assert juger_qa("pbp_coherence", ligne["pbp_coherence"]) == HORS_SEUIL
    assert juger_qa("gap_ratio", ligne["gap_ratio"]) == HORS_SEUIL


def test_le_sens_de_chaque_indicateur_est_ecrit_et_ne_bouge_pas():
    """Le sens vit dans la donnee, pas dans une suite de `if` : c'est lui
    qu'on relit pour verifier qu'aucun n'a ete inverse."""
    assert INDICATEURS_QA["match_rate"].sens == "min"
    assert INDICATEURS_QA["pbp_coherence"].sens == "min"
    assert INDICATEURS_QA["gap_ratio"].sens == "max"


def test_le_verdict_bascule_de_part_et_dautre_du_seuil():
    """AUCUNE des dix journees reelles n'est conforme sur aucun des trois
    indicateurs -- c'est precisement le constat que la page rend visible.
    La branche « conforme » ne peut donc pas s'exercer sur les donnees : on
    l'exerce sur les seuils EUX-MEMES, de part et d'autre.

    L'egalite est CONFORME des deux cotes, comme cote PoC
    (`Live/qa_report.py::evaluate` : `value < threshold` pour un minimum,
    `value > threshold` pour un maximum). Sans ce test, un `<=` mis pour un
    `<` passerait inapercu.
    """
    assert juger_qa("match_rate", SEUIL_QA_MATCH_RATE_MIN) == CONFORME
    assert juger_qa("match_rate", SEUIL_QA_MATCH_RATE_MIN - 0.0001) == HORS_SEUIL
    assert juger_qa("match_rate", SEUIL_QA_MATCH_RATE_MIN + 0.0001) == CONFORME

    assert juger_qa("pbp_coherence", SEUIL_QA_PBP_COHERENCE_MIN) == CONFORME
    assert juger_qa("pbp_coherence", SEUIL_QA_PBP_COHERENCE_MIN - 0.0001) == HORS_SEUIL

    assert juger_qa("gap_ratio", SEUIL_QA_GAP_RATIO_MAX) == CONFORME
    assert juger_qa("gap_ratio", SEUIL_QA_GAP_RATIO_MAX + 0.0001) == HORS_SEUIL
    assert juger_qa("gap_ratio", SEUIL_QA_GAP_RATIO_MAX - 0.0001) == CONFORME


# ── Les seuils eux-memes, dupliques d'un AUTRE depot ──────────────────


def test_les_trois_seuils_sont_epingles_sur_ceux_du_poc():
    """Valeurs REPRISES de `/home/ubuntu/TeNNetPy/Live/config.py` (lignes
    768-770 au prelevement du 2026-08-07), que ce depot n'importe pas.

    Ce test est le seul lien mecanique entre les deux depots : si quelqu'un
    change un seuil ici sans le changer la-bas (ou l'inverse), rien d'autre
    ne le dira. Il ne detecte pas la derive -- il rend au moins la valeur
    difficile a modifier par inadvertance.
    """
    assert SEUIL_QA_MATCH_RATE_MIN == 0.90
    assert SEUIL_QA_PBP_COHERENCE_MIN == 0.95
    assert SEUIL_QA_GAP_RATIO_MAX == 0.05


def test_le_1er_aout_manque_le_seuil_dappariement_de_peu_et_reste_hors_seuil():
    """0,8889 pour un seuil a 0,90 : la journee la plus proche de la
    conformite en dix jours, et elle n'y est pas.

    C'est cette ligne qui epingle la VALEUR du seuil sur des donnees
    reelles : le descendre a 0,85 rendrait ce jour-la conforme, et lui
    seul -- un changement qu'aucun autre test de la suite ne verrait.
    """
    ligne = _jour(date(2026, 8, 1))
    assert ligne["match_rate"] == 0.8889
    assert juger_qa("match_rate", ligne["match_rate"]) == HORS_SEUIL


def test_juger_qa_refuse_un_indicateur_quil_ne_connait_pas():
    """Meme regle que `fraicheur`, qui exige un seuil explicite : un
    indicateur sans seuil connu ne doit pas se juger « conforme » par
    defaut. Un silence vert est le mode de panne que ce depot combat."""
    for inconnu in ("n_inversions", "api_calls", "", None):
        try:
            juger_qa(inconnu, 0.5)
        except (KeyError, ValueError):
            continue
        raise AssertionError(f"{inconnu!r} juge sans seuil connu")


# ── Le bilan entier, jour par jour ────────────────────────────────────


def test_bilan_juge_pose_un_verdict_par_indicateur_et_par_jour():
    """Sur les dix journees reelles : les trois indicateurs sont hors seuil
    a CHAQUE journee mesuree, sans une seule exception -- et les journees
    non mesurees ne comptent pas comme des echecs.

    Repartition attendue, lue dans la table :
      match_rate     4 absences (28-31/07) + 6 hors seuil
      pbp_coherence  3 absences (28-30/07) + 7 hors seuil
      gap_ratio      4 absences (28-31/07) + 6 hors seuil
    """
    juge = bilan_juge(BILAN_REEL)
    assert len(juge) == 10
    attendu = {
        "match_rate": (4, 6),
        "pbp_coherence": (3, 7),
        "gap_ratio": (4, 6),
    }
    for indicateur, (absences, echecs) in attendu.items():
        colonne = juge[f"verdict_{indicateur}"]
        assert list(colonne).count(SANS_MESURE) == absences, indicateur
        assert list(colonne).count(HORS_SEUIL) == echecs, indicateur
        assert list(colonne).count(CONFORME) == 0, indicateur


def test_bilan_juge_ne_touche_pas_aux_valeurs_dorigine():
    """Le jugement s'ajoute, il ne remplace pas : le tableau garde ses
    valeurs brutes pour que le rendu affiche le chiffre a cote du verdict.
    Et il ne mute pas l'entree, lue ailleurs dans la page."""
    juge = bilan_juge(BILAN_REEL)
    assert juge.loc[juge["day"] == date(2026, 8, 6), "match_rate"].iloc[0] == 0.6531
    assert pd.isna(juge.loc[juge["day"] == date(2026, 7, 28), "match_rate"].iloc[0])
    assert "verdict_match_rate" not in BILAN_REEL.columns


def test_bilan_juge_sur_un_tableau_vide_ne_leve_pas():
    vide = bilan_juge(pd.DataFrame())
    assert vide.empty


# ── La tendance : elle porte le meme sens que le seuil ────────────────


def test_la_baisse_du_trou_de_collecte_se_lit_comme_une_AMELIORATION():
    """Le fait mesure que la table portait sans que personne le releve : le
    taux de trou passe de 97,21 % (3 aout) a 62,53 % (4 aout), la fenetre
    exacte de la correction d'authentification.

    Une BAISSE sur un indicateur de type maximum est une amelioration. Lu
    avec le sens d'un minimum, ce meme gain s'afficherait en degradation --
    la page annoncerait une panne le jour d'une reparation.
    """
    assert tendance_qa("gap_ratio", [0.9721, 0.6253]) == "amelioration"
    assert tendance_qa("gap_ratio", [0.6253, 0.9721]) == "degradation"


def test_la_baisse_de_lappariement_se_lit_comme_une_DEGRADATION():
    """Sens inverse, memes donnees reelles : `match_rate` passe de 72,73 %
    (5 aout) a 65,31 % (6 aout). Sur un MINIMUM, baisser est une
    degradation -- l'exact contraire du cas precedent, avec le meme geste.
    """
    assert tendance_qa("match_rate", [0.7273, 0.6531]) == "degradation"
    assert tendance_qa("match_rate", [0.6531, 0.7273]) == "amelioration"


def test_la_tendance_saute_les_journees_sans_mesure():
    """Les quatre premieres journees n'ont pas de `match_rate`. Comparer la
    derniere mesure a une absence ne dit rien ; la comparer a la derniere
    mesure CONNUE dit quelque chose."""
    valeurs = list(BILAN_REEL["match_rate"])
    assert tendance_qa("match_rate", valeurs) == "degradation"
    # Une seule mesure, ou aucune : rien a comparer, et surtout pas
    # « stable » -- qui se lirait comme une mesure.
    assert tendance_qa("match_rate", [float("nan")] * 4) == "inconnue"
    assert tendance_qa("match_rate", [float("nan"), 0.6531]) == "inconnue"
    assert tendance_qa("match_rate", []) == "inconnue"


def test_deux_mesures_egales_sont_stables_pas_ameliorees():
    assert tendance_qa("gap_ratio", [0.5159, 0.5159]) == "stable"
    assert tendance_qa("match_rate", [0.6531, 0.6531]) == "stable"


# ══════════════════════════════════════════════════════════════════════
# Le RENDU : ce que l'operateur lit reellement
# ══════════════════════════════════════════════════════════════════════
#
# Le jugement peut etre juste et l'ecran mentir quand meme -- un « pas de
# mesure » rendu « 0 % », un gain colore en rouge. Ces tests-la portent sur
# le texte pousse, pas sur la fonction qui le calcule.


def _app_bilan(lignes):
    """Une mini-application qui n'affiche QUE le bilan.

    `bilan_collecte.afficher` n'est pas une page : il sera appele depuis
    `pages/match.py` (tache 3). AppTest.from_function permet de l'eprouver
    seul, avec le vrai arbre d'elements Streamlit -- donc avec les couleurs
    reellement calculees, ce qu'un simple appel de fonction ne donnerait
    pas.
    """
    import pandas as pd

    from bilan_collecte import afficher

    afficher(pd.DataFrame(lignes))


def _rendu(lignes):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(
        _app_bilan, kwargs={"lignes": lignes}, default_timeout=30
    )
    at.run()
    assert not at.exception, at.exception
    return at


def _cellule(tableau, jour: date, colonne_contient: str) -> str:
    colonnes = [c for c in tableau.columns if colonne_contient in c]
    assert len(colonnes) == 1, (colonne_contient, list(tableau.columns))
    ligne = tableau[tableau["Jour"] == str(jour)]
    assert len(ligne) == 1, jour
    return ligne.iloc[0][colonnes[0]]


# ── Le denominateur nul, a l'ecran ────────────────────────────────────


def test_un_jour_sans_mesure_se_lit_PAS_DE_MESURE_et_jamais_zero_pourcent():
    """Le piege dans sa forme visible. Quatre journees sur dix n'ont pas de
    taux d'appariement ; rendues « 0,0 % », elles feraient quatre jours
    catastrophiques la ou il n'y a rien a mesurer, et le lecteur cesserait
    de croire la colonne.

    Aucune des dix journees ne mesure zero sur aucun des trois indicateurs
    (minimum reel : 34,36 %), donc « 0 % » ne peut apparaitre nulle part
    dans le tableau -- sauf si une absence y a ete convertie.
    """
    from bilan_collecte import SANS_MESURE_TEXTE, tableau_bilan

    tableau = tableau_bilan(BILAN_REEL)
    for jour in (date(2026, 7, 28), date(2026, 7, 29), date(2026, 7, 30)):
        for colonne in ("Appariement", "Cohérence", "Trou"):
            cellule = _cellule(tableau, jour, colonne)
            assert SANS_MESURE_TEXTE in cellule, (jour, colonne, cellule)
            assert "%" not in cellule, (jour, colonne, cellule)
    # Et le COMPTE, qui ne se contourne pas : 6 taux d'appariement, 7 de
    # coherence, 6 de trou = 19 mesures sur 30 cellules. Une absence
    # convertie en zero en ferait 30. (Chercher le texte « 0 % » ne
    # marcherait pas : « 59,0 % » et « 50,0 % » sont de vraies valeurs.)
    taux = [
        str(valeur)
        for entete in tableau.columns
        if any(x in entete for x in ("Appariement", "Cohérence", "Trou"))
        for valeur in tableau[entete]
    ]
    assert len(taux) == 30, len(taux)
    assert sum("%" in v for v in taux) == 19, [v for v in taux if "%" in v]


def test_le_31_juillet_montre_sa_coherence_MESUREE_a_cote_de_ses_absences():
    """Sur une meme ligne : deux « pas de mesure » et un taux reel. C'est le
    cas qui interdit de traiter l'absence au niveau de la journee."""
    from bilan_collecte import SANS_MESURE_TEXTE, tableau_bilan

    tableau = tableau_bilan(BILAN_REEL)
    jour = date(2026, 7, 31)
    assert SANS_MESURE_TEXTE in _cellule(tableau, jour, "Appariement")
    assert SANS_MESURE_TEXTE in _cellule(tableau, jour, "Trou")
    coherence = _cellule(tableau, jour, "Cohérence")
    assert "55,2 %" in coherence, coherence
    assert SANS_MESURE_TEXTE not in coherence, coherence


def test_chaque_cellule_du_tableau_porte_le_verdict_DE_SA_JOURNEE():
    """La tete de page ne juge que la derniere journee. Sans verdict dans
    le tableau, les neuf autres ne se liraient qu'en comparant de tete
    chaque chiffre au seuil ecrit dans l'en-tete -- et le constat que les
    trois seuils sont franchis TOUS les jours, qui est la raison d'etre de
    la page, ne se verrait plus d'un coup d'oeil.

    Trois etats sur la meme colonne, donc trois pastilles distinctes : le
    31 juillet n'a pas de taux d'appariement (blanc), le 1er aout l'a et le
    manque (rouge)."""
    from bilan_collecte import PASTILLE_QA, tableau_bilan
    from live_data import HORS_SEUIL as ROUGE_QA
    from live_data import SANS_MESURE as BLANC_QA

    tableau = tableau_bilan(BILAN_REEL)
    assert _cellule(tableau, date(2026, 7, 31), "Appariement").startswith(
        PASTILLE_QA[BLANC_QA])
    assert _cellule(tableau, date(2026, 7, 31), "Cohérence").startswith(
        PASTILLE_QA[ROUGE_QA])
    assert _cellule(tableau, date(2026, 8, 1), "Appariement").startswith(
        PASTILLE_QA[ROUGE_QA])
    # Les dix journees, les trois indicateurs : pas une seule conforme.
    for colonne in ("Appariement", "Cohérence", "Trou"):
        for cellule in tableau[[c for c in tableau.columns
                                if colonne in c][0]]:
            assert cellule.startswith(
                (PASTILLE_QA[ROUGE_QA], PASTILLE_QA[BLANC_QA])), cellule


def test_le_tableau_se_lit_du_plus_ancien_au_plus_recent():
    """C'est le sens dans lequel une tendance se lit, et c'est ce que dit
    la legende sous le tableau. L'inverser rendrait la legende fausse."""
    from bilan_collecte import tableau_bilan

    jours = list(tableau_bilan(BILAN_REEL)["Jour"])
    assert jours[0] == "2026-07-28", jours
    assert jours[-1] == "2026-08-06", jours
    assert jours == sorted(jours), jours


def test_la_colonne_des_inversions_naffiche_pas_un_zero_la_ou_rien_na_ete_compte():
    """`n_inversions` est NULL sur neuf des dix journees et vaut 0 sur la
    dixieme. Une colonne remplie de zeros annoncerait « aucune inversion
    detectee » dix jours de suite, alors que le controle n'a tourne qu'une
    fois. Le zero du 28 juillet, lui, est une vraie mesure et reste."""
    from bilan_collecte import SANS_MESURE_TEXTE, tableau_bilan

    tableau = tableau_bilan(BILAN_REEL)
    colonne = [c for c in tableau.columns if "Inversions" in c]
    assert colonne, list(tableau.columns)
    valeurs = list(tableau[colonne[0]])
    assert valeurs.count(SANS_MESURE_TEXTE) == 9, valeurs
    assert valeurs.count("0") == 1, valeurs
    assert _cellule(tableau, date(2026, 7, 28), "Inversions") == "0"


def test_chaque_taux_porte_SON_denominateur_dans_len_tete():
    """Deux taux d'appariement circulent dans cette page et ne comptent pas
    la meme chose (§4 du design) : 65,3 % sur les marches vus en jeu, 36 %
    sur tous les matchs identifies. Un pourcentage sans son denominateur ne
    veut rien dire -- et melanger les deux produirait un chiffre faux."""
    from bilan_collecte import tableau_bilan

    entetes = " | ".join(tableau_bilan(BILAN_REEL).columns)
    assert "marchés vus en jeu" in entetes, entetes
    assert "jeux communs" in entetes, entetes
    assert "temps in-play" in entetes, entetes


def test_le_tableau_dit_le_SEUIL_de_chaque_indicateur():
    """Un taux sans son seuil ne se juge pas : 39,3 % semble mediocre, il
    est en fait a moins de la moitie de ce qui est exige."""
    from bilan_collecte import tableau_bilan

    entetes = " | ".join(tableau_bilan(BILAN_REEL).columns)
    assert "90" in entetes and "95" in entetes and "5" in entetes, entetes


def test_un_bilan_vide_ne_leve_pas_et_le_dit():
    from bilan_collecte import tableau_bilan

    assert tableau_bilan(pd.DataFrame()).empty
    at = _rendu([])
    assert any("Aucun bilan" in str(i.value) for i in at.info), \
        [str(i.value) for i in at.info]


# ── Les trois alarmes, enfin visibles ─────────────────────────────────


def test_les_trois_alarmes_du_dernier_jour_sont_ANNONCEES():
    """La raison d'etre de la page : les trois seuils sont franchis tous les
    jours depuis dix jours et rien ne le disait. Un tableau seul ne suffit
    pas -- il faut que ce soit dit."""
    at = _rendu(LIGNES_REELLES_QA)
    alarmes = " ".join(str(e.value) for e in at.error)
    assert "65,3 %" in alarmes, alarmes
    assert "39,3 %" in alarmes, alarmes
    assert "51,6 %" in alarmes, alarmes
    # Et chacun avec le seuil qu'il franchit, sinon le chiffre ne se juge pas.
    assert "90 %" in alarmes and "95 %" in alarmes and "5 %" in alarmes, alarmes


def test_les_trois_indicateurs_sont_en_tete_avec_leur_pastille():
    at = _rendu(LIGNES_REELLES_QA)
    par_libelle = {m.label: m.value for m in at.metric}
    assert len(par_libelle) == 3, par_libelle
    assert all("🔴" in libelle for libelle in par_libelle), par_libelle
    assert "65,3 %" in " ".join(par_libelle.values()), par_libelle


def test_un_jour_sans_mesure_en_tete_naffiche_pas_un_taux():
    """Rendu du seul 28 juillet : trois indicateurs, aucune mesure. La tete
    de page doit le dire, pas afficher trois zeros ni trois alarmes."""
    at = _rendu(LIGNES_REELLES_QA[:1])
    valeurs = [m.value for m in at.metric]
    assert all("%" not in v for v in valeurs), valeurs
    assert all("⚪" in m.label for m in at.metric), [m.label for m in at.metric]
    assert not at.error, [str(e.value) for e in at.error]


# ── Le SENS, jusqu'a la couleur affichee ──────────────────────────────
#
# MetricProto.MetricColor : 0 = ROUGE, 1 = VERT, 2 = GRIS. La couleur est
# calculee par Streamlit a partir du signe du delta ET de `delta_color`, et
# c'est donc EXACTEMENT ce que l'operateur voit -- pas l'argument qu'on a
# passe.

ROUGE, VERT, GRIS = 0, 1, 2


def test_la_baisse_du_trou_saffiche_en_VERT_le_jour_de_la_correction():
    """Du 3 au 4 aout, le taux de trou tombe de 97,21 % a 62,53 % : la
    fenetre exacte de la correction d'authentification, et le seul vrai
    gain que ces dix jours contiennent.

    Un delta NEGATIF affiche en VERT n'est possible que si l'indicateur est
    traite comme un MAXIMUM. Lu comme un minimum, ce gain s'afficherait en
    rouge -- la page annoncerait une panne le jour d'une reparation.

    Dans le meme rendu, `match_rate` monte de 68,18 % a 68,60 % : un delta
    POSITIF, vert lui aussi, mais pour la raison INVERSE. Les deux
    basculent ensemble si on melange les sens.
    """
    at = _rendu(LIGNES_REELLES_QA[:8])   # jusqu'au 4 aout inclus
    par_libelle = {m.label: m for m in at.metric}
    trou = [m for lib, m in par_libelle.items() if "Trou" in lib][0]
    assert trou.delta.startswith("-"), trou.delta
    assert trou.proto.color == VERT, (trou.delta, trou.proto.color)
    appariement = [m for lib, m in par_libelle.items() if "Appariement" in lib][0]
    assert appariement.delta.startswith("+"), appariement.delta
    assert appariement.proto.color == VERT, (appariement.delta,
                                             appariement.proto.color)


def test_la_HAUSSE_du_trou_du_dernier_jour_saffiche_en_ROUGE():
    """Du 5 au 6 aout le trou remonte de 50,29 % a 51,59 % : un delta
    POSITIF qui doit etre rouge. C'est le meme signe que le gain
    d'appariement du test precedent, et la couleur opposee -- c'est le sens
    du seuil, et rien d'autre, qui les separe."""
    at = _rendu(LIGNES_REELLES_QA)
    par_libelle = {m.label: m for m in at.metric}
    trou = [m for lib, m in par_libelle.items() if "Trou" in lib][0]
    assert trou.delta.startswith("+"), trou.delta
    assert trou.proto.color == ROUGE, (trou.delta, trou.proto.color)
    for cle in ("Appariement", "Cohérence"):
        metrique = [m for lib, m in par_libelle.items() if cle in lib][0]
        assert metrique.delta.startswith("-"), (cle, metrique.delta)
        assert metrique.proto.color == ROUGE, (cle, metrique.proto.color)


def test_sans_deuxieme_mesure_aucune_tendance_nest_affichee():
    """Rendu des cinq premieres journees (28 juillet au 1er aout). Sur ce
    meme ecran, les trois indicateurs ne sont PAS dans le meme etat, et
    c'est ce que ce test protege :

    - `match_rate` et `gap_ratio` n'ont qu'UNE mesure (le 1er aout) : pas
      de delta du tout, plutot qu'un « 0,0 pt » qui se lirait comme une
      stabilite constatee, ou qu'un ecart calcule contre un zero invente.
    - `pbp_coherence` en a DEUX (55,18 % le 31 juillet, 34,36 % le 1er) :
      elle a donc un delta, et il saute les trois journees sans mesure qui
      les separent du debut.

    Une tendance calculee sur des absences remplacees par zero donnerait un
    delta aux trois -- et un gain spectaculaire au 1er aout.
    """
    at = _rendu(LIGNES_REELLES_QA[:5])   # 4 journees creuses + le 1er aout
    par_libelle = {m.label: m for m in at.metric}
    for cle in ("Appariement", "Trou"):
        metrique = [m for lib, m in par_libelle.items() if cle in lib][0]
        assert not metrique.delta, (cle, metrique.delta)
        assert metrique.proto.color == GRIS, (cle, metrique.proto.color)
    coherence = [m for lib, m in par_libelle.items() if "Cohérence" in lib][0]
    assert coherence.delta == "-20,8 pt", coherence.delta
    assert coherence.proto.color == ROUGE, coherence.proto.color
