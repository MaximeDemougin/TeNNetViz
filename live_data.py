"""Lecture des tables temps reel publiees par le PoC de collecte in-play.

Ces fonctions sont ecrites SANS Streamlit et sans etat global : elles se
testent seules, et ce sont elles qui peuvent mentir en silence. Le rendu
vit dans pages/.

Le contrat avec le PoC est le schema des deux tables `TeNNet_test.live_now`
et `TeNNet_test.live_series`, rien d'autre.
"""

import json
import os
import time
from pathlib import Path
from typing import NamedTuple

import pandas as pd
from utils import to_paris

SCHEMA = "TeNNet_test"

# ── Seuils de fraicheur PAR FLUX ─────────────────────────────────────────
#
# Un seuil UNIQUE (30 s, ancienne valeur) applique aux quatre flux affiche
# du rouge PERMANENT sur l'exchange et les books, qui ne publient pas a
# cette cadence -- l'operateur apprend alors a ignorer la pastille, ce qui
# est le mecanisme meme de l'incident d'origine (un capteur mort qui ne se
# voit plus), applique cette fois au rouge plutot qu'au vert. Chaque flux a
# donc son propre seuil, derive de SA cadence de publication propre --
# mesuree par l'agent (score, stats) ou documentee et deja mesuree ailleurs
# dans le depot du PoC (exchange, books) -- jamais suppose.
#
# Score : le capteur n'ecrit qu'au CHANGEMENT d'etat (Live/live_state.py::
# _instant, "score et statistiques : rien... leur reception est donc le seul
# instant connu"), donc pas de cadence periodique.
#
# ATTENTION -- ERREUR CORRIGEE (tour 3) : la premiere version de ce seuil
# (180 s) mesurait les ECARTS ENTRE DEUX CHANGEMENTS consecutifs (mediane
# 27,4 s / p95 103,0 s, NDJSON scores-2026-08-0*.ndjson.gz). C'est la
# MAUVAISE distribution : la page ne lit pas "le temps entre deux
# changements", elle lit "l'age a un instant de lecture QUELCONQUE" -- et un
# instant pris au hasard tombe plus souvent dans un LONG intervalle que dans
# un court (paradoxe de l'inspection). 180 s tombait alors sur le p90 REEL
# de l'age lu, pas au-dela du p95 : ~9,6 % de rouge sur des matchs VIVANTS.
# Remesure sur la BONNE quantite -- l'age tel que la page le lit, echantillonne
# tous les 5 s entre deux changements (agent, meme NDJSON, 205 matchs,
# 243 368 echantillons ; confirme independamment par le relecteur,
# n=49 224) :
#   agent      : mediane 25,0 s / p90 170,0 s / p95 315,0 s / p99 805,0 s
#   relecteur  : mediane 25,5 s / p90 175,3 s / p95 294,5 s / p99 496,4 s
# Les deux s'accordent jusqu'au p95 ; la queue (p99) differe -- filtre
# d'ecarts extremes probablement different (celui-ci ecarte les ecarts >1h
# comme des changements de journee, pas comme un signal de match). Seuil
# choisi a ~2x le p95 MESURE (pas suppose) sur les deux echantillons,
# nettement au-dessus des deux estimations du p99 : taux de rouge attendu
# sur matchs vivants ~1,8 % (agent) a mieux (relecteur, queue plus fine).
SEUIL_FRAICHEUR_SCORE_S = 600.0

# Exchange : source PERIODIQUE, PAS un incident. Live/books.py:257
# documente EXCHANGE_PUBLICATION_PERIOD_SECONDS = 180.0, "mesuree exacte :
# mediane = p25 = p75" (quasi aucune gigue sur la cadence elle-meme) sur
# 8 539 intervalles. Par-dessus cette dent de scie de 0 a 180 s s'ajoute un
# retard publication->reception mesure independamment (mediane 37 s, p90
# 307 s) -- l'age qu'on LIT peut donc legitimement depasser 180 s meme un
# cycle a l'heure. Seuil = 4 x 180 s = 720 s : 1 cycle pour la dent de scie
# elle-meme + jusqu'a ~2 cycles pour absorber le p90 du retard de reception
# (307 s ~= 1,7 cycle, arrondi a 2 par marge) + 1 cycle de tolerance a un
# hoquet, meme logique que LIVE_STALE_SECONDS cote PoC ("un hoquet du
# publieur ne peut pas prononcer un deces").
# CONFIRME (tour 3) : survit a une remesure independante du relecteur --
# conserve tel quel.
SEUIL_FRAICHEUR_EXCHANGE_S = 4 * 180.0

# Books : DEUX QUESTIONS DIFFERENTES, DEUX COLONNES (tour 4 -- decision et
# mesure du publieur, apres que le tour 3 a refute le seuil unique
# 3*227=681s pose ici a l'origine).
#
# La premiere version de ce seuil supposait que c'etait la cadence d'un
# bookmaker qui gouvernait `age_books_s` ; en realite le consensus retient
# le PLUS ANCIEN des `addTime` retenus, SANS PLAFOND, ce qui rend la
# distribution une loi de puissance sans plateau (mesure du relecteur,
# n=47 912 : mediane 229 s, p90 1 037 s, p99 57 530 s, max 141 623 s) --
# aucun seuil fixe ne peut la fermer. Le publieur a tranche : PLAFONNER
# `age_books_s` a 180 s cote publication (Live/books.py::
# DEFAULT_MAX_AGE_SECONDS, deja utilise LA-BAS pour qualifier un prix book
# de "perime" au meme usage), et publier SEPAREMENT l'age du FLUX
# (`age_books_flux_s`, la reception du dernier `api_odds` du match, sans
# plafond). Deux colonnes, deux questions :
#
#   - `age_books_s` = age du PRIX consensus, plafonne [0, 180] ou NULL.
#     Repond a « ce prix est-il encore utilisable ? ». Mesure du publieur
#     avec plafond (rejeu 2026-08-02/03, n=13 498, matchs vivants) :
#     mediane 108 s, p90 162 s, max 179 s -- bornee par construction.
#     Couverture 69,4 % (contre 97,7 % sans plafond : 29,0 % des
#     `book_odds` existantes sont retirees par le plafond -- par
#     definition celles que Live/books.py qualifie d'echos perimes).
#     SEUIL = 180 s, exactement le plafond : au-dela, la valeur elle-meme
#     est NULL (inconnu), jamais perimee au sens de ce seuil -- il ne sert
#     qu'a distinguer un prix jeune (frais) d'un prix juste sous le plafond
#     (perime mais encore present, rare).
#
#     FENETRE DE ROUGE TRES ETROITE, ASSUMEE (releve tour 5) : ce seuil est
#     compare a l'age RECALCULE A LA LECTURE (age_a_la_lecture() = age
#     stocke + temps ecoule depuis updated_ts), pas a l'age stocke seul --
#     alors que le plafond du publieur, lui, ne s'applique qu'a l'age
#     STOCKE au moment d'ecrire la ligne (max 179 s mesure). Consequence :
#     `f_books` ne peut virer rouge que pendant la fenetre entre le moment
#     ou l'age stocke a ete ecrit proche du plafond et le PROCHAIN cycle qui
#     le rafraichit (~5-10 s, la cadence reelle du publieur mesuree plus
#     bas) -- puis redevient blanc des que le prochain cycle republie soit
#     un prix plus frais, soit NULL. Le rouge de cette pastille est donc
#     essentiellement transitoire, pas un etat stable qu'on peut observer
#     longtemps. Assume tel quel : le blanc (prix absent) reste le signal
#     dominant et correct pour "plus utilisable", le rouge n'est qu'un
#     signal furtif en plus, pas la garantie principale de cette colonne.
SEUIL_FRAICHEUR_BOOKS_S = 180.0

#   - `age_books_flux_s` = age du FLUX, l'instant de reception du dernier
#     `api_odds` du match (PAS plafonne : c'est justement l'absence de
#     plafond qui permet de voir un capteur mort). Repond a « le capteur de
#     cotes est-il mort ? ». Mesure du publieur (meme rejeu) : mediane 48 s,
#     p90 224 s, p99 1 229 s, max 2 487 s, couverture 98,0 %. Seuil = 600 s :
#     2,4 % de rouge sur matchs vivants (300 s en donnerait 7,8 %, mesure).
SEUIL_FRAICHEUR_BOOKS_FLUX_S = 600.0

# Stats : meme categorie que score (le capteur "n'ecrit qu'au changement
# d'etat", pas de cadence periodique). Mesure directe (agent, 2026-08-03,
# 3 064 lignes / 164 matchs / 2 896 ecarts, NDJSON stats-2026-08-0*.
# ndjson.gz) : mediane 316,2 s / p90 455,8 s / p95 512,7 s -- un ordre de
# grandeur plus lent que le score (les statistiques de match se mettent a
# jour bien moins souvent que le score lui-meme). Seuil choisi au meme
# multiple du p95 mesure que pour le score (~1,75x) pour garder un raisonnement
# uniforme entre les deux flux "evenementiels" : 1,75 x 512,7 ~= 897,2,
# arrondi a 900.
# CONFIRME (tour 3) : survit a une remesure independante du relecteur (a la
# difference du score, dont la premiere mesure souffrait du paradoxe de
# l'inspection -- voir SEUIL_FRAICHEUR_SCORE_S) -- conserve tel quel.
SEUIL_FRAICHEUR_STATS_S = 900.0

#: Association flux -> (colonne d'age, seuil, libelle lisible, question a
#: laquelle la pastille repond). Source UNIQUE pour le calcul des pastilles
#: ET pour l'infobulle qui explique chaque seuil a l'ecran (pages/live.py) :
#: les deux ne doivent jamais pouvoir diverger. Le 4e element existe
#: SPECIFIQUEMENT pour "books (prix)" et "books (flux)" (tour 4) : deux
#: pastilles voisines, deux quantites d'age plausiblement proches, mais
#: DEUX QUESTIONS differentes -- sans l'affirmer explicitement dans
#: l'infobulle, rien n'empeche l'utilisateur de les confondre.
SEUILS_PAR_FLUX = {
    "f_score": (
        "age_score_s", SEUIL_FRAICHEUR_SCORE_S, "score",
        "le score a-t-il change recemment ?",
    ),
    "f_exchange": (
        "age_exchange_s", SEUIL_FRAICHEUR_EXCHANGE_S, "exchange",
        "le dernier prix exchange est-il encore dans son cycle normal de publication ?",
    ),
    "f_books": (
        "age_books_s", SEUIL_FRAICHEUR_BOOKS_S, "books -- PRIX",
        "ce prix consensus (plafonne a 180 s a la source) est-il encore utilisable ?",
    ),
    "f_books_flux": (
        "age_books_flux_s", SEUIL_FRAICHEUR_BOOKS_FLUX_S, "books -- FLUX",
        "le capteur de cotes bookmakers est-il mort ?",
    ),
    "f_stats": (
        "age_stats_s", SEUIL_FRAICHEUR_STATS_S, "statistiques",
        "les statistiques du match ont-elles change recemment ?",
    ),
}

