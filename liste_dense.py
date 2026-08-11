"""Le rendu de la liste dense : la structure d'un cote, le HTML de l'autre.

Pourquoi du HTML et pas ``st.dataframe``. La maquette validee portait sur un
TRAITEMENT VISUEL -- prix colores aux couleurs du metier (back bleu, lay
rose), cases de set, set en cours marque, regroupement par tournoi. Une grille
standard rend les memes colonnes et rien de tout cela : j'avais livre
l'information sans la lecture, ce qui etait precisement l'objet de la
maquette.

La separation en deux fonctions est deliberee : ``lignes()`` calcule et se
teste sans une ligne de HTML, ``rendu()`` habille. Un test qui devrait lire
une balise pour verifier de quel cote se trouve la balle serait un mauvais
test.
"""

import html

import pandas as pd

from live_data import (
    SEUILS_PAR_FLUX,
    age_a_la_lecture,
    competition,
    ecart_en_ticks,
    fraicheur,
)
from utils import to_paris

#: Les couleurs des prix sont celles du METIER : sur l'exchange, back et lay
#: ont ces teintes depuis toujours. Ce n'est pas une decoration, c'est le code
#: que l'operateur lit deja ailleurs. La fraicheur a une echelle SEPAREE pour
#: qu'on ne confonde jamais « prix » et « confiance ».
#: Prefixe des conteneurs qui portent une ligne de match.
#:
#: La feuille de style et ``cle_ligne()`` en dependent TOUTES DEUX : le CSS
#: etale le bouton sur la ligne entiere en visant la classe
#: `st-key-<prefixe>-…` que Streamlit derive de la cle du conteneur. Les
#: ecrire separement les laisserait diverger a la premiere renomination -- et
#: la zone cliquable retomberait, sans bruit, a la taille du bouton. Aucun
#: test ne pourrait le voir : les conteneurs nommes ne remontent pas dans
#: l'arbre de rendu.
PREFIXE_LIGNE = "ligne"


#: Prefixe des boutons d'ouverture. Streamlit en derive AUSSI une classe sur
#: le conteneur d'element qui enveloppe le bouton -- et c'est la seule prise
#: sur lui.
PREFIXE_BOUTON = "btn"

#: Prefixe des cartes de tournoi. Meme motif que les deux precedents : la
#: feuille de style les plafonne a la MEME largeur que les lignes, sinon la
#: carte s'etire sur tout l'ecran pendant que son contenu s'arrete a 63rem,
#: et le vide se voit.
PREFIXE_CARTE = "carte"

#: Largeur de la liste. Elle sert DEUX fois : a la ligne visible et au
#: conteneur qui porte le clic. Ne la fixer que sur la premiere laissait
#: 232 px cliquables au-dela du dernier pixel affiche -- on ouvrait un match
#: en cliquant dans le vide a sa droite.
LARGEUR_LISTE = "63rem"


def cle_ligne(section: str, event_id: str) -> str:
    """La cle du conteneur d'une ligne -- et la moitie de sa zone cliquable."""
    return f"{PREFIXE_LIGNE}-{section}-{event_id}"


def cle_carte(section: str, rang: int) -> str:
    """La cle de la carte d'un tournoi."""
    return f"{PREFIXE_CARTE}-{section}-{rang}"


def cle_bouton(section: str, event_id: str) -> str:
    """La cle du bouton d'ouverture -- l'autre moitie de la zone cliquable."""
    return f"{PREFIXE_BOUTON}-{section}-{event_id}"


