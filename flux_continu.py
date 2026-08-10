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

  /* Ce qui vient de changer s'allume une demi-seconde, puis s'eteint. Pose
     sur un element que Streamlit recree : joue une fois, au bon moment.

     `background-image`, jamais `background` : une declaration animee vit
     dans l'origine de cascade "animation", qui bat toute regle d'auteur
     quelle que soit sa specificite. Animer le SHORTHAND `background`
     efface donc le fond propre de la cellule pendant les 0,6s -- et
     justement, chaque cellule marquee EN A un : `b.encours` (var(--vif)),
     `span.bp` (var(--break), le seul aplat vif de la ligne) et
     `i.hausse`/`i.baisse` (var(--back-fond)/var(--lay-fond), la marque du
     mouvement que ce surlignage doit COEXISTER avec, pas remplacer). Un
     gradient plat en `background-image` se superpose a la place. */
  @keyframes surlignage {
    from { background-image: linear-gradient(rgba(50,178,150,.30), rgba(50,178,150,.30)); }
    to   { background-image: linear-gradient(rgba(50,178,150,0),   rgba(50,178,150,0)); }
  }
  .liste-dense .neuf {
    animation: surlignage .6s ease-out;
  }

  /* Cette page existe pour RETIRER le mouvement involontaire (le grisement
     du haut de ce fichier) : lui en rendre un par une autre porte serait
     defaire ce que le chantier a fait. `prefers-reduced-motion` est deja la
     regle du depot pour la transition de survol (liste_dense.py) -- les deux
     animations que CE module ajoute suivent la meme regle. */
  @media (prefers-reduced-motion: reduce) {
    .battement u, .liste-dense .neuf { animation: none; }
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


def _valeur(v):
    """Un prix comparable d'un cycle a l'autre.

    `NaN != NaN` : compare brut, une cote absente paraitrait changer a chaque
    cycle et sa ligne battrait sans fin.
    """
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def instantane(structure) -> dict:
    """Les valeurs volatiles telles qu'on vient de les afficher.

    Le diff se fait cote SERVEUR : `st.markdown` n'execute pas de `<script>`,
    il n'y a pas d'autre voie. Le cout est une comparaison de dictionnaires --
    sans rapport avec les 289 ms de `fusionner_series`, qui etait une boucle
    `iterrows` sur un millier de lignes.
    """
    # `event_ids` vide (le repli de `lignes()` sur une ligne sans
    # identifiant connu) collisionnerait entre plusieurs matchs : le
    # survivant du dictionnaire se ferait comparer aux valeurs d'un
    # etranger au cycle suivant.
    return {
        ligne["event_ids"]: [
            {"jeux": tuple(j["jeux"]), "point": j["point"],
             "back": _valeur(j["back"]), "lay": _valeur(j["lay"])}
            for j in ligne["joueurs"]
        ]
        for ligne in structure
        if ligne["event_ids"]
    }


def marquer_changements(structure, vu: dict):
    """Pose `neuf_*` sur les seules valeurs qui ont change depuis le dernier
    affichage.

    `vu` vide -- premier rendu -- ne marque RIEN : marquer tout ferait
    s'allumer la liste entiere a l'ouverture, et le signal ne voudrait plus
    rien dire. Un match qui ENTRE dans la liste n'a rien change non plus : il
    arrive.

    Ce surlignage ne remplace pas les fleches `hausse`/`baisse` : elles disent
    « ce prix a bouge dans les deux dernieres minutes », lui dit « ceci vient
    de changer sous tes yeux ». Deux echelles de temps, deux marques.
    """
    if not vu:
        return structure
    for ligne in structure:
        # Meme collision qu'a l'instantane : une ligne sans identifiant ne
        # se diffuse jamais, meme si `vu` porte malgre tout une cle vide.
        if not ligne["event_ids"]:
            continue
        avant = vu.get(ligne["event_ids"])
        if not avant:
            continue
        for rang, j in enumerate(ligne["joueurs"]):
            if rang >= len(avant):
                continue
            a = avant[rang]
            j["neuf_jeux"] = tuple(j["jeux"]) != a["jeux"]
            j["neuf_point"] = j["point"] != a["point"]
            j["neuf_back"] = _valeur(j["back"]) != a["back"]
            j["neuf_lay"] = _valeur(j["lay"]) != a["lay"]
    return structure
