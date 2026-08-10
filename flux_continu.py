"""Le rafraichissement qui ne se voit pas -- et le battement qui le remplace.

La page « En direct » se grisait entierement toutes les quinze secondes, puis
se rallumait. Ce n'etait PAS un rechargement : c'est un comportement du
frontal Streamlit, lisible dans son bundle 1.52.2 --

    STALE_TRANSITION_PARAMS = "1s ease-in 0.5s"
    STALE_STYLES = { opacity: .33, transition: `opacity 1s ease-in 0.5s` }

Des qu'un rerun passe 500 ms, tout element pas encore recalcule descend a 33 %
d'opacite. Le cycle en coutait ~350 -- juste sous le seuil, d'ou une gene
intermittente qui s'aggravait avec le nombre de matchs, c'est-a-dire les soirs
ou l'on regarde.

Ce module vit a part de `liste_dense` : il sert AUSSI `pages/match.py`, qui ne
dessine aucune liste. L'ecrire deux fois garantirait qu'une correction
n'atterrisse que d'un cote -- la regle que ce depot tient deja pour
`detail_match`.
"""

import html

import pandas as pd

CSS_FLUX = """
<style>
  /* Le grisement de Streamlit, eteint. L'ancien contenu reste PLEINEMENT
     lisible jusqu'a ce que le nouveau le remplace : c'est tout ce que
     « streaming » veut dire ici. Les 289 ms de fusion supprimees par
     ailleurs mettent deja le cycle sous le seuil des 500 ms -- cette regle
     est la ceinture, et elle tient seule les soirs a quarante matchs. */
  [data-testid="stElementContainer"][data-stale="true"] {
    opacity: 1 !important; transition: none !important;
  }
  /* L'homme qui court, et LUI SEUL. Le meme widget porte « Connecting... »
     et l'avis de session perdue : le masquer en entier echangerait une gene
     contre un silence dangereux. */
  .stStatusWidget:has([data-testid="stStatusWidgetRunningIcon"]) { display: none; }

  /* Le battement. Il joue UNE fois, a la creation de l'element -- donc une
     fois par cycle. */
  @keyframes battement {
    0% { opacity: .2; } 12% { opacity: 1; } 100% { opacity: .2; }
  }
  .battement {
    display: flex; align-items: baseline; gap: .5rem;
    font-size: .82rem; opacity: .75; margin: 0 0 .5rem .1rem;
  }
  .battement u {
    width: .5rem; height: .5rem; border-radius: 50%;
    background: #32b296; text-decoration: none;
    animation: battement 1s ease-out;
  }
</style>
"""


def bandeau_battement(n_matchs: int, maintenant: float) -> str:
    """Le signal de vie qui remplace le grisement.

    Une pastille qui bat une fois par cycle et l'heure du dernier chargement
    reussi. L'animation est posee sur un element que Streamlit RECREE a chaque
    cycle : elle rejoue donc a chaque cycle, et seulement alors. Une boucle
    infinie tournerait aussi sur une page morte, et ne dirait rien.

    L'heure vient de `maintenant`, l'instant du chargement cote serveur, et
    se lit avec le meme idiome que la colonne « heure » de la liste
    (`liste_dense._heure`) : les deux doivent s'accorder, sans quoi un match
    paraitrait commencer apres l'heure affichee en tete de page.
    """
    heure = pd.to_datetime(float(maintenant), unit="s").strftime("%H:%M:%S")
    return (f'<div class="battement"><u></u><span>{html.escape(heure)}</span>'
            f'<span>· {int(n_matchs)} match(s) en cours</span></div>')