CSS = f"""
<style>
  /* Le bouton d'ouverture RECOUVRE toute la ligne, transparent : cliquer
     n'importe ou sur le match ouvre son detail. Une fleche de quelques
     pixels demandait de viser -- ce n'est pas une liste qu'on vise, c'est
     une liste qu'on parcourt. */
  div[class*="st-key-{PREFIXE_LIGNE}-"] {{
    position: relative; margin-bottom: 1px; max-width: {LARGEUR_LISTE};
  }}
  /* La carte d'un tournoi : la surface arrondie et surelevee du reste de
     l'application, bornee a la meme largeur que ses lignes. */
  div[class*="st-key-{PREFIXE_CARTE}-"] {{ max-width: {LARGEUR_LISTE}; }}
  /* L'ecart entre deux matchs se regle par `gap=None` sur la carte, cote
     Streamlit. Le forcer en CSS sur `stVerticalBlock` frappait AUSSI le
     conteneur de chaque ligne, qui retombait a 30 px pour un contenu de
     46 : le bouton n'en couvrait plus que les deux tiers et 56 points de
     la ligne ne repondaient plus au clic. */

  /* Streamlit enveloppe CHAQUE element dans un `stElementContainer` qu'il
     pose en `position: relative`. C'est donc LUI, et non la ligne, qui
     servait de reference a `inset: 0` -- et il mesure 16 px de large sur 0 de
     haut. Le bouton se retrouvait large de 16 px, 57 px SOUS sa propre ligne,
     donc dans la bande visuelle de la suivante : on cliquait a cote, et le
     survol s'allumait sur le match du dessus. Mesure au navigateur, pas
     deduction. Le remettre en `static` fait remonter la reference jusqu'a la
     ligne. On le vise par la classe que Streamlit derive de la cle du bouton
     -- `:has()` ferait le meme travail en dependant du navigateur. */
  div[class*="st-key-{PREFIXE_BOUTON}-"] {{ position: static; }}

  div[class*="st-key-{PREFIXE_LIGNE}-"] [data-testid="stButton"] {{
    position: absolute; inset: 0; z-index: 3; margin: 0; padding: 0;
  }}
  div[class*="st-key-{PREFIXE_LIGNE}-"] [data-testid="stButton"] button {{
    /* Streamlit impose un plancher de 40 px (mesure) qui gagnerait sur
       `height: 100%`. Sans effet sur les lignes actuelles, hautes de 55 px :
       c'est une precaution pour une ligne plus courte, pas une regle dont on
       ait constate le besoin -- aucun test ne la couvre. */
    width: 100%; height: 100%; min-height: 0; opacity: 0; border: none;
    background: transparent; padding: 0; margin: 0; cursor: pointer;
  }}
  div[class*="st-key-{PREFIXE_LIGNE}-"] [data-testid="stButton"] button:focus-visible {{
    opacity: 1; outline: 2px solid var(--vif, #D9A02B); background: transparent;
  }}
  div[class*="st-key-{PREFIXE_LIGNE}-"] [data-testid="stElementContainer"] {{ margin: 0; }}

  .liste-dense {{
    /* L'accent est celui de l'APPLICATION (.streamlit/config.toml :
       primaryColor #32b296), pas un ambre invente pour cette page seule.
       Il marque ce qui est vivant et normal : le set en cours, la ligne
       ouverte, le focus. */
    --vif: #32b296; --vif-doux: rgba(50,178,150,0.13);
    --back: #4C93F0; --back-fond: rgba(76,147,240,0.16);
    --lay:  #E06A98; --lay-fond:  rgba(224,106,152,0.16);
    /* Un flux FRAIS est l'etat normal : il ne merite pas d'etre allume,
       sinon la couleur ne veut plus rien dire. Seul ce qui cloche
       s'eclaire. Le vert d'avant se confondait de toute facon avec
       l'accent de l'application. */
    --frais: rgba(140,150,160,0.45); --perime: #E0655B; --break: #F07A3C;
    --creux: rgba(128,128,128,0.10);
    /* Hauteur d'UNE ligne de joueur. Chaque colonne empile ses deux
       joueurs separement, avec des tailles de police differentes : sans
       hauteur commune, le nom du second joueur ne tomberait pas en face
       de ses propres cotes -- on lirait le prix de l'autre. */
    --ligne: 1.4rem;
    --trait: rgba(128,128,128,0.22);
    font-variant-numeric: tabular-nums;
    /* Sans plafond, la colonne des noms absorbe toute la largeur d'un
       ecran large et met un vide de plusieurs centimetres entre le nom
       d'un joueur et sa cote -- l'oeil ne fait plus le lien. */
    max-width: {LARGEUR_LISTE};
  }}
  /* Le titre du tournoi occupe la colonne des JOUEURS de la ligne
     d'entete : il annonce donc ses lignes en se calant exactement sur
     elles. La legende flottait auparavant au-dessus de la carte, sur une
     ligne a elle, visiblement detachee. */
  .liste-dense .match.entete .titre {{
    font-size: 1.02rem; font-weight: 650; letter-spacing: -.01em;
    text-transform: none; opacity: 1; color: inherit;
  }}
  /* Le titre part du BORD de la carte et court sur les deux premieres
     colonnes. Cale sur la colonne des NOMS il laissait un vide de plusieurs
     centimetres a sa gauche, et se faisait tronquer -- « Grodzisk
     Mazowiecki Challe… ». Les libelles de colonnes, eux, restent chacun sur
     la sienne : c'est la seule chose qui doit s'aligner. */
  .liste-dense .match.entete .noms {{
    grid-column: heure-start / noms-end;
    display: flex; align-items: baseline; gap: .6rem; overflow: visible;
  }}
  .liste-dense .match.entete.tournoi {{
    position: relative; opacity: 1; border-radius: 0;
    padding-top: .5rem; padding-bottom: 1.25rem;
  }}
  /* AUCUN filet sous l'entete. La carte borne deja le tournoi en haut et en
     bas : un trait de plus faisait TROIS lignes horizontales pour un seul
     match. C'est l'espace qui separe -- il le fait aussi bien, et sans
     rien ajouter au dessin. */
  .liste-dense .match.entete.tournoi > span:not(.noms) {{ opacity: .42; }}
  .liste-dense .match + .match.entete.tournoi {{ margin-top: 1.4rem; }}
  .liste-dense .tournoi {{
    display: flex; align-items: baseline; gap: .6rem;
    /* Cale sur les COLONNES, pas sur le bord de la carte : la ligne a son
       propre rembourrage horizontal, et sans lui le titre partait 15 px a
       gauche de « HEURE ». Le bas etait pire -- il MORDAIT de 9 px sur la
       premiere ligne, mesure au navigateur. */
    padding: 0 .75rem; margin: .2rem 0 .7rem;
    font-weight: 650; font-size: 1.02rem; letter-spacing: -.01em;
  }}
  /* Un tournoi qui suit un autre dans la meme liste respire davantage. */
  .liste-dense .match + .tournoi {{ margin-top: 1.5rem; }}

  /* Un badge par circuit, teinte par circuit : « ATP », « WTA » et leurs
     Challenger ne sont pas la meme population, et la liste sert a choisir
     ou regarder. Les teintes evitent celles qui portent deja un sens dans
     la ligne -- bleu du back, rose du lay, vert de l'accent, orange de la
     balle de break, rouge du flux mort. */
  .liste-dense .circuit.atp {{
    background: rgba(108,140,245,0.18); color: #93AAF7;
  }}
  .liste-dense .circuit.wta {{
    background: rgba(199,125,219,0.18); color: #D3A2E4;
  }}
  .liste-dense .circuit.challenger {{ opacity: .82; }}
  /* Premier niveau : le circuit, hors des cartes, teinte comme son badge.
     Il porte ce que l'entete de tournoi n'a plus a repeter. */
  .liste-dense .competition {{
    font-size: .68rem; font-weight: 700; letter-spacing: .16em;
    text-transform: uppercase; padding: 0 .1rem; margin: 0 0 .5rem;
  }}
  .liste-dense .competition.atp {{ color: #93AAF7; }}
  .liste-dense .competition.wta {{ color: #D3A2E4; }}
  .liste-dense .competition.challenger {{ opacity: .8; }}
  .liste-dense .circuit {{
    font-size: .6rem; letter-spacing: .13em; text-transform: uppercase;
    opacity: .8; background: var(--creux); border-radius: 999px;
    padding: .12rem .55rem; font-weight: 600;
  }}

  .liste-dense .match {{
    display: grid;
    /* Largeurs FIXES, sauf les noms. Chaque ligne est une grille
       INDEPENDANTE : des colonnes `auto` se dimensionnent sur le contenu de
       LEUR ligne, donc deux lignes voisines ne s'alignent pas, et l'entete
       encore moins -- mesure a l'appui, « SETS » tombait 70 px a cote de sa
       colonne. Figer les largeurs est ce qui fait tenir la promesse d'une
       liste dense : comparer les cotes verticalement d'un match a l'autre. */
    grid-template-columns:
      3.1rem minmax(0, 1fr) 7.6rem 2.15rem 8.8rem 3.9rem 9rem;
    grid-template-areas: "heure noms jeux pts prix ecart flux";
    gap: .15rem 1.05rem; align-items: center;
    padding: .3rem .75rem; border-radius: 10px;
    /* RIEN ne doit se peindre hors de cette boite : c'est elle que le bouton
       invisible recouvre, donc tout ce qui en sort est visible mais MORT au
       clic. Deux cas mesures : sous ~430 px de large les colonnes fixes
       debordent de 29 px, et une cellule dont le contenu passe a la ligne
       (un `points` inattendu, la source publiant ce qu'elle veut) se peint
       dans la zone morte entre deux lignes. */
    overflow: hidden;
    border-left: 3px solid transparent;
    transition: background .12s ease, border-color .12s ease;
  }}
  .liste-dense .match.entete {{
    /* AUCUN retrait : l'entete vit desormais DANS la carte, comme les
       lignes qu'elle annonce. Le retrait de 1rem datait du temps ou elle
       flottait au-dessus, et le conserver la decalait de 16 px -- mesure au
       navigateur, dans les deux sens selon le cote de la colonne. */
    padding-top: 0; padding-bottom: .1rem; border-left-color: transparent;
    font-size: .6rem; letter-spacing: .1em; text-transform: uppercase;
    opacity: .42; border-radius: 0;
  }}
  .liste-dense .match.entete span {{
    display: block; font-size: inherit; opacity: 1; white-space: nowrap;
    overflow: hidden;
  }}
  /* L'entete se cale comme SA colonne de donnees, sinon elle designe le
     vide a cote. */
  .liste-dense .match.entete .jeux,
  .liste-dense .match.entete .pts,
  .liste-dense .match.entete .ecart {{ text-align: right; }}

  div[class*="st-key-{PREFIXE_LIGNE}-"]:hover .match {{
    background: var(--creux); border-left-color: var(--trait);
  }}
  .liste-dense .match.ouvert {{
    background: var(--vif-doux); border-left-color: var(--vif);
  }}
  @media (prefers-reduced-motion: reduce) {{
    .liste-dense .match {{ transition: none; }}
  }}

  .liste-dense .heure {{
    grid-area: heure; font-size: .74rem; opacity: .55; letter-spacing: .02em;
  }}
  .liste-dense .noms, .liste-dense .jeux,
  .liste-dense .pts, .liste-dense .prix {{
    /* Une hauteur de rangee FIXE, identique dans les quatre piles : c'est
       elle qui fait que le second joueur tombe en face de ses propres
       cotes. Elle doit rester SUPERIEURE a son contenu -- a 1,15rem les
       deux rangees se chevauchaient de 2 a 5 px, mesure au navigateur, et
       les cases de set se touchaient. */
    display: grid; grid-auto-rows: var(--ligne); row-gap: .2rem;
    align-items: center;
    /* `min-width: 0` : sans lui une cellule de grille refuse de descendre
       sous son contenu et pousse la ligne hors de sa propre boite. */
    min-width: 0; white-space: nowrap;
  }}
  .liste-dense .noms {{ grid-area: noms; min-width: 0; }}
  .liste-dense .nom {{
    /* La balle suit le NOM au lieu de le preceder : les noms partent tous
       du meme bord -- ils n'ont plus a laisser la place a un marqueur qui
       n'est la qu'une ligne sur deux -- et la balle se lit comme ce qu'elle
       est, une annotation du nom. */
    display: flex; align-items: center; gap: .35rem;
    font-size: .93rem; line-height: 1.2; white-space: nowrap; min-width: 0;
  }}
  .liste-dense .nom > em {{
    font-style: normal; font-size: .78rem; line-height: 1; text-align: center;
  }}
  .liste-dense .nom > span {{ overflow: hidden; text-overflow: ellipsis; }}
  /* La balle vit DANS le groupe des sets et se cale a droite avec eux :
     dans une colonne a elle, elle restait a 83 px de la premiere case --
     tout le vide de la colonne des sets, calee a droite, s'intercalait. */
  .liste-dense .jeux em {{
    font-style: normal; font-size: .78rem; line-height: 1.35;
    flex: none; width: 1.1rem; text-align: center;
  }}
  /* Seules les CASES sont rognees : la balle, hors de ce groupe, ne peut
     pas disparaitre quand un cinquieme set manque de place. */
  .liste-dense .jeux .cases {{
    display: flex; gap: 2px; align-items: center; justify-content: flex-end;
    overflow: hidden;
  }}
  .liste-dense .nom.sert {{ font-weight: 650; }}
  /* Cales a DROITE : le set en cours est le dernier, donc il tombe toujours
     au meme endroit quel que soit le nombre de sets joues. A gauche, un
     match a un set et un match a trois n'alignaient pas leur seule case qui
     bouge encore. */
  .liste-dense .jeux {{ grid-area: jeux; }}
  .liste-dense .jeux span {{
    display: flex; gap: 2px; align-items: center; justify-content: flex-end;
    /* Un score a CINQ sets deborde de sa colonne : sans ce rognage il
       ecrasait la colonne des points -- le « 8 » du cinquieme set par-dessus
       le « 30 », mesure et vu. Cales a droite, ce sont les sets les plus
       ANCIENS qui disparaissent, jamais celui qui se joue. */
    overflow: hidden;
  }}
  .liste-dense .jeux b {{
    background: var(--creux); border-radius: 5px; min-width: 1.35em;
    text-align: center; font-weight: 500; font-size: .8rem;
    line-height: 1.35; padding: 0 .28rem;
  }}
  .liste-dense .jeux b.encours {{
    background: var(--vif); color: #07211b; font-weight: 700;
  }}
  .liste-dense .pts {{
    grid-area: pts; font-size: .8rem; justify-items: end;
  }}
  /* MEME boite pour un point ordinaire et pour une balle de break : le
     badge portait un rembourrage que le texte nu n'avait pas, si bien que
     les chiffres ne tombaient pas au meme endroit d'une ligne a l'autre --
     le « 40 » orange decale par rapport au « 30 » du dessus. */
  .liste-dense .pts span {{
    opacity: .7; line-height: 1.35; padding: .04rem .3rem;
    border-radius: 5px; text-align: right;
  }}
  /* Le seul aplat vif de la ligne, et il ne s'allume qu'a un moment precis :
     le receveur est a un point de rompre le service. */
  .liste-dense .pts span.bp {{
    opacity: 1; background: var(--break); color: #14100c; font-weight: 700;
  }}
  .liste-dense .prix {{ grid-area: prix; }}
  .liste-dense .prix span {{ display: flex; gap: 2px; align-items: center; }}
  .liste-dense .prix i {{
    font-style: normal; font-size: .78rem; line-height: 1.35; padding: 0 .4rem;
    border-radius: 5px; min-width: 3.3em; text-align: right; font-weight: 500;
  }}
  /* La LETTRE double la couleur. Back et lay ne doivent pas se distinguer
     par la seule teinte : un daltonien lirait le carnet a l'envers. */
  .liste-dense .prix i.b::before,
  .liste-dense .prix i.l::before {{
    content: attr(data-c); font-size: .62rem; opacity: .55; margin-right: .28em;
  }}
  .liste-dense .prix i.b {{ color: var(--back); }}
  .liste-dense .prix i.l {{ color: var(--lay); }}
  .liste-dense .prix i.b::before {{ content: "b"; }}
  .liste-dense .prix i.l::before {{ content: "l"; }}
  /* Un prix qui a bouge se detache du fond : le reste de la ligne reste
     nu, donc l'oeil va la ou ca remue -- et nulle part ailleurs. */
  .liste-dense .prix i.hausse, .liste-dense .prix i.baisse {{
    font-weight: 650;
  }}
  .liste-dense .prix i.b.hausse, .liste-dense .prix i.b.baisse {{
    background: var(--back-fond);
  }}
  .liste-dense .prix i.l.hausse, .liste-dense .prix i.l.baisse {{
    background: var(--lay-fond);
  }}
  .liste-dense .prix i.hausse::after {{ content: "▲"; font-size: .5rem; margin-left: .3em; }}
  .liste-dense .prix i.baisse::after {{ content: "▼"; font-size: .5rem; margin-left: .3em; }}
  .liste-dense .prix i.vide {{ opacity: .35; }}
  .liste-dense .ecart {{
    grid-area: ecart;
    /* Assez large pour « 111 / 100 » : replie sur deux lignes, l'ecart
       cassait la hauteur de la ligne et le rythme de la liste. */
    font-size: .7rem; opacity: .68; text-align: right; letter-spacing: .02em;
    white-space: nowrap;
  }}
  .liste-dense .flux {{ grid-area: flux; display: flex; gap: 3px; align-items: center; }}
  .liste-dense .flux em {{
    font-style: normal; font-size: .62rem; color: var(--perime);
    margin-left: .35em; letter-spacing: .02em;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }}
  .liste-dense .flux u {{
    width: 6px; height: 6px; border-radius: 50%; display: block;
    text-decoration: none;
  }}
  /* Ces trois noms sont ceux que rend `fraicheur()` -- pas des synonymes.
     Ils ont diverge une fois : la feuille de style colorait « ok / tiede /
     mort » quand le HTML ecrivait « frais / perime / inconnu », et les
     pastilles sont restees incolores, seule raison d'etre de cette page.
     `test_toute_classe_AFFICHEE_est_bien_stylee` empeche la rechute. */
  .liste-dense .flux u.frais {{ background: var(--frais); }}
  .liste-dense .flux u.perime {{ background: var(--perime); }}
  /* MOBILE. La grille a sept colonnes fixes ne rentre pas sous ~760 px :
     elle debordait, et comme la ligne rogne ce qui depasse (il le faut, le
     bouton de clic ne couvre que la boite), le contenu DISPARAISSAIT
     purement et simplement. Deux lignes valent mieux qu'une amputation.
     Le point de rupture est celui que l'application utilise deja
     (pages/login.py). */
  @media (max-width: 760px) {{
    /* Les DEUX plafonds tombent ensemble. N'en lever qu'un rendait la
       zone cliquable plus large que la zone visible -- on ouvrait un match
       en cliquant dans le vide a sa droite. Le test navigateur l'a repris
       au vol. */
    .liste-dense {{ max-width: none; }}
    div[class*="st-key-{PREFIXE_LIGNE}-"] {{ max-width: none; }}
    div[class*="st-key-{PREFIXE_CARTE}-"] {{ max-width: none; }}
    .liste-dense .match {{
      grid-template-columns: 3rem minmax(0, 1fr) auto 2.2rem;
      grid-template-areas:
        "heure noms  jeux  pts"
        "flux  prix  prix  ecart";
      row-gap: .15rem; padding: .5rem .6rem; gap: .15rem .5rem;
    }}
    /* L'entete nomme les colonnes de la mise en page LARGE : sur deux
       lignes elle designerait le vide. */
    .liste-dense .match.entete {{ display: none; }}
    .liste-dense .flux {{ justify-content: flex-start; }}
    /* Les prix suivent immediatement les pastilles : cales a droite, ils
       laissaient un vide de deux centimetres au milieu de la ligne. */
    .liste-dense .prix {{ justify-self: start; }}
    .liste-dense .prix span {{ gap: .35rem; }}
    .liste-dense .ecart {{ align-self: center; }}
    .liste-dense .noms {{ font-size: .95rem; }}
  }}

  .liste-dense .flux u.inconnu {{
    /* Un contour, pas un aplat : « jamais recu » n'est ni frais ni perime.
       Assez marque pour se voir sur fond clair, ou --trait disparaissait. */
    background: transparent; box-shadow: inset 0 0 0 1px rgba(128,128,128,0.55);
  }}
</style>
"""




