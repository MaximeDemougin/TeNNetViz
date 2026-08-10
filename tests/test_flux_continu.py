"""Le rafraichissement continu : ce qui empeche la page de se griser, et ce
qui remplace le signal ainsi supprime.

Ces tests gardent des SELECTEURS INTERNES a Streamlit, releves dans le bundle
1.52.2 et non de memoire. Une montee de version peut les deplacer : c'est
`tests/test_navigateur.py` qui le constatera, mais ceux-ci disent au moins ce
qu'on visait et pourquoi.
"""

from flux_continu import CSS_FLUX


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