# Seuil de repli SEULEMENT : compare `updated_ts` (l'instant du dernier
# cycle touchant une ligne) a l'horloge, UNIQUEMENT quand le battement de
# vie du publieur (voir plus bas) est illisible. Depuis le tour 3, un
# battement LISIBLE est AUTORITAIRE et n'a plus besoin de ce seuil-ci --
# corrige exactement le defaut I1 (tour 3) : avant, `updated_ts` seul
# pouvait prononcer un "publieur arrete" qu'un battement FRAIS aurait pu
# dementir, parce que le battement n'etait consulte qu'en dernier recours.
#
# Le nominal PUBLISH_PERIOD_SECONDS = 5 s (cote Live/config.py, PoC de
# collecte) ne dit PAS la duree reelle d'un cycle : Publieur.run fait
# tick() PUIS stop_event.wait(period), et tick() lui-meme prend du temps --
# qui croit avec le nombre de matchs suivis. Deux mesures independantes sur
# le publieur EN SERVICE le confirment :
#   - agent, 2026-08-03, 90 s / 10 intervalles (live_now.updated_ts des
#     matchs InPlay) : min 7,10 s / mediane 7,57 s / max 8,13 s.
#   - relecture independante, 9 min / 78 cycles : min 5,93 s / mediane
#     7,37 s / max 10,19 s -- avec la remarque que l'intervalle grossit
#     avec le nombre de matchs suivis et avait deja double dans la journee.
# Le projet applique deja une marge de x6 au nominal pour son propre seuil
# de fraicheur par flux (PUBLISH_FRESH_SECONDS = 30 = 6 x PUBLISH_PERIOD_
# SECONDS = 5, "sans quoi la page afficherait du rouge en regime normal").
# Meme marge (x6), mais appliquee a la MEDIANE MESUREE (7,37 s, l'echantillon
# le plus long) plutot qu'au nominal qui ne represente pas la duree reelle :
# 6 * 7,37 ~= 44,2, arrondi a 45.
#
# ATTENTION (I1a, tour 3) : entre ce seuil (45 s) et LIVE_STALE_SECONDS=120
# cote publieur (l'instant ou une ligne EN COURS, plus touchee, est
# reetiquetee "Finished"), il existe une fenetre de ~75 s ou une ligne est
# encore InPlay et deja perimee au sens de CE seuil-ci -- mesuree en
# service, PUBLIEUR VIVANT dans toute la fenetre. Avant le tour 3, ce seuil
# a lui seul suffisait a declencher "publieur arrete" dans cette fenetre, a
# chaque fin de match, sans que le battement (pourtant frais) puisse s'y
# opposer. Depuis le tour 3 ce seuil n'est plus consulte QUE si le
# battement est illisible -- la fenetre ne produit plus de fausse alerte
# tant que le battement repond.
SEUIL_PUBLIEUR_ARRETE_S = 45.0

# Seuil de staleness d'un BATTEMENT DE VIE lui-meme (heartbeat-publish.json
# ou heartbeat-score.json, meme mecanisme -- Live.supervise.Heartbeat,
# HEARTBEAT_SECONDS=30 cote PoC). PAS le meme seuil que SEUIL_PUBLIEUR_
# ARRETE_S ci-dessus : celui-la juge la cadence des LIGNES de live_now,
# celui-ci juge la cadence du FICHIER de battement, deux mecanismes
# distincts.
#
# VALEUR REPRISE, PAS RE-DERIVEE : identique, deliberement, a
# ``HEARTBEAT_STALE_SECONDS`` defini dans ``Live/config.py`` du DEPOT
# TeNNetPy (le PoC de collecte -- chemin absolu typique sur cette machine :
# ``/home/ubuntu/TeNNetPy/Live/config.py``, ligne ~177 au tour 3). Ce depot
# la justifie deja pour interpreter CE MEME fichier ("genereux devant la
# cadence... une fausse alerte de mutisme coute la confiance qu'on met dans
# le signal") -- reprendre ce nombre plutot que d'en inventer un troisieme
# est precisement ce que demandait I1a : que les deux seuils ne soient plus
# choisis chacun dans son depot sans jamais se comparer.
#
# RISQUE DE DERIVE SILENCIEUSE : si ``HEARTBEAT_STALE_SECONDS`` change un
# jour cote TeNNetPy, RIEN ici ne le detecte automatiquement -- TeNNetViz
# est un depot separe qui ne l'importe pas (seulement les FICHIERS que ce
# depot ecrit, jamais son code). Quiconque modifie cette constante la-bas
# doit penser a revenir ici. A defaut d'un lien automatique entre les deux
# depots, ce commentaire est le seul repere : que la prochaine personne qui
# cherche pourquoi ce nombre vaut 300 sache ou regarder.
SEUIL_BATTEMENT_ARRETE_S = 300.0

# Meme convention que Live/config.py::DATA_DIR et Live/supervise.py::
# heartbeat_path(nom) cote PoC (TeNNetViz ne les importe pas -- depot
# separe -- mais lit les MEMES fichiers qu'ils ecrivent) : variable
# d'environnement TENNET_LIVE_DATA, repli sur /home/ubuntu/tennet_live_data.
#
# COUPLAGE NON GARANTI, A SURVEILLER (releve tour 5) : le cron du publieur
# (cote TeNNetPy) pose TENNET_LIVE_DATA EXPLICITEMENT dans son environnement
# (`TENNET_LIVE_DATA=/home/ubuntu/tennet_live_data`, verifie le 2026-08-04
# dans l'environnement du process Live.publish_live reellement en service).
# CE process Streamlit, lui, ne l'a PAS (verifie de meme, absent) -- il
# repose entierement sur le repli ci-dessous.
#
# ET EN LIGNE, IL N'Y A PAS DE REPERTOIRE DU TOUT. Sur Streamlit Community
# Cloud, le conteneur n'a ni ce disque ni ces fichiers : les battements y
# sont TOUJOURS absents. Ce n'est pas une panne, et surtout ce n'est pas
# l'arret propre d'un capteur -- c'est pourquoi `capteur_score_mort()`
# corrobore l'absence avec `updated_ts` (lu en base, disponible partout)
# avant de conclure, et pourquoi `publieur_arrete()` retombe sur le meme
# signal. Sans cette corroboration, la page en ligne annoncerait six
# capteurs arretes alors qu'ils tournent.
#
# Les deux coincident aujourd'hui sur cette machine, mais rien ne les LIE :
# si l'environnement du cron change un jour (deploiement different,
# variable renommee, autre machine), le repli ici resterait a l'ancienne
# valeur SANS AUCUNE ERREUR -- lire_battement_publieur()/lire_battement_score()
# degradent proprement sur un chemin absent (voir _lire_fichier_battement),
# ce qui rend ce battement simplement "illisible" plutot que de faire
# planter quoi que ce soit. Consequence concrete : publieur_arrete()
# retomberait alors sur son repli updated_ts (le comportement d'AVANT le
# tour 3), et la fenetre de fausse alerte I1a (~75 s a chaque fin de match)
# reviendrait silencieusement, sans qu'aucune exception ni log ne le
# signale ici. Pas d'action prise ce tour (pas de mecanisme de verification
# croisee entre deux depots distincts sans dependance) -- seulement
# documente, pour que la prochaine personne qui doit diagnostiquer un
# retour de cette fausse alerte sache par ou commencer.
_REPERTOIRE_BATTEMENTS = Path(
    os.environ.get("TENNET_LIVE_DATA", "/home/ubuntu/tennet_live_data")
)
CHEMIN_BATTEMENT_PUBLIEUR = _REPERTOIRE_BATTEMENTS / "heartbeat-publish.json"
#: Le capteur de SCORE est un process distinct du publieur (voir I1b) :
#: `Publieur._marquer_termines` est gardee par son propre battement
#: (`Publieur._capteur_de_score_vivant`, cote PoC) et refuse de reetiqueter
#: les lignes "Finished" quand il est muet -- les lignes restent InPlay,
#: `updated_ts` gele, jusqu'a la purge de retention (6 h). Sans lire CE
#: battement-ci, la page ne peut pas distinguer "le publieur est mort" de
#: "le publieur est vivant mais le capteur de score s'est tu" : deux
#: diagnostics, deux actions de reparation, un seul coupable accuse si on ne
#: regarde que le publieur.
CHEMIN_BATTEMENT_SCORE = _REPERTOIRE_BATTEMENTS / "heartbeat-score.json"

# CONTRAT A TROIS ETATS, PAS DEUX (releve tour 6) -- ce module l'ignorait
# jusqu'ici et ca a coute un defaut de plus (voir capteur_score_mort()).
#
# ``Live/supervise.py::Heartbeat.clear()`` (depot TeNNetPy, lignes ~249-256)
# documente explicitement pourquoi le fichier de battement est SUPPRIME (pas
# laisse tel quel) a l'arret propre d'un capteur :
#
#   "Retire la preuve de vie, a l'arret PROPRE du capteur. Un battement
#   laisse derriere un capteur arrete se lirait comme un capteur vivant
#   pendant toute la duree du seuil de mutisme. Apres un arret propre il
#   n'y a plus rien a attester ; apres un plantage, le fichier reste et
#   vieillit -- ce qui est exactement le signal recherche."
#
# Trois etats du fichier, trois significations, AUCUNE n'est "je ne sais
# pas" :
#   1. FRAIS (age <= seuil)  -> le capteur tourne.
#   2. VIEUX (age > seuil)   -> le capteur a PLANTE (le fichier existe,
#      personne ne le reecrit plus).
#   3. ABSENT (aucun fichier) -> le capteur s'est ARRETE PROPREMENT
#      (Heartbeat.clear() l'a retire lui-meme). C'est le signal le PLUS NET
#      des trois, pas un silence -- mais il faut le distinguer d'un fichier
#      present-mais-illisible (JSON tronque, permissions...), qui LUI reste
#      genuinement ambigu (aucune semantique documentee cote PoC pour ce
#      cas). Voir ``battement_absent()``.
#
# Nuance a ne pas perdre (celle qui a fait la difference entre ce tour et le
# precedent) : l'absence ne doit JAMAIS etre lue comme "arrete" en isolation
# -- au tout premier demarrage du systeme, avant que le tout premier
# battement n'ait ete ecrit, le fichier est ABSENT sans qu'aucun capteur ne
# soit jamais tombe. L'absence doit donc etre CORROBOREE par un second
# signal independant (ici, des lignes EN COURS dont ``updated_ts`` a gele)
# avant de conclure -- voir ``capteur_score_mort()``.

# Les six series du graphique de cotes. L'ordre fixe l'ordre de la legende.
SERIES_COTES = (
    "back_odds_a", "lay_odds_a",
    "back_odds_b", "lay_odds_b",
    "book_odds_a", "book_odds_b",
)


def fraicheur(age_s, seuil: float) -> str:
    """« frais », « perime » ou « inconnu ».

    Un age absent rend « inconnu » et JAMAIS « frais » : un flux dont on
    ignore l'age ne doit surtout pas s'afficher en vert. C'est ce defaut qui
    a laisse le capteur de cotes passer pour vivant pendant des heures alors
    qu'il n'ecrivait plus rien.

    ATTENTION : ``age_s`` doit etre l'age VRAI au moment de la lecture (voir
    ``age_a_la_lecture``), pas l'age stocke tel quel par le publieur. Un age
    stocke fige (publieur mort) reste petit pour toujours ; c'est exactement
    le defaut C4 que cette fonction, seule, ne peut pas voir -- elle ne fait
    que comparer le nombre qu'on lui donne a un seuil.

    ``seuil`` est OBLIGATOIRE, sans defaut : les quatre flux ont des
    cadences de publication trop differentes (score et exchange n'ont pas le
    meme ordre de grandeur, voir ``SEUILS_PAR_FLUX``) pour qu'une valeur par
    defaut soit jamais la bonne pour tout le monde. Un defaut aurait
    exactement reproduit le defaut que ce tour corrige : un seuil pense pour
    un flux, applique par accident a un autre.
    """
    if age_s is None or pd.isna(age_s):
        return "inconnu"
    return "frais" if float(age_s) <= float(seuil) else "perime"