#: Les points qu'un jeu classique peut afficher. Un jeu decisif compte en
#: chiffres bruts (« 6-5 ») : on n'y cherche pas de balle de break, il n'y en a
#: pas -- le service alterne a l'interieur.
_POINTS = ("0", "15", "30", "40", "A", "AD")

#: Au-dela, un prix qui a bouge n'est plus un mouvement qu'on regarde : c'est
#: un fait acquis. Le but est de montrer ce qui remue MAINTENANT.
SEUIL_MOUVEMENT_S = 120.0

#: Le nom court de chaque flux, dans l'ordre des pastilles.
#:
#: Il sert a ECRIRE lequel est mort. Les pastilles portaient un `title` qui ne
#: s'est jamais affiche : le bouton invisible qui rend la ligne cliquable
#: recouvre tout, donc le pointeur n'atteint jamais la pastille. On voyait
#: qu'un flux etait rouge, jamais lequel.
NOMS_COURTS = {
    "f_score": "score", "f_exchange": "exchange", "f_books": "prix",
    "f_books_flux": "books", "f_stats": "stats",
}


def balle_de_break(server, points):
    """L'indice (0 ou 1) du joueur qui tient une balle de break, sinon None.

    Le receveur est a un point du jeu s'il a l'avantage, ou s'il est a 40
    quand le serveur n'y est pas : gagner CE point romprait le service. C'est
    la regle du jeu, rien de plus -- et c'est le moment ou un match bascule,
    le seul que cette liste ne montrait pas alors qu'elle en a les elements.

    Rien n'est devine : un serveur inconnu, un score de jeu decisif ou une
    egalite a 40-40 rendent None. Un faux positif serait pire que rien, il
    ferait regarder un match ou il ne se passe pas ce qu'on annonce.
    """
    if server not in ("0", "1"):
        return None
    morceaux = str(points or "").strip().upper().split("-")
    if len(morceaux) != 2:
        return None
    srv = int(server)
    rcv = 1 - srv
    p = [m.strip() for m in morceaux]
    if p[0] not in _POINTS or p[1] not in _POINTS:
        return None
    if p[rcv] in ("A", "AD"):
        return rcv
    if p[rcv] == "40" and p[srv] not in ("40", "A", "AD"):
        return rcv
    return None


