"""Le rafraichissement continu : ce qui empeche la page de se griser, et ce
qui remplace le signal ainsi supprime.

Ces tests gardent des SELECTEURS INTERNES a Streamlit, releves dans le bundle
1.52.2 et non de memoire. Une montee de version peut les deplacer : c'est
`tests/test_navigateur.py` qui le constatera, mais ceux-ci disent au moins ce
qu'on visait et pourquoi.
"""

import pandas as pd

from flux_continu import CSS_FLUX, bandeau_battement, instantane, marquer_changements


def test_la_feuille_neutralise_le_GRISEMENT():
    """Streamlit 1.52.2 : STALE_STYLES = {opacity: .33} pose apres 500 ms sur
    tout `[data-testid="stElementContainer"][data-stale="true"]`. C'est ce
    grisement, et rien d'autre, qui donnait a la page son air de F5."""
    assert '[data-stale="true"]' in CSS_FLUX
    assert "opacity: 1 !important" in CSS_FLUX


def test_la_feuille_n_eteint_QUE_l_homme_qui_court():
    """Le meme widget porte « Connecting... » et l'avis de session perdue.
    Le masquer en entier echangerait une gene contre un silence dangereux."""
    assert '[data-testid="stStatusWidgetRunningIcon"]' in CSS_FLUX
    # La regle est portee par `:has()`, donc conditionnee a l'icone. Une
    # regle sur `.stStatusWidget` nu masquerait aussi la deconnexion.
    for ligne in CSS_FLUX.splitlines():
        if "stStatusWidget" in ligne and "display" in ligne:
            assert ":has(" in ligne, f"regle trop large : {ligne.strip()}"


def test_le_bandeau_porte_l_HEURE_du_chargement():
    """Supprimer le grisement supprime le seul signe que les donnees bougent.
    L'heure affichee est celle du chargement REUSSI cote serveur : si le
    cycle s'arrete, elle se fige, et ca se voit."""
    html = bandeau_battement(6, 1786352606.0)
    attendue = pd.to_datetime(1786352606.0, unit="s").strftime("%H:%M:%S")
    assert attendue in html
    assert "6" in html


def test_le_bandeau_s_accorde_avec_la_colonne_HEURE_de_la_liste():
    """Les deux doivent lire l'horodatage de la meme facon, sans quoi un
    match paraitrait commencer apres l'heure affichee en tete de page."""
    from liste_dense import _heure

    assert _heure(1786352606.0)[:5] in bandeau_battement(1, 1786352606.0)


def test_le_battement_rejoue_a_CHAQUE_cycle():
    """Une animation posee sur un element que Streamlit RECREE a chaque cycle
    rejoue a chaque cycle : c'est un battement. Une boucle infinie
    (`animation-iteration-count: infinite`) tournerait aussi sur une page
    morte et ne prouverait rien."""
    assert "@keyframes battement" in CSS_FLUX
    assert "infinite" not in CSS_FLUX


def _ligne(event_ids="A", jeux=("6", "4"), point="30", back=2.0, lay=2.1):
    return {
        "event_ids": event_ids,
        "joueurs": [
            {"jeux": list(jeux), "point": point, "back": back, "lay": lay},
            {"jeux": list(jeux), "point": "0", "back": 1.8, "lay": 1.9},
        ],
    }


def test_le_PREMIER_rendu_n_allume_rien():
    """Sans instantane precedent il n'y a rien a comparer. Marquer tout
    ferait s'allumer la liste entiere a l'ouverture, et le signal ne voudrait
    plus rien dire."""
    structure = [_ligne()]
    marquer_changements(structure, {})
    for joueur in structure[0]["joueurs"]:
        assert not any(joueur.get(c) for c in
                       ("neuf_jeux", "neuf_point", "neuf_back", "neuf_lay"))


def test_seule_la_valeur_qui_a_CHANGE_s_allume():
    vu = instantane([_ligne(point="30", back=2.0)])
    structure = [_ligne(point="40", back=2.0)]
    marquer_changements(structure, vu)
    j = structure[0]["joueurs"][0]
    assert j["neuf_point"] is True, "le point a change"
    assert j["neuf_back"] is False, "la cote back n'a pas bouge"
    assert j["neuf_jeux"] is False