def age_a_la_lecture(age_stocke, updated_ts, maintenant: float | None = None):
    """Age VRAI d'un flux au moment de la LECTURE, pas au moment du cycle.

    Le publieur calcule ``age_stocke`` (l'age d'un flux donne, ex.
    ``age_score_s``) ET ``updated_ts`` (l'instant epoch UTC du cycle) UNE
    SEULE FOIS, au moment d'ecrire la ligne. Si le publieur meurt, la ligne
    cesse de changer et ``age_stocke`` reste fige au dernier cycle reussi --
    pour toujours « frais » si on le relit tel quel. C'est exactement le
    defaut qui a laisse le capteur de cotes passer pour vivant pendant des
    heures : la page existe pour empecher ca, et ne le faisait pas.

    L'age reel a l'instant de la lecture est ``age_stocke + (maintenant -
    updated_ts)`` : on rattrape le temps ecoule depuis le cycle qui a ecrit
    la ligne, en plus de l'age que ce cycle avait deja mesure.

    - ``age_stocke`` absent (ce flux precis n'a jamais ete recu -- fait
      INDEPENDANT de la sante du publieur, ex. pas de marche exchange
      apparie) -> inconnu, propage tel quel.
    - ``updated_ts`` absent ou illisible -> inconnu : sans lui, impossible de
      savoir depuis combien de temps la ligne n'a pas bouge.
    - ``updated_ts`` dans le futur (derive d'horloge entre le publieur et
      cette machine) -> le delta ecoule est borne a zero plutot que negatif,
      meme convention que ``Live.live_state.age`` cote publieur : un flux ne
      doit jamais paraitre plus frais que ce que son propre age stocke
      indiquait deja.

    ``maintenant`` est injectable pour les tests ; en service vaut
    ``time.time()`` -- LA MEME HORLOGE (epoch UTC) que celle utilisee par le
    publieur pour ecrire ``updated_ts`` (``time.time()`` dans
    ``Live/publish_live.py``, cote PoC). Un decalage de fuseau entre lecture
    et ecriture ferait virer toutes les pastilles au rouge, ou aucune.
    """
    if age_stocke is None or pd.isna(age_stocke):
        return None
    try:
        age_stocke = float(age_stocke)
    except (TypeError, ValueError):
        return None
    if updated_ts is None or pd.isna(updated_ts):
        return None
    try:
        updated_ts = float(updated_ts)
    except (TypeError, ValueError):
        return None
    if maintenant is None:
        maintenant = time.time()
    ecoule = max(0.0, float(maintenant) - updated_ts)
    return age_stocke + ecoule


def _lire_fichier_battement(chemin: Path) -> dict | None:
    """Relit un signe de vie ecrit par ``Live.supervise.Heartbeat`` cote PoC.

    ``None`` = absent OU illisible (fichier manquant, JSON tronque, chemin
    inaccessible) : dans tous les cas ca n'atteste rien PAR ELLE-MEME,
    jamais une exception qui remonterait a l'ecran. Rejoint le cas ou cette
    page tournerait un jour dans le conteneur du ``Dockerfile`` du depot :
    le ``docker-compose.yml`` actuel ne monte que le depot lui-meme
    (``./:/app``), pas ce repertoire hote -- le fichier serait alors
    simplement absent, et cette fonction degraderait proprement plutot que
    de planter. (Verifie le 2026-08-03 : le processus Streamlit reellement
    en service sur cette machine tourne nativement, pas dans ce conteneur ;
    la lecture fonctionne donc aujourd'hui, mais ne doit pas y etre
    suspendue.)

    ATTENTION (tour 6) : cette fonction seule ne distingue PAS "absent" de
    "illisible", alors que ces deux ``None`` n'ont pas le meme sens cote PoC
    -- voir le commentaire au-dessus de ``CHEMIN_BATTEMENT_SCORE`` et
    ``battement_absent()``. Un appelant qui a besoin de cette distinction
    (``capteur_score_mort()``) appelle les deux.
    """
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def battement_absent(chemin: Path) -> bool:
    """Vrai si AUCUN fichier n'existe a ce chemin -- distinct d'un fichier
    PRESENT mais illisible (JSON tronque, permissions...), que cette
    fonction ne detecte PAS (elle rend ``False`` dans ce cas : le fichier
    existe).

    Cette distinction porte un sens documente cote PoC (voir le commentaire
    au-dessus de ``CHEMIN_BATTEMENT_SCORE``, qui cite
    ``Live/supervise.py::Heartbeat.clear()``) : l'ABSENCE d'un battement est
    l'arret PROPRE d'un capteur, un signal aussi net que "frais" ou "vieux"
    -- alors qu'un fichier corrompu n'a aucune semantique documentee, et
    reste genuinement ambigu.

    Petite course possible (le fichier peut apparaitre/disparaitre entre cet
    appel et une lecture ulterieure) : sans consequence ici, la pire erreur
    possible est une pastille qui se corrige au prochain rafraichissement de
    la page, pas une decision irreversible.
    """
    return not Path(chemin).exists()


def lire_battement_publieur(chemin: Path = CHEMIN_BATTEMENT_PUBLIEUR) -> dict | None:
    """Signe de vie du PROCESS PUBLIEUR (``Publieur.tick`` l'ecrit a CHAQUE
    cycle, meme sans aucun match a publier -- contrairement a ``live_now``,
    qui ne dit plus rien quand elle est vide)."""
    return _lire_fichier_battement(chemin)


def lire_battement_score(chemin: Path = CHEMIN_BATTEMENT_SCORE) -> dict | None:
    """Signe de vie du CAPTEUR DE SCORE, process DISTINCT du publieur (voir
    I1b / ``CHEMIN_BATTEMENT_SCORE``) : le publieur peut battre normalement
    pendant que ce capteur-ci s'est tu, et c'est alors LUI qu'il faut
    accuser, pas le publieur."""
    return _lire_fichier_battement(chemin)


def age_du_battement(battement: dict | None, maintenant: float | None = None):
    """Age du signe de vie, meme convention que ``age_a_la_lecture`` :
    battement absent/illisible ou sans ``ts`` -> inconnu ; horloge future ->
    borne a zero plutot que negatif."""
    if not isinstance(battement, dict):
        return None
    ts = battement.get("ts")
    if ts is None or pd.isna(ts):
        return None
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return None
    if maintenant is None:
        maintenant = time.time()
    return max(0.0, float(maintenant) - ts)


def publieur_arrete(df: pd.DataFrame, maintenant: float | None = None,
                     seuil: float = SEUIL_PUBLIEUR_ARRETE_S,
                     seuil_battement: float = SEUIL_BATTEMENT_ARRETE_S,
                     lire_battement=None) -> bool:
    """Vrai si le publieur semble ne plus tourner -- le signalement en tete
    de la page liste.

    Le battement de vie (voir ``lire_battement_publieur``) est AUTORITAIRE
    des qu'il est lisible : un battement FRAIS emporte un VETO sur ce que
    ``updated_ts`` pourrait dire, et un battement PERIME suffit a conclure
    a l'arret, sans consulter ``updated_ts`` du tout.

    Correctif I1a (tour 3) : avant, ``updated_ts`` etait consulte EN
    PREMIER et ``df`` etait considere PLUS TOT que le battement s'il n'etait
    pas vide -- un verdict "arrete" tire de lignes perimees ne pouvait alors
    JAMAIS etre dementi par un battement pourtant frais. Mesure en service :
    entre ce seuil (45 s) et ``LIVE_STALE_SECONDS`` = 120 s cote publieur
    (l'instant ou une ligne EN COURS, plus touchee, est reetiquetee
    "Finished"), une fenetre de ~75 s laisse des lignes InPlay et perimees
    a CHAQUE fin de match, publieur pourtant vivant -- l'ancien ordre y
    declenchait une fausse alerte a coup sur.

    Le repli sur ``updated_ts`` (comparaison au max de ``df["updated_ts"]``,
    matchs EN COURS uniquement -- un match termine cesse legitimement
    d'etre touche, et ``live_now`` n'est jamais purgee avant 6 h) ne sert
    plus QUE quand le battement est illisible (fichier absent, JSON
    tronque, chemin inaccessible). C'est la seule situation ou ``updated_ts``
    reste le MEILLEUR signal disponible.

    ``lire_battement`` est injectable pour les tests (``None`` retombe sur
    ``lire_battement_publieur`` au moment de l'appel -- pas au moment de la
    definition -- pour rester monkeypatchable depuis un test qui rejoue la
    PAGE, pas seulement cette fonction).

    Une absence totale de signal (battement illisible ET tableau vide/sans
    ``updated_ts``) ne prouve rien sur la sante du publieur : on ne signale
    rien plutot que de fabriquer une fausse alerte.

    VOIR AUSSI ``publieur_ecritures_refusees()`` : un battement frais prouve
    que le PROCESS tourne, pas que ses ECRITURES vers ``live_now``
    reussissent -- deux questions distinctes, cf. le defaut IMPORTANT 1
    releve au tour 5.

    VERIFIE (tour 6) : contrairement a ``capteur_score_mort()``, cette
    fonction n'a PAS besoin de distinguer "battement absent" (arret propre,
    voir ``battement_absent()`` et le commentaire au-dessus de
    ``CHEMIN_BATTEMENT_SCORE``) de "battement illisible" (corrompu, ambigu).
    Raison : elle a DEJA un repli sur ``updated_ts`` pour tout battement
    non-lisible, quelle qu'en soit la cause -- et ce repli est EXACTEMENT le
    mecanisme de corroboration qu'exige un traitement correct de
    l'absence (ne pas conclure a l'arret sans preuve independante que les
    lignes ont vraiment gele). Absent ou corrompu, le publieur reellement
    arrete laisse ``updated_ts`` vieillir de la meme facon dans les deux
    cas, et ce repli le detecte deja, sans distinction necessaire. Ajouter
    la distinction ici n'aurait rien change au verdict final -- seulement a
    la VITESSE de detection dans le cas "absent" (une reponse plus rapide,
    sans attendre le repli), au prix de reintroduire le risque de fausse
    alerte au demarrage que ce meme repli protege deja. Pas fait : le gain
    ne compensait pas le risque, pour une fonction qui fonctionne deja
    correctement (confirme par la revue de cloture, tour 5).
    """
    if maintenant is None:
        maintenant = time.time()
    if lire_battement is None:
        lire_battement = lire_battement_publieur
    age_battement = age_du_battement(lire_battement(), maintenant)
    if age_battement is not None:
        return age_battement > seuil_battement
    if df is not None and not df.empty and "updated_ts" in df.columns:
        plus_recent = pd.to_numeric(df["updated_ts"], errors="coerce").max()
        if pd.notna(plus_recent):
            return (float(maintenant) - float(plus_recent)) > seuil
    return False