def mouvements_de_prix(serie, maintenant: float, seuil: float = SEUIL_MOUVEMENT_S):
    """Par match, le SENS du dernier mouvement de chaque prix.

    On compare le dernier prix a celui d'avant la fenetre : « ce prix a bouge
    depuis deux minutes, et dans quel sens ». Pas une derivee, pas une
    amplitude -- juste de quoi attirer l'oeil sur les lignes qui remuent.

    La comparaison se fait sur ``ts``, l'horodatage de la SOURCE, jamais sur
    l'heure de lecture : c'est la meme regle que partout ailleurs ici, et la
    seule qui garde le sens quand la collecte prend du retard.
    """
    sens = {}
    if serie is None or len(serie) == 0 or "ts" not in serie.columns:
        return sens
    prix = [c for c in ("back_odds_a", "lay_odds_a", "back_odds_b", "lay_odds_b")
            if c in serie.columns]
    for event_id, groupe in serie.groupby("event_id"):
        g = groupe.sort_values("ts")
        recents = g[g["ts"] >= maintenant - seuil]
        if recents.empty or len(g) < 2:
            continue
        avant = g[g["ts"] < maintenant - seuil]
        # Sans releve anterieur a la fenetre, on n'a pas de point de
        # comparaison : ne rien dire plutot que d'annoncer un mouvement
        # depuis le premier releve du match.
        if avant.empty:
            continue
        for colonne in prix:
            debut, fin = avant[colonne].iloc[-1], g[colonne].iloc[-1]
            if pd.isna(debut) or pd.isna(fin) or float(debut) == float(fin):
                continue
            sens.setdefault(str(event_id), {})[colonne] = (
                "hausse" if float(fin) > float(debut) else "baisse")
    return sens