def test_une_cote_ABSENTE_ne_clignote_pas_indefiniment():
    """NaN != NaN : compare brut, une cote absente paraitrait changer a
    chaque cycle et la ligne battrait sans fin."""
    vu = instantane([_ligne(back=float("nan"))])
    structure = [_ligne(back=float("nan"))]
    marquer_changements(structure, vu)
    assert structure[0]["joueurs"][0]["neuf_back"] is False


def test_un_match_NOUVEAU_n_est_pas_un_changement():
    """Un match qui entre dans la liste n'a rien « change » : il arrive."""
    vu = instantane([_ligne(event_ids="A")])
    structure = [_ligne(event_ids="B", point="40")]
    marquer_changements(structure, vu)
    assert not structure[0]["joueurs"][0].get("neuf_point")


def test_instantane_IGNORE_les_lignes_SANS_identifiant():
    """`event_ids` vide -- le repli de `lignes()` sur une ligne sans
    identifiant connu -- collisionnerait entre plusieurs matchs dans le
    dictionnaire : le survivant se ferait comparer aux valeurs d'un
    etranger au cycle suivant."""
    vu = instantane([_ligne(event_ids="", point="30"), _ligne(event_ids="", point="99")])
    assert vu == {}


def test_marquer_changements_IGNORE_une_ligne_SANS_identifiant_meme_si_vu_en_a_une():
    """Meme si l'appelant fournit malgre tout un `vu` portant une cle vide
    (construit a la main, hors `instantane`), une ligne sans identifiant ne
    doit jamais s'y comparer : elle n'a aucune facon fiable de savoir a
    quel match cette cle appartenait."""
    vu = {"": [{"jeux": ("6", "4"), "point": "30", "back": 2.0, "lay": 2.1}]}
    structure = [_ligne(event_ids="", point="40")]
    marquer_changements(structure, vu)
    assert not structure[0]["joueurs"][0].get("neuf_point")


def test_le_surlignage_joue_une_SEULE_fois():
    assert "@keyframes surlignage" in CSS_FLUX
    assert ".neuf" in CSS_FLUX


def test_le_rendu_pose_la_classe_sur_la_seule_cellule_neuve():
    """La preuve doit porter sur le HTML POUSSE, pas sur le drapeau : c'est
    le HTML qu'on regarde a l'ecran."""
    from liste_dense import rendu

    structure = [{
        "event_id": "A", "event_ids": "A", "debut": 1786352606.0,
        "competition": "ATP", "tournoi": "Test",
        "joueurs": [
            {"nom": "A", "sert": True, "jeux": ["6"], "point": "40",
             "back": 2.0, "lay": 2.1, "bp": False,
             "mvt_back": None, "mvt_lay": None, "neuf_back": True},
            {"nom": "B", "sert": False, "jeux": ["4"], "point": "0",
             "back": 1.8, "lay": 1.9, "bp": False,
             "mvt_back": None, "mvt_lay": None},
        ],
        "ecarts": [1, 1], "fraicheur": [], "morts": [],
    }]
    html = rendu(structure)
    assert html.count("neuf") == 1, "une seule cellule doit s'allumer"
    # Aucune fleche sur ce prix : la classe est donc exactement « b neuf ».
    assert 'class="b neuf"' in html, html


def test_une_structure_jamais_marquee_est_rendue_a_l_identique():
    """`rendu` sert aussi `pages/match.py` et deux bancs de test qui
    n'appellent jamais `marquer_changements`."""
    from liste_dense import lignes, rendu
    import pandas as pd, time

    df = pd.DataFrame([{
        "event_id": "A", "participant1": "A", "participant2": "B",
        "score": "6-4", "points": "30-0", "server": "0",
        "back_odds_a": 2.0, "lay_odds_a": 2.1,
        "back_odds_b": 1.8, "lay_odds_b": 1.9,
        "league": "Test", "tour_type": "atp", "start_timestamp": time.time(),
        "status": "InPlay", "updated_ts": time.time(),
    }])
    html = rendu(lignes(df, time.time()))
    assert "neuf" not in html
    # L'absence de « neuf » ne suffit pas : la regression exacte etait
    # `class=""` sur une cellule de points ordinaire (une classe VIDE ne
    # contient pas la sous-chaine « neuf », donc l'assertion ci-dessus
    # restait verte). C'est cette ligne, sur le HTML exact, qui l'aurait
    # attrapee.
    assert "<span>30</span><span>0</span>" in html, html
