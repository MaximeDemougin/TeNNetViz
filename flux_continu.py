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
</style>
"""