def jeux_par_joueur(score):
    """« 6-2,5-4 » devient deux listes de jeux, une par joueur.

    Un score illisible rend deux listes vides plutot que de lever : la liste
    doit continuer de s'afficher meme si un match publie une chaine bizarre.
    """
    a, b = [], []
    for morceau in str(score or "").split(","):
        parties = morceau.strip().split("-")
        if len(parties) != 2:
            continue
        a.append(parties[0].strip())
        b.append(parties[1].strip())
    return a, b


def etat_fraicheur(m, maintenant: float) -> list:
    """L'etat et l'age de chaque flux, dans l'ordre de ``SEUILS_PAR_FLUX``.

    Cet ordre est le contrat annonce a l'utilisateur par l'infobulle : il
    fait partie de ce qui se teste.
    """
    out = []
    for flux, (cle, seuil, libelle, question) in SEUILS_PAR_FLUX.items():
        age = age_a_la_lecture(m.get(cle), m.get("updated_ts"), maintenant)
        out.append({
            "flux": flux, "etat": fraicheur(age, seuil), "age": age,
            "libelle": libelle, "seuil": seuil, "question": question,
        })
    return out


def lignes(df, maintenant: float, mouvements=None) -> list:
    """La STRUCTURE de la liste, sans une ligne de HTML.

    Tout ce qui peut se tromper est ici : de quel cote est la balle, quel set
    est en cours, quel ecart en ticks, quel etat de fraicheur. ``rendu()``
    n'habille que ca.
    """
    mouvements = mouvements or {}
    out = []
    for _, m in df.iterrows():
        ja, jb = jeux_par_joueur(m.get("score"))
        pts = str(m.get("points") or "").split("-")
        srv = str(m.get("server")) if m.get("server") is not None and not pd.isna(m.get("server")) else None
        bp = balle_de_break(srv, m.get("points"))
        # Les mouvements sont indexes par event_id ; un match fusionne en
        # porte plusieurs, et n'importe lequel peut avoir servi de cle.
        mvt = {}
        for ident in str(m.get("event_ids") or m.get("event_id") or "").split(","):
            mvt.update(mouvements.get(ident.strip(), {}))
        etats = etat_fraicheur(m, maintenant)
        out.append({
            "event_id": str(m.get("event_id") or ""),
            "event_ids": str(m.get("event_ids") or m.get("event_id") or ""),
            "debut": m.get("start_timestamp"),
            "competition": competition(m.get("tour_type"), m.get("league")),
            "tournoi": str(m.get("league") or ""),
            "joueurs": [
                {"nom": str(m.get("participant1") or "?"), "sert": srv == "0",
                 "jeux": ja, "point": pts[0] if len(pts) > 0 else "",
                 "back": m.get("back_odds_a"), "lay": m.get("lay_odds_a"),
                 "bp": bp == 0,
                 "mvt_back": mvt.get("back_odds_a"), "mvt_lay": mvt.get("lay_odds_a")},
                {"nom": str(m.get("participant2") or "?"), "sert": srv == "1",
                 "jeux": jb, "point": pts[1] if len(pts) > 1 else "",
                 "back": m.get("back_odds_b"), "lay": m.get("lay_odds_b"),
                 "bp": bp == 1,
                 "mvt_back": mvt.get("back_odds_b"), "mvt_lay": mvt.get("lay_odds_b")},
            ],
            "ecarts": [ecart_en_ticks(m.get("back_odds_a"), m.get("lay_odds_a")),
                       ecart_en_ticks(m.get("back_odds_b"), m.get("lay_odds_b"))],
            "fraicheur": etats,
            # Ecrire LEQUEL est mort, plutot qu'une pastille rouge anonyme.
            "morts": [NOMS_COURTS.get(f["flux"], f["flux"]) for f in etats
                      if f["etat"] == "perime"],
        })
    return out