def publieur_ecritures_refusees(df: pd.DataFrame, maintenant: float | None = None,
                                 seuil: float = SEUIL_PUBLIEUR_ARRETE_S,
                                 seuil_battement: float = SEUIL_BATTEMENT_ARRETE_S,
                                 lire_battement=None) -> bool:
    """Vrai si le publieur est VIVANT (battement frais) mais que ses
    ECRITURES vers ``live_now`` semblent refusees -- IMPORTANT 1, tour 5.

    Regression introduite PAR le correctif I1a (tour 3), releve a la revue
    de cloture : rendre le battement AUTORITAIRE pour ``publieur_arrete()``
    signifiait aussi qu'un battement frais fait ``return`` avant meme de
    regarder ``updated_ts`` -- correct pour DEMENTIR une fausse mort (c'est
    ce qui etait demande), mais ca laisse un trou : ``Live.db_utils.
    execute_query`` (cote PoC) avale ses exceptions et rend ``False`` en cas
    d'echec d'ecriture ; ``Publieur.tick()`` compte chaque echec dans
    ``n_echecs`` MAIS CONTINUE DE BATTRE -- le process vit, le battement
    reste frais, et pourtant plus aucune ligne n'est ecrite. Sonde du
    relecteur : ligne InPlay gelee depuis 1h + battement frais avec
    ``state.n_echecs=12`` -> ``publieur_arrete()`` rend ``False`` (correct,
    ce n'est PAS le process qui est mort) mais AUCUN bandeau n'apparaissait
    nulle part avant ce correctif -- alors que le battement qu'on vient de
    lire porte lui-meme la reponse.

    ``state.n_echecs`` est le signal PRIORITAIRE et, s'il est present,
    DEFINITIF : le publieur (cote PoC, voir ``Publieur.tick``) l'inclut a
    CHAQUE battement reel, meme quand il vaut 0 -- ``n_echecs=0`` documente
    positivement "aucun echec d'ecriture ce cycle", ce n'est pas une absence
    d'information. Dans ce cas, on ne retombe PAS sur ``updated_ts`` :
    une ligne EN COURS peut legitimement rester perimee quelques dizaines
    de secondes sans qu'aucune ecriture n'ait echoue (le match qui vient de
    finir a simplement cesse d'etre reporte par le flux de score -- c'est
    exactement le cas qu'I1a distingue deja, cf. ``publieur_arrete()``, pas
    un echec d'ecriture). Le repli sur ``updated_ts`` ne sert donc QUE si
    ``state`` est absent ou ne documente pas ``n_echecs`` du tout (format de
    battement different, champ manquant) -- une situation degradee ou
    ``updated_ts`` reste le meilleur signal disponible, faute de mieux.
    """
    if maintenant is None:
        maintenant = time.time()
    if lire_battement is None:
        lire_battement = lire_battement_publieur
    battement = lire_battement()
    age_battement = age_du_battement(battement, maintenant)
    if age_battement is None or age_battement > seuil_battement:
        # Battement illisible ou perime : c'est publieur_arrete() qui juge
        # ce cas, pas celui-ci -- eviter tout chevauchement de diagnostic.
        return False
    etat = battement.get("state") if isinstance(battement, dict) else None
    n_echecs = etat.get("n_echecs") if isinstance(etat, dict) else None
    if isinstance(n_echecs, (int, float)) and not isinstance(n_echecs, bool):
        # Documente explicitement, y compris quand il vaut 0 : reponse
        # DEFINITIVE, on ne consulte pas updated_ts par-dessus.
        return n_echecs > 0
    if df is not None and not df.empty and "updated_ts" in df.columns:
        plus_recent = pd.to_numeric(df["updated_ts"], errors="coerce").max()
        if pd.notna(plus_recent):
            return (float(maintenant) - float(plus_recent)) > seuil
    return False


def capteur_score_mort(df: pd.DataFrame, maintenant: float | None = None,
                        seuil: float = SEUIL_PUBLIEUR_ARRETE_S,
                        seuil_battement: float = SEUIL_BATTEMENT_ARRETE_S,
                        lire_battement=None, est_absent=None) -> bool:
    """Vrai si le CAPTEUR DE SCORE (process distinct du publieur) semble
    mort -- correctif I1b (tour 3), complete par le tour 6 (voir plus bas).

    ``Publieur._marquer_termines`` est gardee, cote PoC, par le battement de
    CE capteur (``Publieur._capteur_de_score_vivant``) : quand il est muet,
    le publieur refuse de reetiqueter les matchs "Finished" (decision juste
    LA-BAS -- reetiqueter sans savoir si le match est vraiment fini serait
    pire). Consequence cote page, jamais visible avant le tour 3 : les
    lignes restent "InPlay", ``updated_ts`` gele, jusqu'a la purge de
    retention (6 h) -- alors que le publieur, LUI, peut battre normalement
    pendant tout ce temps. Sans ce signal-ci, la page accuserait le
    publieur (via ``publieur_arrete``, qui rend ``False`` puisque SON
    battement est frais) de rien du tout, en silence, pendant six heures.

    TROIS ETATS DU BATTEMENT, PAS DEUX (tour 6 -- voir le commentaire au-
    dessus de ``CHEMIN_BATTEMENT_SCORE`` pour la source complete) :

    1. Battement lisible -> son age tranche directement (frais/vieux).
    2. Battement ABSENT (aucun fichier, voir ``battement_absent()``) ->
       arret PROPRE du capteur (``Heartbeat.clear()`` cote PoC l'a retire
       lui-meme) -- un signal, pas un silence. Premiere version de cette
       fonction (tour 3-5) traitait ce cas comme "illisible" et rendait
       toujours ``False`` : un capteur de score arrete proprement (le mode
       d'ARRET NORMAL, pas un cas de bord) ne declenchait donc AUCUN
       bandeau -- les pastilles rougissaient (vrai), mais rien ne disait
       QUEL process relancer, alors que le systeme de fichiers portait deja
       la reponse. Corrobore neanmoins avec ``updated_ts`` (matchs EN
       COURS) avant de conclure, meme motif que le repli de
       ``publieur_arrete()`` : au tout premier demarrage du systeme, avant
       le tout premier battement jamais ecrit, le fichier est ABSENT sans
       qu'aucun capteur ne soit jamais tombe -- l'absence seule ne doit
       jamais hurler.
    3. Battement PRESENT mais illisible (JSON tronque, permissions...) ->
       reste ambigu, aucune semantique documentee pour ce cas precis
       (contrairement a l'absence) : pas de repli, pas de fausse alerte.

    ``est_absent`` est injectable pour les tests (``None`` retombe sur
    ``battement_absent(CHEMIN_BATTEMENT_SCORE)`` au moment de l'appel, meme
    motif que ``lire_battement``).
    """
    if maintenant is None:
        maintenant = time.time()
    if lire_battement is None:
        lire_battement = lire_battement_score
    if est_absent is None:
        est_absent = lambda: battement_absent(CHEMIN_BATTEMENT_SCORE)
    age = age_du_battement(lire_battement(), maintenant)
    if age is not None:
        return age > seuil_battement
    if not est_absent():
        # Present mais illisible : ambigu, pas de signal documente.
        return False
    # ABSENT : arret propre, corrobore par updated_ts avant de conclure.
    if df is not None and not df.empty and "updated_ts" in df.columns:
        plus_recent = pd.to_numeric(df["updated_ts"], errors="coerce").max()
        if pd.notna(plus_recent):
            return (float(maintenant) - float(plus_recent)) > seuil
    return False


def _lecteur_par_defaut():
    """Le lecteur de production, importe SANS laisser le repertoire courant
    deplace.

    ``db_utils/db_utils.py`` fait un ``os.chdir(project_path)`` A L'IMPORT
    (ligne 34). Notre import est DIFFERE -- au premier appel, pas en tete de
    module -- donc ce chdir survient pendant le rendu d'une page, longtemps
    apres que ``st.navigation`` a ete construit.

    Sans restauration, le repertoire courant d'un appelant qui n'etait PAS
    a la racine se retrouve deplace sous ses pieds. Historiquement la
    destination etait ``db_utils/`` (l'ancien ``globals.py`` y cherchait
    ``credentials.yml``) et le rechargement suivant cherchait
    ``pages/login.py`` depuis ce repertoire : l'application tombait avec
    « Unable to create Page », constate en service reel le 2026-08-03
    (incident ``145b76d``). La destination est aujourd'hui la RACINE, ce qui
    rend ce mode de panne-la improbable -- mais le deplacement, lui, a
    toujours lieu, et il n'appartient pas a ce module de le laisser fuir.
    """
    ancien = os.getcwd()
    try:
        from db_utils.db_utils import read_sql_query
    finally:
        os.chdir(ancien)
    return read_sql_query


def charger_matchs(lecteur=None) -> pd.DataFrame:
    """Tous les matchs publies, les plus recemment mis a jour d'abord.

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe jusqu'ici (et non en tete de module) :
    ``db_utils.globals`` lit ``credentials.yml`` des l'import, absent en
    local -- differer garantit que les tests, qui injectent toujours un
    ``lecteur``, ne touchent jamais ce fichier.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    df = lire(SCHEMA, "SELECT * FROM live_now ORDER BY updated_ts DESC")
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    # Fusion AVANT le calcul de `en_cours` : le statut fait partie des champs
    # que la fusion prend a la ligne au score le plus frais, et le calculer
    # d'abord le figerait sur une ligne perimee du groupe.
    df = fusionner_doublons(df)
    df["en_cours"] = ~df["status"].astype(str).str.lower().isin(
        {"finished", "ended", "completed", "retired", "walkover", "cancelled"}
    )
    return df


def _identifiants_surs(event_id) -> list:
    """Les ``event_id`` demandes, nettoyes de tout ce qui sort d'un litteral.

    ``event_id`` vient de ``st.query_params`` cote page : modifiable par
    n'importe qui dans l'URL. On ne parametre pas la requete (pas d'API de
    parametres bindes exposee par ``read_sql_query``) ; retirer TOUTES les
    apostrophes empeche toute evasion du litteral SQL entre quotes -- c'est
    cette propriete, pas un simple nettoyage cosmetique, qui rend la ligne
    sure.

    Un event_id finissant par un antislash echapperait la quote fermante
    (`'...\\'  ORDER BY...`) : ce n'est pas une porte d'injection (le
    litteral ne se referme jamais, la requete est juste invalide), mais
    l'erreur SQL qui en resulte remonterait comme "Base de donnees
    injoignable", un message qui pointerait vers la mauvaise cause. Retirer
    aussi les antislashs le rend impossible.

    UNE SEULE implementation, partagee par ``charger_serie``,
    ``charger_points`` et ``charger_mouvements`` : ce depot tient deja
    qu'ecrire deux fois la meme regle garantit qu'une correction n'atterrisse
    que d'un cote (voir ``detail_match``, partage entre les deux pages). Pour
    une regle de SECURITE, le cote oublie serait celui qu'on ne verrait
    jamais -- et donc celui qu'il faut nommer ici a chaque nouveau client,
    sous peine de mentir sur ce que "une seule implementation" protege.

    Accepte plusieurs identifiants -- separes par des virgules ou donnes en
    liste -- parce que la source attribue parfois deux ou trois ``event_id``
    a une meme rencontre. Rend une liste VIDE quand rien d'exploitable ne
    reste : c'est a l'appelant de ne pas interroger la base plutot que
    d'envoyer un ``IN ()``, qui est une erreur de syntaxe MySQL.
    """
    if event_id is None:
        return []
    bruts = event_id if isinstance(event_id, (list, tuple, set)) else \
        str(event_id).split(",")
    surs = [
        str(e).replace("'", "").replace("\\", "").strip()
        for e in bruts
    ]
    return [e for e in surs if e]


def _litteral_liste(valeurs) -> str:
    """La liste d'un ``IN (...)``, chaque valeur entre quotes.

    N'echappe RIEN : elle suppose ses entrees deja passees par
    ``_identifiants_surs``. Separee pour que les deux lecteurs produisent le
    meme texte, pas pour ajouter une garantie.
    """
    return ", ".join(f"'{v}'" for v in valeurs)


def charger_serie(event_id, lecteur=None) -> pd.DataFrame:
    """La serie d'un match, dans l'ordre du temps.

    Parametree par ``event_id`` pour ne charger que ce match : c'est l'index
    (event_id, ts) qui rend cette requete instantanee quel que soit le poids
    de la table.

    ``event_id`` accepte PLUSIEURS identifiants, separes par des virgules ou
    donnes en liste. La source attribue parfois deux ou trois ``event_id`` a
    une meme rencontre (cf. ``fusionner_doublons``), et la serie est alors
    repartie entre eux -- mesure du 2026-08-04 : sur un match en direct, un
    identifiant portait les cotes bookmakers et les statistiques que l'autre
    n'avait pas. N'en lire qu'un afficherait un demi-graphique sans le dire.

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe jusqu'ici (et non en tete de module),
    meme motif que ``charger_matchs`` : ``db_utils.globals`` lit
    ``credentials.yml`` des l'import, absent en local -- differer garantit
    que les tests, qui injectent toujours un ``lecteur``, ne touchent jamais
    ce fichier.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    surs = _identifiants_surs(event_id)
    if not surs:
        return pd.DataFrame()
    # Le ORDER BY porte sur `ts` SEUL et non sur (event_id, ts) : les series
    # de deux identifiants d'un meme match doivent s'entrelacer dans le temps,
    # pas se suivre bout a bout -- sans quoi la courbe reviendrait en arriere
    # au milieu du graphique.
    liste = _litteral_liste(surs)
    df = lire(
        SCHEMA,
        f"SELECT * FROM live_series WHERE event_id IN ({liste}) ORDER BY ts",
    )
    if df is None:
        return pd.DataFrame()
    # Chaque identifiant ecrit sa ligne au MEME horodatage a chaque cycle :
    # sans ce repliement, le tableau point par point montrerait deux lignes
    # par instant, avec des scores en desaccord jusqu'a un jeu entier.
    #
    # La famille est DECLAREE : cette fonction promet « la serie d'un match »,
    # donc les identifiants qu'elle a recus sont parents par construction.
    # Sans cette declaration la fusion ne replierait plus rien -- c'est le
    # sens meme de la correction du 2026-08-10.
    return fusionner_series(df, famille=surs)


