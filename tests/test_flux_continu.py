"""Le rafraichissement continu : ce qui empeche la page de se griser, et ce
qui remplace le signal ainsi supprime.

Ces tests gardent des SELECTEURS INTERNES a Streamlit, releves dans le bundle
1.52.2 et non de memoire. Une montee de version peut les deplacer : c'est
`tests/test_navigateur.py` qui le constatera, mais ceux-ci disent au moins ce
qu'on visait et pourquoi.
"""

import pandas as pd

from flux_continu import CSS_FLUX, bandeau_battement


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