def _prix(valeur, classe: str, mouvement=None, neuf: bool = False) -> str:
    """Un prix. La lettre « b »/« l » et la fleche viennent de la feuille de
    style : ce sont des redondances visuelles, pas du contenu.

    La lettre double la couleur -- back et lay ne doivent pas se distinguer
    par la seule teinte, sinon un daltonien lit le carnet a l'envers.

    `neuf` marque ce qui vient de changer depuis le dernier affichage. La
    fleche, elle, porte les deux dernieres minutes : deux echelles de temps,
    deux marques.
    """
    if valeur is None or pd.isna(valeur):
        return '<i class="vide">—</i>'
    bouge = f" {mouvement}" if mouvement in ("hausse", "baisse") else ""
    # `frais`/`perime`/`inconnu` est le vocabulaire de la FRAICHEUR des flux
    # (`etat_fraicheur`, les pastilles) ; ce drapeau-ci est un autre concept,
    # le SURLIGNAGE local de `flux_continu`. Les nommer pareil ferait lire ce
    # `_prix` comme s'il parlait de fraicheur des capteurs.
    marque = " neuf" if neuf else ""
    return f'<i class="{classe}{bouge}{marque}">{float(valeur):.2f}</i>'


def _heure(ts) -> str:
    """L'heure de debut, a l'heure de PARIS.

    `pd.to_datetime(epoch, unit="s")` rend un timestamp NAIF en UTC : le
    `.strftime()` qui suit affichait donc de l'UTC, deux heures en retard
    l'ete et une l'hiver. Signale le 2026-08-11 sur la page en direct.

    `to_paris` convertit et rend un timestamp naif en heure de Paris, pour
    que le formatage en aval ne change pas. Il gere le CHANGEMENT D'HEURE,
    ce qu'un decalage code en dur ne ferait pas -- deux tests l'exigent, un
    par regime.
    """
    if ts is None or pd.isna(ts):
        return "--:--"
    return to_paris(pd.to_datetime(float(ts), unit="s")).strftime("%H:%M")