#: Les seules colonnes dont le SENS d'un prix a besoin. `SELECT *` en lisait
#: quatorze pour en utiliser six.
COLONNES_MOUVEMENT = ("event_id", "ts", "back_odds_a", "lay_odds_a",
                      "back_odds_b", "lay_odds_b")


def charger_mouvements(event_id, lecteur=None) -> pd.DataFrame:
    """Ce qu'il faut, et rien de plus, pour dire quels prix remuent.

    La liste appelait ``charger_serie`` pour toute la liste des matchs en
    cours, uniquement pour nourrir ``mouvements_de_prix``. Mesure du
    2026-08-10 : 341 ms, dont 48 de SQL et **289 de fusion** -- 85 % du cycle
    dans une boucle pandas ligne a ligne. Or la liste n'a jamais eu besoin de
    la fusion : ``mouvements_de_prix`` regroupe par ``event_id``, et
    ``lignes()`` refusionne ensuite les identifiants d'un meme match. Et la
    fusion, appliquee a plusieurs matchs, DETRUISAIT l'information (cf.
    ``fusionner_series``). Ce lecteur-ci : 16 ms.

    La fenetre temporelle n'est volontairement PAS reduite. ``live_series``
    ecrit au CHANGEMENT et non a cadence fixe -- ecarts medians de 8 a 101 s
    selon le match, trous mesures jusqu'a 1354 s. Une fenetre de dix minutes
    perdrait le releve de reference d'avant la fenetre de mouvement, donc des
    fleches. La lenteur n'etait pas dans le volume lu.

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe, meme motif que ``charger_serie``.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    surs = _identifiants_surs(event_id)
    if not surs:
        return pd.DataFrame()
    liste = _litteral_liste(surs)
    df = lire(
        SCHEMA,
        f"SELECT {', '.join(COLONNES_MOUVEMENT)} FROM live_series "
        f"WHERE event_id IN ({liste}) ORDER BY ts",
    )
    return df if df is not None else pd.DataFrame()


# ── Les tables du PASSE ───────────────────────────────────────────────
#
# `live_now` et `live_series` portent le direct ; `live_qa_daily`,
# `live_matches` et `live_points` portent ce qui a ete collecte. Meme motif
# que les deux lecteurs ci-dessus -- SCHEMA du PoC, lecteur injectable,
# import differe -- et pour les memes raisons.
#
# Ces trois lecteurs ne CALCULENT rien. `Live/qa_report.py` calcule deja les
# indicateurs de sante et les ecrit dans `live_qa_daily` : les recalculer
# ici creerait deux verites qui divergeraient (§7 du design).


def charger_bilan_qa(lecteur=None) -> pd.DataFrame:
    """Le bilan quotidien de la collecte, du plus ancien au plus recent.

    Une ligne par journee, ecrite chaque nuit par ``Live/qa_report.py`` cote
    PoC. L'ordre est CHRONOLOGIQUE : c'est lui qui rend la tendance lisible
    (le taux de trou passe de 97 % a 51 % entre le 3 et le 5 aout 2026, la
    fenetre exacte de la correction d'authentification). Sans ``ORDER BY``,
    MySQL ne promet aucun ordre.

    Les absences restent des absences : les journees sans marche vu en jeu
    portent ``match_rate`` a NULL, relu en NaN, et ce lecteur n'y touche
    pas. Les convertir en zero ferait passer une journee NON MESUREE pour
    une journee catastrophique -- c'est le piege que ``juger_qa`` refuse
    plus bas, et qu'il ne pourrait plus voir si la conversion avait lieu
    ici.

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe jusqu'ici (et non en tete de module),
    meme motif que ``charger_matchs``.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    df = lire(SCHEMA, "SELECT * FROM live_qa_daily ORDER BY day")
    if df is None or df.empty:
        return pd.DataFrame()
    return df


def charger_matchs_passes(lecteur=None) -> pd.DataFrame:
    """Les matchs identifies par la collecte, le plus recent d'abord.

    Une ligne par (journee, event_id) -- pas par match : un match a cheval
    sur deux journees en produit deux (mesure du 2026-08-07 : 1 153 lignes
    sur 10 jours), et la source attribue parfois deux ``event_id`` a une
    meme rencontre.

    ``matched`` est rendu tel quel (0/1) et non filtre : les matchs jamais
    vus en direct par l'exchange sont une information de la liste, pas un
    dechet. ATTENTION -- ce taux d'appariement-la (416/1 153 au prelevement)
    n'est PAS ``match_rate`` du bilan, qui porte sur les seuls marches vus
    en jeu et hors ambigus ; les melanger produirait un chiffre qui ne veut
    rien dire (§4 du design).

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe jusqu'ici, meme motif que
    ``charger_matchs``.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    df = lire(
        SCHEMA,
        "SELECT * FROM live_matches ORDER BY day DESC, start_ts DESC",
    )
    if df is None or df.empty:
        return pd.DataFrame()
    return df


def charger_points(event_id, lecteur=None) -> pd.DataFrame:
    """Le point par point d'un match, dans l'ordre de reception.

    Parametree par ``event_id`` pour ne charger que ce match : la table
    porte 176 208 lignes au prelevement du 2026-08-07, et c'est l'index
    (event_id) qui rend cette requete instantanee.

    ``event_id`` accepte PLUSIEURS identifiants, separes par des virgules ou
    donnes en liste, exactement comme ``charger_serie`` -- et pour la meme
    raison, verifiee en donnees : 3799286 et 3802032 sont la meme rencontre
    (meme ``match_id`` dans ``live_matches``) et portent respectivement 2 et
    105 points. N'en lire qu'un rendrait la moitie du match sans le dire.

    MEME PRECAUTION que ``charger_serie`` sur le litteral SQL : ``event_id``
    vient de l'URL, il passe par ``_identifiants_surs`` avant d'entrer dans
    la requete. Rien a lire -> aucune requete du tout : ``IN ()`` est une
    erreur de syntaxe MySQL, qui remonterait a l'ecran comme une base
    injoignable.

    Le ORDER BY porte sur ``recv_ts`` SEUL, pas sur (event_id, recv_ts) :
    les points des deux identifiants d'un meme match doivent s'entrelacer
    dans le temps, pas se suivre bout a bout.

    A la difference de ``charger_serie``, AUCUN repliement n'est applique :
    ``live_series`` ecrit une ligne par cycle (donc des repetitions a etat
    de jeu inchange), alors que ``live_points`` n'ecrit qu'au CHANGEMENT.
    Replier ici effacerait de vrais points.

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe jusqu'ici, meme motif que
    ``charger_matchs``.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    surs = _identifiants_surs(event_id)
    if not surs:
        return pd.DataFrame()
    liste = _litteral_liste(surs)
    df = lire(
        SCHEMA,
        f"SELECT * FROM live_points WHERE event_id IN ({liste}) "
        "ORDER BY recv_ts",
    )
    if df is None or df.empty:
        return pd.DataFrame()
    return df


# ── Les seuils de sante de la COLLECTE ────────────────────────────────
#
# VALEURS REPRISES, PAS RE-DERIVEES : identiques, deliberement, a
# ``QA_MIN_MATCH_RATE``, ``QA_MIN_PBP_COHERENCE`` et ``QA_MAX_GAP_RATIO``
# definis dans ``Live/config.py`` du DEPOT TeNNetPy (le PoC de collecte --
# chemin absolu typique sur cette machine : ``/home/ubuntu/TeNNetPy/Live/
# config.py``, lignes 768-770 au prelevement du 2026-08-07). C'est
# ``Live/qa_report.py`` qui les applique la-bas, sur les memes trois
# metriques, ecrites chaque nuit dans ``live_qa_daily`` -- la table que
# cette page lit. Reprendre ces nombres plutot que d'en inventer d'autres
# est la seule facon que la page dise « hors seuil » au meme moment que le
# PoC.
#
# RISQUE DE DERIVE SILENCIEUSE : si l'un de ces trois change un jour cote
# TeNNetPy, RIEN ici ne le detecte automatiquement -- TeNNetViz est un depot
# separe qui ne l'importe pas (il ne lit que les TABLES que ce depot ecrit,
# jamais son code). Quiconque modifie ces constantes la-bas doit penser a
# revenir ici. A defaut d'un lien automatique entre les deux depots, ce
# commentaire et ``test_les_trois_seuils_sont_epingles_sur_ceux_du_poc``
# sont les seuls reperes. Meme convention que
# ``SEUIL_BATTEMENT_ARRETE_S`` plus haut, pour la meme raison.
#
# LE SENS N'EST PAS LE MEME POUR LES TROIS, et c'est le piege principal :
# les deux premiers sont des MINIMA (en dessous = mauvais), le troisieme un
# MAXIMUM (au-dessus = mauvais). Le sens est porte par ``INDICATEURS_QA``
# ci-dessous, pas par une suite de comparaisons ecrites a la main, pour
# qu'il se relise d'un coup d'oeil.
SEUIL_QA_MATCH_RATE_MIN = 0.90
SEUIL_QA_PBP_COHERENCE_MIN = 0.95
SEUIL_QA_GAP_RATIO_MAX = 0.05


class IndicateurQA(NamedTuple):
    """Un indicateur du bilan : son seuil, son SENS, et ce qu'il compte."""

    seuil: float
    #: "min" -> en dessous du seuil c'est mauvais ; "max" -> au-dessus.
    sens: str
    libelle: str
    #: Le DENOMINATEUR, affiche avec le taux. Deux taux d'appariement
    #: circulent dans cette page et ne comptent pas la meme chose (§4 du
    #: design) : sans son denominateur, un pourcentage ne veut rien dire.
    denominateur: str


INDICATEURS_QA = {
    "match_rate": IndicateurQA(
        SEUIL_QA_MATCH_RATE_MIN, "min", "Appariement",
        "des marchés vus en jeu, hors appariements ambigus",
    ),
    "pbp_coherence": IndicateurQA(
        SEUIL_QA_PBP_COHERENCE_MIN, "min", "Cohérence du point par point",
        "des jeux communs au direct et au pbp",
    ),
    "gap_ratio": IndicateurQA(
        SEUIL_QA_GAP_RATIO_MAX, "max", "Trou de collecte",
        "du temps in-play passé sans aucune trame",
    ),
}

#: Les trois verdicts possibles. « Pas de mesure » est un etat A PART
#: ENTIERE, ni conforme ni hors seuil : c'est tout l'objet du piege du
#: denominateur nul.
SANS_MESURE = "sans_mesure"
CONFORME = "conforme"
HORS_SEUIL = "hors_seuil"


def juger_qa(indicateur: str, valeur) -> str:
    """Confronte UNE valeur du bilan a SON seuil, dans SON sens.

    Rend ``SANS_MESURE`` quand la valeur est absente -- et c'est le point
    important. Quatre journees (28 au 31 juillet 2026) n'ont vu aucun
    marche in-play : leur ``match_rate`` est NULL en base, relu en NaN.
    NaN echoue TOUTES les comparaisons (il n'est ni inferieur ni superieur
    a quoi que ce soit), donc un jugement naif les declarerait conformes ;
    les convertir en zero les declarerait catastrophiques. Les deux mentent,
    et le second est le pire : quatre journees a « 0 % de sante » noieraient
    l'information vraie des journees mesurees.

    Le PoC refuse deja cette division a la source (``Live/qa_report.py::
    _ratio`` : "une journee creuse n'est pas un echec de collecte") ; on ne
    la reintroduit pas de ce cote-ci.

    DIVERGENCE ASSUMEE avec ``Live/qa_report.py::evaluate``, qui compte une
    metrique absente comme un ECHEC : la-bas c'est une porte de cloture (on
    ne declare pas conforme ce qu'on n'a pas su mesurer), ici c'est un
    AFFICHAGE. Un tableau de bord qui peint en rouge ce qu'il n'a pas
    mesure apprend a son lecteur a ignorer le rouge -- exactement le mode
    de panne que ce depot combat ailleurs (les pastilles de fraicheur).

    Le sens, lui, est repris tel quel : ``<`` pour un minimum, ``>`` pour un
    maximum, donc l'EGALITE est conforme des deux cotes, comme cote PoC.
    """
    if indicateur not in INDICATEURS_QA:
        # Pas de defaut : un indicateur sans seuil connu ne doit pas se
        # juger « conforme » par accident. Meme regle que `fraicheur`, qui
        # exige un seuil explicite -- un silence vert est le mode de panne
        # que ce depot combat.
        raise KeyError(
            f"indicateur de bilan inconnu : {indicateur!r} "
            f"(connus : {', '.join(sorted(INDICATEURS_QA))})"
        )
    spec = INDICATEURS_QA[indicateur]
    if valeur is None or pd.isna(valeur):
        return SANS_MESURE
    valeur = float(valeur)
    if spec.sens == "min":
        return HORS_SEUIL if valeur < spec.seuil else CONFORME
    return HORS_SEUIL if valeur > spec.seuil else CONFORME


def tendance_qa(indicateur: str, valeurs) -> str:
    """« amelioration », « degradation », « stable » ou « inconnue ».

    Compare la derniere valeur MESUREE a la precedente valeur mesuree, en
    sautant les absences : comparer une mesure a une absence ne dit rien.

    Le SENS compte ici autant que pour le seuil, et a l'envers d'un
    indicateur a l'autre. Le fait que la table portait sans que personne le
    releve : ``gap_ratio`` passe de 97,21 % (3 aout) a 62,53 % (4 aout) --
    une BAISSE, donc une amelioration, la fenetre exacte de la correction
    d'authentification. Lue avec le sens d'un minimum, cette meme baisse
    s'afficherait en degradation : la page annoncerait une panne le jour
    d'une reparation.

    « inconnue » quand il n'y a pas deux mesures a comparer -- et surtout
    pas « stable », qui se lirait comme une mesure.
    """
    spec = INDICATEURS_QA[indicateur] if indicateur in INDICATEURS_QA else None
    if spec is None:
        raise KeyError(f"indicateur de bilan inconnu : {indicateur!r}")
    mesurees = [
        float(v) for v in list(valeurs)
        if not (v is None or pd.isna(v))
    ]
    if len(mesurees) < 2:
        return "inconnue"
    avant, apres = mesurees[-2], mesurees[-1]
    if apres == avant:
        return "stable"
    monte = apres > avant
    ameliore = monte if spec.sens == "min" else not monte
    return "amelioration" if ameliore else "degradation"


def bilan_juge(df: pd.DataFrame) -> pd.DataFrame:
    """Le bilan, augmente d'une colonne ``verdict_<indicateur>`` par
    indicateur.

    Le jugement s'AJOUTE : les valeurs brutes restent, pour que le rendu
    affiche le chiffre a cote du verdict -- un verdict sans son chiffre ne
    se verifie pas. Copie, jamais mutation en place : le meme tableau est
    relu ailleurs dans la page.

    Un indicateur absent de la table (schema plus ancien, colonne renommee
    cote PoC) rend ``SANS_MESURE`` plutot que de lever : la page doit rester
    debout et le dire, pas tomber.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    juge = df.copy()
    for nom in INDICATEURS_QA:
        valeurs = juge[nom] if nom in juge.columns else [None] * len(juge)
        juge[f"verdict_{nom}"] = [juger_qa(nom, v) for v in valeurs]
    return juge


def serie_longue(df: pd.DataFrame) -> pd.DataFrame:
    """Les six series de cotes en forme longue, pour Altair.

    Les valeurs absentes ne produisent AUCUN point : un match sans marche
    s'affiche avec son score, mais ne doit pas dessiner une cote a zero --
    zero se lirait comme un prix, et un prix a zero est une certitude.

    Une serie sans colonne ``ts`` degrade au tableau vide plutot que de
    lever un ``KeyError`` brut jusqu'a l'interface : ``ts`` est garanti par
    le ``ORDER BY`` de ``charger_serie`` en usage normal, mais l'interface
    ne doit JAMAIS dependre de cette garantie pour rester debout.
    """
    if df is None or df.empty or "ts" not in df.columns:
        return pd.DataFrame(columns=["ts", "serie", "cote"])
    presentes = [c for c in SERIES_COTES if c in df.columns]
    longue = df.melt(
        id_vars=["ts"], value_vars=presentes,
        var_name="serie", value_name="cote",
    )
    return longue.dropna(subset=["cote"]).reset_index(drop=True)


def evenements(df: pd.DataFrame) -> pd.DataFrame:
    """Les instants a marquer d'un trait vertical.

    Seules deux valeurs existent, ``fin_de_jeu`` et ``fin_de_set``, parce
    qu'elles se deduisent du SCORE SEUL et sont donc exactes. Le BREAK exige
    de savoir qui servait, et le champ serveur de la source se contredit dans
    13 % des jeux : le publieur n'en marque jamais, et cette fonction n'en
    invente pas.

    Meme garde que ``serie_longue`` pour la colonne ``ts`` : degrader au
    tableau vide plutot que de lever, elle est garantie par ``charger_serie``
    mais l'interface ne doit jamais en dependre pour ne pas planter.
    """
    if (
        df is None or df.empty
        or "evenement" not in df.columns or "ts" not in df.columns
    ):
        return pd.DataFrame(columns=["ts", "evenement"])
    garde = df["evenement"].isin(("fin_de_jeu", "fin_de_set"))
    return df.loc[garde, ["ts", "evenement"]].reset_index(drop=True)


#: Ce que chaque flux apporte a la ligne fusionnee. Pour chaque flux on prend
#: la ligne du groupe dont l'AGE de ce flux est le plus petit, et on lui
#: emprunte son age ET les champs qu'il alimente. Aucun autre decoupage n'est
#: possible : c'est exactement la structure que le publieur ecrit, un age par
#: flux, et c'est ce qui rend la fusion sure -- on ne melange jamais un prix
#: avec l'age d'un autre releve.
_FLUX_FUSION = (
    ("age_score_s", ("score", "points", "status", "server")),
    ("age_exchange_s", ("id_market", "back_odds_a", "lay_odds_a",
                        "back_odds_b", "lay_odds_b")),
    ("age_books_s", ("book_odds_a", "book_odds_b")),
    ("age_books_flux_s", ()),
    ("age_stats_s", ()),
)


def fusionner_doublons(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par MATCH, la ou la source en emet parfois plusieurs.

    La source attribue parfois DEUX -- vu jusqu'a TROIS -- ``event_id`` a une
    meme rencontre. ``live_now`` ayant ``event_id`` pour cle primaire, la
    liste affichait alors le match autant de fois. Mesure du 2026-08-04 :
    5 groupes en doublon sur 16 lignes.

    Le regroupement se fait sur ``id_market`` ET la paire de joueurs, pas sur
    l'un des deux seul. Le marche est le rattachement le plus sur -- c'est
    l'exchange qui l'attribue, independamment des noms, et toutes les lignes
    d'un groupe observe portaient le MEME -- mais un marche peut etre reutilise
    d'un jour a l'autre (cf. ``_flag_reused_markets`` cote PoC), d'ou les noms
    en second garde-fou. Sans marche apparie, les noms et le tournoi suffisent.

    On ne CHOISIT pas une ligne : on les FUSIONNE. Mesure sur deux matchs en
    direct : aucune des deux lignes ne domine l'autre -- l'une portait le score
    le plus frais (2 s contre 33 s), l'autre les cotes bookmakers et les
    statistiques que la premiere n'avait pas. En garder une seule perdrait de
    la donnee dans les deux sens.

    ``event_ids`` porte tous les identifiants du groupe : la serie temporelle
    est elle aussi repartie entre eux, et la page detail en a besoin pour ne
    pas afficher un demi-graphique.
    """
    if df is None or df.empty or "event_id" not in df.columns:
        return df if df is not None else pd.DataFrame()

    def _cle(ligne):
        marche = str(ligne.get("id_market") or "").strip()
        p1 = str(ligne.get("participant1") or "").strip()
        p2 = str(ligne.get("participant2") or "").strip()
        if not marche and not (p1 and p2):
            # Ni marche apparie, ni paire de joueurs : on ne SAIT PAS de quel
            # match il s'agit. Deux lignes ainsi anonymes partageraient une
            # cle vide et seraient fusionnees -- deux rencontres differentes
            # reduites a une. On retombe donc sur l'event_id, qui est unique :
            # ne pas conclure plutot que confondre. Defaut attrape par
            # `test_le_tableau_des_matchs_separe_en_cours_et_termines` le
            # 2026-08-04, sur une fixture sans identite.
            return ("__seul__", str(ligne.get("event_id")), "", "")
        return (marche, p1, p2, str(ligne.get("league") or "").strip())

    cles = df.apply(_cle, axis=1)
    sorties = []
    for _, groupe in df.groupby(cles, sort=False):
        if len(groupe) == 1:
            ligne = groupe.iloc[0].copy()
            ligne["event_ids"] = str(ligne["event_id"])
            sorties.append(ligne)
            continue
        # La ligne de base est celle au score le plus frais : c'est elle qui
        # porte l'identite qu'on veut voir en tete, et son event_id est celui
        # que « Voir le detail » doit ouvrir en premier.
        base = _plus_frais(groupe, "age_score_s")
        fusion = base.copy()
        for age, champs in _FLUX_FUSION:
            if age not in groupe.columns:
                continue
            meilleure = _plus_frais(groupe, age, exiger=True)
            if meilleure is None:
                continue
            fusion[age] = meilleure[age]
            for champ in champs:
                if champ in groupe.columns:
                    fusion[champ] = meilleure[champ]
        if "updated_ts" in groupe.columns:
            fusion["updated_ts"] = groupe["updated_ts"].max()
        fusion["event_ids"] = ",".join(str(e) for e in groupe["event_id"])
        sorties.append(fusion)
    return pd.DataFrame(sorties).reset_index(drop=True)


def _plus_frais(groupe: pd.DataFrame, colonne: str, exiger: bool = False):
    """La ligne du groupe dont ``colonne`` (un age) est la plus petite.

    ``exiger`` ecarte les ages ABSENTS. C'est la difference entre « ce flux
    n'a jamais parle pour cet identifiant » et « il a parle il y a zero
    seconde » -- la confusion que tout ce paquet combat, et qui ferait ici
    preferer une ligne muette a une ligne renseignee.
    """
    if colonne not in groupe.columns:
        return None if exiger else groupe.iloc[0]
    valides = groupe[groupe[colonne].notna()]
    if valides.empty:
        return None if exiger else groupe.iloc[0]
    return valides.loc[valides[colonne].idxmin()]


#: Ordre des points d'un jeu de tennis. « A » est l'avantage.
_RANG_POINT = {"0": 0, "15": 1, "30": 2, "40": 3, "A": 4, "AD": 4}


def avancement(score, points) -> tuple:
    """Ou en est le match : (jeux joues, points du jeu courant).

    L'ordre lexicographique de ce couple EST l'ordre du temps dans un match :
    les jeux d'abord (ils remettent les points a zero), les points ensuite.
    C'est ce qui permet de dire laquelle de deux vues d'un meme instant est
    la plus avancee, sans avoir besoin de savoir laquelle vient de quel
    identifiant.

    Un score ou des points illisibles rendent ``-1`` pour la composante
    concernee : ils perdent contre n'importe quelle valeur lisible, ce qui est
    le comportement voulu -- on ne prefere jamais une vue qu'on ne sait pas
    lire.
    """
    try:
        jeux = sum(
            int(a) + int(b)
            for a, b in (s.strip().split("-") for s in str(score).split(","))
        )
    except Exception:
        jeux = -1
    try:
        a, b = str(points).split("-")
        ra = _RANG_POINT.get(a.strip().upper(), -1)
        rb = _RANG_POINT.get(b.strip().upper(), -1)
        pts = -1 if (ra < 0 or rb < 0) else ra + rb
    except Exception:
        pts = -1
    return (jeux, pts)


def fusionner_series(df: pd.DataFrame, famille=None) -> pd.DataFrame:
    """Une ligne par INSTANT, pour les identifiants qu'on a declares parents.

    ``charger_serie`` lit tous les identifiants d'un meme match (cf.
    ``fusionner_doublons``). Chacun ecrit sa propre ligne a CHAQUE cycle du
    publieur, donc au MEME horodatage : sans repliement, le tableau point par
    point affiche deux lignes par instant, portant des scores differents.
    Constate a l'usage le 2026-08-04.

    Mesure sur les deux matchs concernes : les deux vues sont d'accord sur
    les cotes de l'exchange dans 100 % des cas (c'est le meme marche), mais
    en desaccord sur le score dans 77 % des instants doubles -- et l'ecart
    porte sur un JEU ENTIER 5 et 30 fois. La cote du bookmaker, elle, n'est
    presente que d'UN cote (45 et 77 fois) : c'est precisement pour ne pas la
    perdre qu'on lit les deux identifiants.

    On garde donc, par instant, le score le PLUS AVANCE, et pour chaque autre
    colonne la premiere valeur renseignee. Jamais de moyenne : deux vues d'un
    meme carnet ne se moyennent pas, l'une est simplement en retard.

    ``famille`` DECLARE quels identifiants sont parents, et c'est la seule
    facon de le savoir : ``live_series`` ne porte aucune colonne « match »,
    l'appartenance vient de ``live_now.event_ids`` et de nulle part ailleurs.
    Sans declaration, deux identifiants distincts ne se replient JAMAIS.

    C'est la correction du defaut du 2026-08-10 : la fonction groupait sur
    ``ts`` SEUL, ce qui revenait a tenir un horodatage commun pour une
    appartenance commune. La page « En direct » lui passait les six matchs en
    cours d'un coup ; le publieur les ecrit dans le meme cycle, donc au meme
    instant. Mesure contre ``TeNNet_test`` : 342 horodatages sur 439 partages
    entre plusieurs matchs, 726 lignes sur 1165 ecrasees -- 62 % -- et les
    survivantes comblaient leurs colonnes vides avec les valeurs d'un AUTRE
    match. Trois matchs sur six perdaient leur fleche de mouvement, et l'une
    des trois restantes pointait a l'envers.
    """
    if df is None or df.empty or "ts" not in df.columns:
        return df if df is not None else pd.DataFrame()
    declaree = {str(e) for e in (famille or [])}
    if "event_id" in df.columns:
        # Les membres declares partagent la cle vide : eux seuls se replient
        # entre eux. Tout autre identifiant garde la sienne, donc sa ligne.
        parente = df["event_id"].map(
            lambda e: "" if str(e) in declaree else str(e))
    else:
        # Sans identifiant, rien ne permet de distinguer deux matchs : on ne
        # peut que grouper sur l'instant. N'arrive jamais en service.
        parente = pd.Series("", index=df.index)
    travail = df.assign(_parente=parente)
    if not travail.duplicated(subset=["_parente", "ts"]).any():
        return df.reset_index(drop=True)
    sorties = []
    for _, groupe in travail.groupby(["_parente", "ts"], sort=True):
        if len(groupe) == 1:
            sorties.append(groupe.iloc[0])
            continue
        rangs = [
            avancement(l.get("score"), l.get("points"))
            for _, l in groupe.iterrows()
        ]
        base = groupe.iloc[rangs.index(max(rangs))].copy()
        for colonne in groupe.columns:
            if colonne in ("score", "points", "ts", "event_id", "_parente"):
                continue
            if pd.isna(base.get(colonne)):
                renseignees = groupe[colonne].dropna()
                if not renseignees.empty:
                    base[colonne] = renseignees.iloc[0]
        sorties.append(base)
    # Le tri sur `ts` est desormais EXPLICITE. Il l'etait implicitement tant
    # qu'on groupait sur `ts` seul ; grouper d'abord par parente le perdrait,
    # et les series de deux identifiants doivent s'entrelacer dans le temps
    # -- sans quoi la courbe revient en arriere au milieu du graphique.
    return (pd.DataFrame(sorties)
            .drop(columns=["_parente"])
            .sort_values("ts", kind="stable")
            .reset_index(drop=True))


def competition(tour_type, league) -> str:
    """« ATP », « WTA », « ATP CHALLENGER »... -- le circuit et le niveau.

    Le niveau se lit dans le NOM du tournoi et nulle part ailleurs : ni la
    source ni les tables ne le portent. Regle volontairement pauvre, la meme
    que ``Live.model_bench.tour_level`` cote PoC -- « challenger » ou « itf »
    dans le libelle, sinon circuit principal -- parce que c'est exactement ce
    que les libelles observes permettent de distinguer.

    Le circuit reste visible meme sur un Challenger : « ATP CHALLENGER » et
    « WTA CHALLENGER » ne sont pas la meme population, et la liste sert a
    choisir ou regarder.
    """
    circuit = str(tour_type or "").strip().upper() or "?"
    nom = str(league or "").lower()
    if "challenger" in nom:
        return f"{circuit} CHALLENGER"
    if "itf" in nom:
        return f"{circuit} ITF"
    return circuit


def nom_tournoi(league) -> str:
    """Le tournoi, tel qu'on veut le LIRE dans une liste dense.

    Depuis la bascule du flux de score sur Goalserve (2026-08-16), les
    categories s'appellent « Challenger Men - Singles: Roehampton (United
    Kingdom) - Qualification, Hard ». La famille est DEJA portee par la
    colonne de competition, le pays n'apprend rien, et la ligne devient
    illisible. On garde la ville, la surface, et deux marqueurs.

    CES DEUX MARQUEURS NE SONT PAS COSMETIQUES.

    « Qualification » reste : un tableau de qualification n'a le plus souvent
    AUCUN marche en face -- mesure du 2026-08-16, zero occurrence chez OrbitX
    pour les qualifs de Sion -- et le confondre avec le tableau final ferait
    chercher des cotes qui n'existent pas.

    « Doubles » reste : sans lui, le double de Todi et le simple de Todi
    s'affichent a l'identique.

    Un libelle d'une AUTRE forme est rendu tel quel. « Astana Challenger »
    est la nomenclature de la source precedente, et elle vit encore dans les
    lignes de moins de sept jours : on ne devine pas.
    """
    texte = str(league or "").strip()
    if ":" not in texte:
        return texte
    famille, _, reste = texte.partition(":")
    while "(" in reste and ")" in reste:
        avant, _, apres = reste.partition("(")
        _, _, apres = apres.partition(")")
        reste = f"{avant.strip()} {apres.strip()}"
    reste = " ".join(reste.split()).replace(" ,", ",").strip()
    if not reste:
        return texte
    if "doubles" in famille.lower():
        reste = f"{reste} (doubles)"
    return reste


def a_joue(score, points, cotes_bougent: bool = False) -> bool:
    """Vrai des qu'au moins un point a ete joue, OU que le marche est suivi.

    Un match annonce mais pas commence encombre la liste sans rien apprendre :
    il n'a ni score, ni points, ET SES COTES NE BOUGENT PAS. C'est cette
    derniere condition qui compte depuis le 2026-08-10, et elle etait deja
    dans l'intention d'origine : certains matchs n'ont de score chez AUCUNE
    source -- l'API ne les annonce pas, le canal `general` d'OrbitX ne les
    pousse pas -- alors que leur carnet arrive a quatre secondes. Le PoC les
    publie desormais sous `source_score = "exchange_seul"`, et les ecarter ici
    reviendrait a cacher la SEULE donnee qu'on ait sur eux.

    On s'appuie sur ``avancement``, la meme mesure qui sert a departager deux
    vues d'un meme instant -- une seule definition de « ou en est le match »
    dans tout le module.

    Un score illisible rend FAUX : sans savoir lire, on ne peut pas affirmer
    qu'un point a ete joue.
    """
    if cotes_bougent:
        return True
    jeux, pts = avancement(score, points)
    return jeux > 0 or pts > 0


def duree_courte(secondes) -> str:
    """Un age en texte court, a mettre a cote de la pastille.

    La pastille dit le VERDICT (frais, perime, inconnu), pas la mesure. Deux
    flux verts peuvent avoir 2 s et 400 s d'age -- leurs seuils different d'un
    facteur 5 -- et rien a l'ecran ne le disait. L'operateur qui se demande
    « depuis quand ? » ne doit pas avoir a ouvrir la base.

    Un age inconnu rend « ? » et JAMAIS « 0 s » : c'est la meme regle que
    partout ici, confondre « je ne sais pas » avec « a l'instant » ferait
    passer un flux muet pour le plus vivant des quatre.
    """
    if secondes is None or pd.isna(secondes):
        return "?"
    try:
        s = float(secondes)
    except (TypeError, ValueError):
        return "?"
    if s < 0:
        s = 0.0
    if s < 60:
        return f"{s:.0f}s"
    if s < 3600:
        return f"{int(s // 60)}m{int(s % 60):02d}"
    return f"{int(s // 3600)}h{int((s % 3600) // 60):02d}"


def points_uniques(df: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par ETAT de jeu, dans l'ordre du temps.

    ``live_series`` ecrit une ligne des qu'un PRIX bouge, score inchange :
    c'est son role, et le graphique de cotes vit de ces lignes-la. Mais le
    tableau point par point, lui, n'affiche PAS les cotes -- ces lignes y
    apparaissent donc comme des doublons parfaits, plusieurs fois le meme
    score et les memes points. Mesure du 2026-08-04 : 2 808 lignes sur
    11 117 (25 %), et jusqu'a 49 % sur un match.

    On garde la PREMIERE ligne de chaque suite, c'est-a-dire l'instant ou
    l'etat est APPARU -- pas celui du dernier rafraichissement de prix, qui
    daterait un point de plusieurs minutes apres qu'il a ete joue.

    L'evenement est cherche dans TOUTE la suite et non sur la seule ligne
    gardee : le marqueur de fin de jeu est pose par le publieur sur la ligne
    ou le score a change, mais rien ne garantit que ce soit celle-la, et le
    perdre effacerait une fin de jeu du tableau.

    TOUTES les colonnes du releve sont conservees, cotes comprises : ce sont
    alors les prix a l'instant ou le point a ete joue, et pas ceux du dernier
    rafraichissement -- c'est ce que la ligne gardee garantit. Le choix de ce
    qu'on affiche appartient a la page, pas a cette fonction.
    """
    colonnes = list(df.columns) if df is not None else []
    if df is None or df.empty or not colonnes:
        return pd.DataFrame(columns=["ts", "score", "points", "evenement"])
    cles = [c for c in ("score", "points") if c in colonnes]
    vue = df[colonnes].copy()
    if not cles:
        # Sans score ni points il n'y a rien a replier : on rend la vue
        # telle quelle plutot que de tout fondre en une seule ligne.
        return vue.reset_index(drop=True)
    # `astype(str)` deliberement : NaN n'est pas egal a lui-meme, donc deux
    # absences successives formeraient chacune leur propre suite et le
    # repliement ne servirait a rien la ou il sert le plus.
    signature = vue[cles].astype(str).agg("|".join, axis=1)
    groupe = (signature != signature.shift()).cumsum()
    garde = signature != signature.shift()
    premiers = vue[garde].copy()
    if "evenement" in colonnes:
        porteurs = (
            vue.assign(_g=groupe).dropna(subset=["evenement"])
            .groupby("_g")["evenement"].first()
        )
        premiers["evenement"] = groupe[garde].map(porteurs).values
    return premiers.reset_index(drop=True)


def en_datetime(df: pd.DataFrame, colonne: str = "ts") -> pd.DataFrame:
    """Convertit une colonne de secondes epoch en datetime pandas, pour
    l'affichage (I4, tour 3).

    ``ts`` circule en secondes epoch BRUTES depuis la base (``live_series.ts``)
    jusqu'ici : correct pour trier et calculer des ecarts, mais un flottant
    comme ``1785794036.9001677`` ne dit rien a l'operateur qui regarde le
    graphique ou le tableau point par point -- l'outil PRINCIPAL de cette
    page. Ca ne ment sur rien (l'ordre et les ecarts entre points restent
    exacts), mais ca oblige a faire soi-meme la conversion mentale que
    l'ecran devrait avoir faite.

    Copie le DataFrame (n'altere jamais l'original, ``serie_longue()`` et
    ``evenements()`` restent utilisables sur les donnees brutes ailleurs) ;
    ne fait rien si le DataFrame est vide ou si la colonne est absente --
    degradation, jamais une exception.
    """
    if df is None or df.empty or colonne not in df.columns:
        return df
    df = df.copy()
    # A l'heure de PARIS : `pd.to_datetime(epoch, unit="s")` rend un
    # timestamp NAIF en UTC, et cette colonne est AFFICHEE.
    df[colonne] = to_paris(pd.to_datetime(df[colonne], unit="s"))
    return df


#: Echelle de prix de l'exchange, recopiee de ``Live/ticks.py`` cote PoC (ou
#: elle est verifiee empiriquement sur nos propres carnets, 100 % conforme par
#: bande). Recopiee et non importee : les deux depots sont independants, et
#: une echelle fausse ici se verrait immediatement -- un ecart en ticks
#: aberrant saute aux yeux la ou une importation cassee ne dirait rien.
ECHELLE_TICKS = (
    (1.01, 2.00, 0.01), (2.00, 3.00, 0.02), (3.00, 4.00, 0.05),
    (4.00, 6.00, 0.10), (6.00, 10.0, 0.20), (10.0, 20.0, 0.50),
    (20.0, 30.0, 1.00), (30.0, 50.0, 2.00), (50.0, 100.0, 5.00),
    (100.0, 1000.0, 10.0),
)


def _rang_tick(cote) -> int | None:
    """Le rang d'une cote sur l'echelle, en comptant depuis 1,01.

    Tout se calcule en MILLIEMES ENTIERS : 1,01 + 0,01 ne vaut pas 1,02 en
    binaire, et compter des crans en flottants derive au bout de quelques
    centaines de barreaux.
    """
    if cote is None or pd.isna(cote):
        return None
    try:
        m = int(round(float(cote) * 1000))
    except (TypeError, ValueError):
        return None
    if m < 1010 or m > 1000000:
        return None
    rang = 0
    for bas, haut, pas in ECHELLE_TICKS:
        b, h, p = int(bas * 1000), int(haut * 1000), int(pas * 1000)
        if m <= h:
            return rang + (m - b + p // 2) // p
        rang += (h - b) // p
    return rang


def ecart_en_ticks(back, lay) -> int | None:
    """L'ecart back/lay compte en CRANS de l'echelle, pas en valeur absolue.

    Un ecart absolu de 0,05 vaut cinq crans a 1,50 et un seul a 3,50 : en
    valeur absolue on melangerait des situations sans rapport. Le tick est la
    seule unite dans laquelle « un cran de carnet » signifie la meme chose
    partout -- et la mesure du PoC le confirme, l'ecart en ticks est
    independant de la cote (pearson 0,000) la ou l'ecart absolu la suit
    (pearson +0,292).

    C'est le cout d'execution paye a chaque aller-retour, et un carnet large
    signale un marche peu suivi ou une photo perimee.

    ``None`` si l'un des deux prix manque, ou si le carnet est CROISE (lay
    sous back) -- cas qui ne decrit pas un ecart mais une incoherence, et
    qu'il ne faut pas afficher comme un zero.
    """
    ra, rb = _rang_tick(back), _rang_tick(lay)
    if ra is None or rb is None:
        return None
    return None if rb < ra else rb - ra


def probabilite_implicite(back_a, lay_a, back_b, lay_b):
    """La probabilite que « a » gagne, marge du marche retiree.

    On prend le MILIEU de chaque fourchette back/lay -- le prix qu'on paierait
    en moyenne a l'aller et au retour -- puis on normalise les deux cotes
    l'une par l'autre (demarginalisation proportionnelle, celle que le PoC
    applique deja au carnet).

    Une cote se lit mal pour juger : 1,38 contre 2,92 ne dit pas
    spontanement « 68 % ». C'est la seule raison d'etre de cette fonction --
    elle n'ajoute aucune information, elle rend lisible celle qui est la.

    ``None`` des qu'un cote manque : une probabilite calculee sur un seul
    joueur serait la marge du bookmaker deguisee en pronostic.
    """
    def milieu(x, y):
        vals = [v for v in (x, y) if v is not None and not pd.isna(v) and float(v) > 1]
        return sum(float(v) for v in vals) / len(vals) if vals else None

    ma, mb = milieu(back_a, lay_a), milieu(back_b, lay_b)
    if ma is None or mb is None:
        return None
    ia, ib = 1.0 / ma, 1.0 / mb
    total = ia + ib
    return None if total <= 0 else ia / total


def chronologie(texte) -> list:
    """Le recit jeu par jeu publie par le PoC, ou une liste vide.

    Ne leve JAMAIS : un texte illisible rend une liste vide plutot que de
    faire tomber la page -- la chronologie est un ornement utile, pas la
    donnee dont depend l'affichage du score.
    """
    if texte is None or (not isinstance(texte, str)) or not texte.strip():
        return []
    try:
        jeux = json.loads(texte)
    except Exception:
        return []
    return [j for j in jeux if isinstance(j, dict)] if isinstance(jeux, list) else []


def ordonner_par_tournoi(df):
    """Trier par heure de debut SANS eparpiller les tournois.

    Trier sur la seule heure entrelace les tournois : les deux matchs de
    Hagen se retrouvaient separes par ceux de Varsovie, et l'entete « Hagen
    Challenger » etait ecrit deux fois dans la meme liste -- on croyait a
    deux tournois. On ordonne donc les TOURNOIS par l'heure de leur premier
    match, et les matchs par heure a l'interieur de chacun : l'ordre reste
    chronologique la ou il se lit, et un tournoi ne s'annonce qu'une fois.
    """
    if not {"start_timestamp", "league"} <= set(df.columns) or df.empty:
        return df
    # TROIS niveaux : competition, tournoi, match. Trier sans regrouper la
    # competition l'annoncerait plusieurs fois -- exactement le defaut deja
    # repare pour les tournois, un cran plus haut.
    circuit = [competition(t, lg) for t, lg in zip(df.get("tour_type", ""), df["league"])]
    d = df.assign(_circuit=circuit)
    d = d.assign(
        _c_premier=d.groupby("_circuit")["start_timestamp"].transform("min"),
        _t_premier=d.groupby("league")["start_timestamp"].transform("min"),
    )
    return (
        d.sort_values(["_c_premier", "_circuit", "_t_premier", "league",
                       "start_timestamp"], na_position="last", kind="stable")
        .drop(columns=["_circuit", "_c_premier", "_t_premier"])
    )


def source_score_figee(maintenant: float | None = None,
                       seuil: float = SEUIL_BATTEMENT_ARRETE_S,
                       lire_battement=None) -> bool:
    """Vrai si la SOURCE de score sert son cache : elle repond, sans bouger.

    Troisieme panne distincte, et la plus trompeuse des trois. Le publieur
    bat, le capteur de score bat aussi -- tout parait sain -- mais la source
    renvoie le meme etat depuis des minutes. Le capteur n'ecrivant que sur
    changement, plus aucun match n'est frais, et le publieur declarait alors
    TOUS les matchs termines : la page affichait « aucun match en cours » en
    pleine soiree. Mesure du 2026-08-04 a 19:42 : 14,8 minutes, 20 matchs en
    cours, pas une ecriture.

    Le publieur sait desormais s'en apercevoir et refuse de prononcer ces
    fins-la ; il l'annonce dans son battement. Sans ce signal-ci, la page
    afficherait un score fige sans dire qu'il l'est -- ce qui est
    exactement le mensonge que sa colonne de fraicheur existe pour empecher.
    """
    lire = lire_battement or lire_battement_publieur
    try:
        battement = lire()
    except Exception:
        return False
    if not battement:
        return False
    try:
        age = (time.time() if maintenant is None else float(maintenant)) - float(
            battement.get("ts"))
    except (TypeError, ValueError):
        return False
    if age > seuil:
        # Un battement perime ne prouve plus rien du present : c'est
        # `publieur_arrete` qui parle alors, pas ce signal-ci.
        return False
    return str((battement.get("state") or {}).get("capteur_score")) == "fige"