def entete_competition(ligne) -> str:
    """Le premier niveau : le CIRCUIT, au-dessus de ses tournois.

    Trois niveaux plutot que deux -- competition, tournoi, matchs -- parce
    que « ATP » et « WTA » ne se choisissent pas de la meme facon qu'un
    tournoi : on decide d'abord ou regarder, ensuite lequel.
    """
    c = html.escape(str(ligne["competition"]))
    mots = c.lower().split()
    genre = " ".join(m for m in mots if m in ("atp", "wta", "challenger", "itf"))
    return (f'<div class="liste-dense"><div class="competition {genre}">'
            f"{c}</div></div>")


def _entete(noms: str, circuit: str = "", tournoi: bool = False,
            enveloppe: bool = True) -> str:
    """La ligne d'entete, dessinee par la MEME regle de grille que les matchs.

    Elle partage la classe `match` avec les lignes de donnees : une largeur
    de colonne ne peut pas changer d'un cote sans changer de l'autre. Sa
    cellule de noms reprend jusqu'a la structure INTERNE d'un nom de joueur
    -- marqueur de service compris -- faute de quoi le libelle se cale 22 px
    a gauche des noms qu'il annonce.
    """
    mots = str(circuit).lower().split()
    genre = " ".join(m for m in mots if m in ("atp", "wta", "challenger", "itf"))
    puce = (f'<span class="circuit {genre}">{circuit}</span>'.replace("  ", " ")
            if circuit else "")
    classes = "match entete tournoi" if tournoi else "match entete"
    corps = (
        f'<div class="{classes}">'
        f'<span class="noms"><span class="titre">{noms}</span>{puce}</span>'
        '<span class="jeux">sets</span>'
        '<span class="pts">pt</span>'
        '<span class="prix">back / lay</span>'
        '<span class="ecart">ticks</span>'
        '<span class="flux">flux</span>'
        "</div>"
    )
    return f'<div class="liste-dense">{corps}</div>' if enveloppe else corps


def entete_tournoi(ligne) -> str:
    """La ligne qui annonce un tournoi ET nomme les colonnes.

    La page l'obtenait en decoupant `rendu()` sur la premiere occurrence de
    `<div class="match` -- une chirurgie de chaine qui s'est cassee le jour
    ou l'entete est devenue, elle aussi, une ligne `match`. Une fonction
    dediee ne peut pas se casser ainsi.
    """
    return _entete(html.escape(str(ligne["tournoi"])), tournoi=True)


def entete_colonnes() -> str:
    """Une legende SEULE, pour l'appelant qui n'a pas de tournoi a annoncer.

    La page ne s'en sert plus : la legende flottait au-dessus de la carte,
    visiblement detachee d'elle, et il fallait deux lignes la ou une suffit.
    C'est desormais la ligne de TOURNOI qui porte les libelles de colonnes.
    """
    return _entete("joueur")


def rendu(structure: list, ouvert: str = "", entetes: bool = True,
          section: str = "en-cours") -> str:
    """Le HTML de la liste, regroupee par tournoi.

    Le clic ne passe PAS par un lien : ``<a href="?...">`` rechargeait la
    page, ce qui cree une nouvelle session Streamlit -- et comme
    l'authentification de cette application ne vit que dans
    ``session_state`` (le cookie est commente dans ``pages/login.py``), un
    rechargement DECONNECTE. Constate a l'usage. C'est donc un bouton
    Streamlit voisin qui porte le clic, et ce module ne fait que l'habillage.

    ``entetes`` permet a la page de dessiner les matchs un par un -- un
    bouton chacun -- sans repeter l'entete de tournoi a chaque ligne.

    ``section`` distingue « en cours » de « termines » dans le HTML : les
    deux listes se suivent sur la page et rien d'autre ne permettrait de
    savoir a laquelle une ligne appartient.
    """
    e = html.escape
    ouverts = {i.strip() for i in str(ouvert or "").split(",") if i.strip()}
    morceaux = ['<div class="liste-dense">']
    tournoi_courant = None
    for ligne in structure:
        cle = (ligne["tournoi"], ligne["competition"])
        if entetes and cle != tournoi_courant:
            tournoi_courant = cle
            morceaux.append(
                _entete(e(ligne["tournoi"]), e(ligne["competition"]),
                        tournoi=True, enveloppe=False)
            )
        n_sets = max(len(j["jeux"]) for j in ligne["joueurs"]) or 1
        # La balle occupe TOUJOURS sa colonne, vide quand le joueur ne sert
        # pas : sinon elle pousse le nom du serveur de 40 px et les deux
        # joueurs d'un meme match ne s'alignent plus -- un empilement en
        # dents de scie sur toute la liste. Mesure d'un relecteur, verifiee.
        noms = "".join(
            f'<div class="nom{" sert" if j["sert"] else ""}">'
            f'<span>{e(j["nom"])}</span></div>'
            for j in ligne["joueurs"]
        )
        # Un score ABSENT rend le meme tiret qu'une cote absente (`_prix`).
        # Certains matchs n'ont de score chez AUCUNE source -- l'API ne les
        # annonce pas, le canal `general` d'OrbitX ne les pousse pas -- et leur
        # ligne ne porte QUE des cotes. Laisser la colonne vide se lirait comme
        # un defaut d'affichage ; le tiret dit qu'on ne sait pas, et c'est le
        # vocabulaire deja employe ailleurs dans cette liste.
        jeux = "".join(
            f'<span><em>{"🎾" if j["sert"] else ""}</em>'
            + '<span class="cases">' + ("".join(
                f'<b class="{"encours" if i == n_sets - 1 else ""}'
                f'{" neuf" if j.get("neuf_jeux") and i == n_sets - 1 else ""}">'
                f'{e(v)}</b>'
                for i, v in enumerate(j["jeux"])
            ) or '<i class="vide">—</i>') + "</span></span>"
            for j in ligne["joueurs"]
        )
        # La balle de break ne vient d'aucune colonne : elle se deduit du
        # serveur et des points. C'est le moment ou un match bascule, et le
        # seul que cette liste avait sous la main sans jamais le montrer.
        points = "".join(
            f'<span class="bp{" neuf" if j.get("neuf_point") else ""}">'
            f'{e(j["point"])}</span>' if j["bp"]
            # `class=""` cassait `_cellules()` (tests/test_pages_live.py),
            # qui n'attend qu'un `<span>` nu sur un point ordinaire non
            # marque -- l'attribut ne s'ecrit que s'il y a quelque chose a
            # marquer.
            else f'<span class="neuf">{e(j["point"])}</span>' if j.get("neuf_point")
            else f'<span>{e(j["point"])}</span>'
            for j in ligne["joueurs"]
        )
        prix = "".join(
            "<span>" + _prix(j["back"], "b", j.get("mvt_back"), j.get("neuf_back"))
            + _prix(j["lay"], "l", j.get("mvt_lay"), j.get("neuf_lay")) + "</span>"
            for j in ligne["joueurs"]
        )
        ecarts = " / ".join("—" if t is None else str(t) for t in ligne["ecarts"])
        # Pas de `title` : le bouton invisible qui rend la ligne cliquable
        # recouvre les pastilles, le pointeur ne les atteint jamais. L'age
        # detaille vit dans la fenetre de detail ; ici on nomme seulement ce
        # qui est mort, ce qui suffit a savoir s'il faut aller voir.
        pastilles = "".join(
            f'<u class="{f["etat"]}"></u>' for f in ligne["fraicheur"]
        )
        morts = ligne.get("morts") or []
        if morts:
            # Deux noms au plus, puis un compte : trois noms passaient a la
            # ligne, cassaient le rythme et se faisaient couper par le
            # rognage de la ligne -- on lisait un nom tronque sans le savoir.
            visibles = " ".join(morts[:2])
            reste = f" +{len(morts) - 2}" if len(morts) > 2 else ""
            pastilles += f'<em>{e(visibles)}{reste}</em>' 
        classe = "match ouvert" if ligne["event_id"] in ouverts else "match"
        morceaux.append(
            f'<div class="{classe}" data-section="{e(section)}" '
            f'data-ids="{e(ligne["event_ids"])}">'
            f'<span class="heure">{_heure(ligne["debut"])}</span>'
            f'<span class="noms">{noms}</span>'
            f'<span class="jeux">{jeux}</span>'
            f'<span class="pts">{points}</span>'
            f'<span class="prix">{prix}</span>'
            f'<span class="ecart">{ecarts}</span>'
            f'<span class="flux">{pastilles}</span>'
            "</div>"
        )
    morceaux.append("</div>")
    return "".join(morceaux)
