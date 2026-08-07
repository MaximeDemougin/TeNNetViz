"""Fixtures PRELEVEES sur l'etat reel du systeme le 2026-08-03, pas ecrites
a la main.

La revue de branche a releve que des fixtures inventees (ex. les quatre
colonnes d'age posees a une meme petite valeur non-NaN) peuvent masquer
l'etat REELLEMENT dominant en base et laisser passer un defaut critique sans
qu'aucun test ne tombe (cf. rapport fix-B, points C2/I3/I5). Ce module fige
des lignes et un battement authentiques, avec leur provenance, pour que les
tests qui en ont besoin les reutilisent sans dependre d'un acces reseau/DB a
l'execution (memes proprietes de determinisme que le reste de la suite).
"""

from datetime import date

# Instant de la capture (epoch UTC, time.time() au moment de la requete).
CAPTURE_TS = 1785790563.2821338

# Ligne REELLE de TeNNet_test.live_now (event_id 3796196, Carol Zhao vs
# Magda Linette, National Bank Open - Toronto), capturee au CAPTURE_TS
# ci-dessus. Choisie parce qu'elle porte l'etat DOMINANT en base ce jour-la :
# age_books_s et age_stats_s NULL en SQL -> NaN pandas (PAS None Python) --
# mesure sur cette meme capture, 50 a 55 lignes sur 58-59 ont ce NaN sur au
# moins un des trois flux annexes au score. Une fixture qui pose les quatre
# ages a une meme petite valeur (comme le faisait la premiere version de ce
# correctif) ne produit JAMAIS cet etat.
LIGNE_REELLE_INPLAY = {
    "event_id": "3796196", "id_market": "1.260626999",
    "participant1": "Carol Zhao", "participant2": "Magda Linette",
    "league": "National Bank Open - Toronto", "tour_type": "wta",
    "score": "3-3", "points": "15-30", "server": None, "status": "InPlay",
    "back_odds_a": 7.2, "lay_odds_a": 7.6,
    "back_odds_b": 1.15, "lay_odds_b": 1.16,
    "book_odds_a": float("nan"), "book_odds_b": float("nan"),
    "age_score_s": 310.72726249694824,
    "age_exchange_s": 29.852842092514038,
    "age_books_s": float("nan"),
    "age_stats_s": float("nan"),
    "updated_ts": 1785790556.0558422,
}

# Ligne REELLE, re-capturee le 2026-08-04 (tour 3 -- la premiere capture,
# event_id 3802255, epinglait `"server": "0,1"`, une valeur que le publieur
# ne peut PLUS emettre depuis la decision C6 : server=NULL a 100 %, mesure
# ci-dessous sur les 61 lignes de cette nouvelle capture). La plus vieille
# ligne "Finished" encore presente : event_id 3797321. `live_now` n'est
# aujourd'hui jamais purgee avant 6 h (defaut C5, traite en parallele cote
# publieur, hors perimetre ici) : une ligne terminee cesse d'etre touchee
# mais reste en base, `updated_ts` age de ~5 631 s au moment de la capture
# (1h34) sans que ce soit une panne du publieur -- exactement le cas que
# publieur_arrete() doit savoir ignorer.
CAPTURE_TS_FINISHED = 1785795163.6429493
LIGNE_REELLE_FINISHED = {
    "event_id": "3797321", "id_market": None,
    "participant1": "Alex Barrena", "participant2": "Timofey Skatov",
    "league": "Hagen Challenger", "tour_type": "atp",
    "score": "7-6,6-2", "points": "0-0", "server": None, "status": "Finished",
    "back_odds_a": float("nan"), "lay_odds_a": float("nan"),
    "back_odds_b": float("nan"), "lay_odds_b": float("nan"),
    "book_odds_a": float("nan"), "book_odds_b": float("nan"),
    "age_score_s": 15494.946043729782,
    "age_exchange_s": float("nan"),
    "age_books_s": float("nan"),
    "age_stats_s": float("nan"),
    "updated_ts": 1785789532.6328914,
}

# Ligne REELLE, capturee le 2026-08-03 a CAPTURE_TS_MI_CYCLE (event_id
# 3798175, Victoria Jimenez Kasintseva vs Alycia Parks) : un match SAIN, dont
# les quatre flux sont a mi-cycle -- AUCUN n'est frais au sens de l'ancien
# seuil unique (30 s), et pourtant aucun n'est mort. C'est la preuve directe
# du defaut vise par ce tour : age_score_s=87,8s (~mediane 27s + quelques
# points), age_exchange_s=121,6s (bien dans la dent de scie 0-180s
# documentee), age_books_s=126,5s (consensus a deux books rapides),
# age_stats_s=32,8s. Avec l'ancien seuil unique de 30s, les QUATRE pastilles
# rougissaient. Avec les seuils par flux, aucune ne doit rougir.
CAPTURE_TS_MI_CYCLE = 1785792275.387427
LIGNE_REELLE_MI_CYCLE = {
    "event_id": "3798175", "id_market": "1.260673209",
    "participant1": "Victoria Jimenez Kasintseva", "participant2": "Alycia Parks",
    "league": "National Bank Open - Toronto", "tour_type": "wta",
    "score": "1-4", "points": "0-0", "server": None, "status": "InPlay",
    "back_odds_a": 5.1, "lay_odds_a": 5.2,
    "back_odds_b": 1.24, "lay_odds_b": 1.25,
    "book_odds_a": 4.47, "book_odds_b": 1.21,
    "age_score_s": 87.8239426612854,
    "age_exchange_s": 121.61405372619629,
    "age_books_s": 126.4850537776947,
    "age_stats_s": 32.84827470779419,
    "updated_ts": 1785792268.4850538,
}

# Deux lignes REELLES, capturees le 2026-08-04 (tour 4), APRES l'ALTER qui a
# ajoute `age_books_flux_s` a `live_now` cote publieur : ce sont les
# premieres fixtures de ce depot a porter cette colonne, les trois
# precedentes (ci-dessus) datent d'avant son existence et ne l'ont donc
# jamais eue -- ce n'est pas un oubli, `f_books_flux` degrade proprement a
# "inconnu" sur une colonne absente, deja teste ailleurs.
#
# `age_books_s` (le PRIX, plafonne a 180 s a la source) et
# `age_books_flux_s` (le FLUX, la reception du dernier api_odds, jamais
# plafonne) repondent a deux questions differentes -- deux lignes REELLES
# qui les separent clairement :
CAPTURE_TS_BOOKS = 1785796877.982668

# event_id 3801815 (Luca Van Assche vs Titouan Droguet, National Bank Open
# - Montreal) : prix ET flux frais tous les deux -- le cas sain "de base".
LIGNE_REELLE_BOOKS_SAINE = {
    "event_id": "3801815", "id_market": "1.260671004",
    "participant1": "Luca Van Assche", "participant2": "Titouan Droguet",
    "league": "National Bank Open - Montreal", "tour_type": "atp",
    "score": "4-6,3-2", "points": "30-15", "server": None, "status": "InPlay",
    "back_odds_a": 2.2, "lay_odds_a": 2.46,
    "back_odds_b": 1.69, "lay_odds_b": 1.82,
    "book_odds_a": 2.19, "book_odds_b": 1.66,
    "age_score_s": 21.2932186126709,
    "age_exchange_s": 40.07716107368469,
    "age_books_s": 73.77916097640991,
    "age_stats_s": 7.522812366485596,
    "age_books_flux_s": 31.025394916534424,
    "updated_ts": 1785796868.779161,
}

# event_id 3798175 (Victoria Jimenez Kasintseva vs Alycia Parks -- LE MEME
# match que LIGNE_REELLE_MI_CYCLE ci-dessus, ~10h plus tard : plus aucun
# prix book depuis longtemps) : `age_books_s` NULL (le dernier prix a
# depasse le plafond de 180s, il y a longtemps qu'aucun n'est utilisable) ET
# `age_books_flux_s`=611,8s (>600, le capteur de cotes bookmakers pour ce
# match semble mort) -- exactement le cas que la colonne flux existe pour
# rendre visible : `age_books_s` seul, plafonne, ne peut QUE dire "inconnu"
# ici, jamais "le capteur est mort depuis 10 minutes".
LIGNE_REELLE_BOOKS_FLUX_MORT = {
    "event_id": "3798175", "id_market": "1.260673209",
    "participant1": "Victoria Jimenez Kasintseva", "participant2": "Alycia Parks",
    "league": "National Bank Open - Toronto", "tour_type": "wta",
    "score": "4-6,4-6", "points": "0-0", "server": None, "status": "InPlay",
    "back_odds_a": float("nan"), "lay_odds_a": float("nan"),
    "back_odds_b": float("nan"), "lay_odds_b": float("nan"),
    "book_odds_a": float("nan"), "book_odds_b": float("nan"),
    "age_score_s": 599.5255534648895,
    "age_exchange_s": 392.4233076572418,
    "age_books_s": float("nan"),
    "age_stats_s": 698.5621898174286,
    "age_books_flux_s": 611.77729845047,
    "updated_ts": 1785796860.9963076,
}

# Contenu REEL de /home/ubuntu/tennet_live_data/heartbeat-publish.json,
# ecrit par Live.supervise.Heartbeat cote PoC (publieur en service sur cette
# machine), lu le 2026-08-03 a 20:48:55Z.
BATTEMENT_REEL_PUBLIEUR = {
    "sensor": "publish", "pid": 984985, "ts": 1785790135.977158,
    "utc": "2026-08-03T20:48:55Z", "started_utc": "2026-08-03T20:39:02Z",
    "uptime_s": 593.2, "beats": 18,
    "state": {
        "n_matchs": 4, "n_exchange": 3, "n_books": 3, "n_series": 1,
        "n_echecs": 0, "capteur_score": "vivant", "total_publies": 415,
    },
}

# Contenu REEL de /home/ubuntu/tennet_live_data/heartbeat-score.json (I1b,
# tour 3) : le capteur de SCORE est un process DISTINCT du publieur, avec
# son propre fichier de battement (meme mecanisme, Live.supervise.Heartbeat).
# Lu le 2026-08-03 a 22:06:07Z.
BATTEMENT_REEL_SCORE = {
    "sensor": "score", "pid": 1543510, "ts": 1785794767.8184435,
    "utc": "2026-08-03T22:06:07Z", "started_utc": "2026-08-01T11:37:01Z",
    "uptime_s": 210546.2, "beats": 6809,
    "state": {
        "n_events": 8, "n_events_total": 8, "n_written": 0,
        "total_written": 26747, "n_tracked": 165, "api_calls": 60980,
        "api_failures": 0, "consecutive_api_failures": 0,
        "since_change_s": 10.2,
    },
}


# ══════════════════════════════════════════════════════════════════════
# Les tables du PASSE : bilan de collecte, matchs joues, point par point
# ══════════════════════════════════════════════════════════════════════
#
# Prelevees le 2026-08-07 sur TeNNet_test (lecture seule), pour la page
# « Match » -- parcours du passe et bilan de collecte. Aucune donnee de
# pari, aucun identifiant de compte : ces trois tables sont ecrites par le
# PoC de collecte et ne portent ni mise, ni resultat de production, ni
# compte. `ID_MATCH` est la cle de match du schema de production, conservee
# telle quelle parce qu'elle EST dans la table -- la page n'en fait aucune
# jointure (hors perimetre, §7 du design).

# LES DIX LIGNES de TeNNet_test.live_qa_daily, integrales et dans l'ordre
# du jour. Copiees telles que pandas les relit : les DECIMAL NULL de MySQL
# reviennent en NaN flottant (PAS None), et `day` en datetime.date.
#
# Ce que cet echantillon DISCRIMINE, ligne par ligne -- c'est la raison de
# le prendre en entier plutot que d'en choisir trois :
#
# - 2026-07-28 a 07-31 : `n_markets = 0`, donc `match_rate` NULL. Ce sont
#   les jours « pas de mesure » : les afficher a 0 % en ferait quatre jours
#   catastrophiques la ou il n'y a simplement rien a mesurer.
# - 2026-07-31 est LE cas qui separe « jour sans mesure » de « indicateur
#   sans mesure » : `match_rate` et `gap_ratio` y sont NULL, mais
#   `pbp_coherence` vaut 0,5518 sur 868 jeux communs -- une VRAIE mesure,
#   hors seuil. Un code qui declarerait « pas de mesure » au niveau du JOUR
#   masquerait cette mesure-la. Aucune autre ligne ne le revele.
# - 2026-08-01 : `match_rate` = 0,8889, a un cheveu SOUS le seuil de 0,90.
#   C'est la ligne qui epingle la valeur exacte du seuil : le descendre a
#   0,85 rendrait ce jour conforme, et lui seul.
# - 2026-08-06 : les trois indicateurs valent 0,6531 / 0,3931 / 0,5159 --
#   trois valeurs DIFFERENTES, donc une permutation entre indicateurs se
#   voit. Et les deux SENS s'y separent : 0,6531 est hors seuil comme
#   MINIMUM (< 0,90) et conforme si on le lisait comme maximum ; 0,5159 est
#   hors seuil comme MAXIMUM (> 0,05) et conforme si on le lisait comme
#   minimum. Inverser un sens inverse le verdict, sur cette ligne.
# - `n_inversions` : NULL partout SAUF le 2026-07-28 (0). La colonne est
#   donc vide a 90 % -- l'afficher comme si elle valait zero annoncerait
#   « aucune inversion detectee » la ou rien n'a ete compte.
# - `gap_ratio` : 0,9742 -> 0,9513 -> 0,9721 -> 0,6253 -> 0,5029 -> 0,5159.
#   La chute du 3 au 5 aout (la correction d'authentification) est dans les
#   donnees : une tendance calculee a l'envers la lirait comme une
#   degradation.
LIGNES_REELLES_QA = [
    {"id": 1, "day": date(2026, 7, 28), "n_markets": 0, "n_matched": 0,
     "match_rate": float("nan"), "n_pbp_common": 0, "n_pbp_ok": 0,
     "pbp_coherence": float("nan"), "gap_seconds": float("nan"),
     "inplay_seconds": float("nan"), "gap_ratio": float("nan"),
     "n_inversions": 0.0, "api_calls": 3975},
    {"id": 2, "day": date(2026, 7, 29), "n_markets": 0, "n_matched": 0,
     "match_rate": float("nan"), "n_pbp_common": 0, "n_pbp_ok": 0,
     "pbp_coherence": float("nan"), "gap_seconds": float("nan"),
     "inplay_seconds": float("nan"), "gap_ratio": float("nan"),
     "n_inversions": float("nan"), "api_calls": 27935},
    {"id": 3, "day": date(2026, 7, 30), "n_markets": 0, "n_matched": 0,
     "match_rate": float("nan"), "n_pbp_common": 0, "n_pbp_ok": 0,
     "pbp_coherence": float("nan"), "gap_seconds": float("nan"),
     "inplay_seconds": float("nan"), "gap_ratio": float("nan"),
     "n_inversions": float("nan"), "api_calls": 33003},
    {"id": 4, "day": date(2026, 7, 31), "n_markets": 0, "n_matched": 0,
     "match_rate": float("nan"), "n_pbp_common": 868, "n_pbp_ok": 479,
     "pbp_coherence": 0.5518, "gap_seconds": float("nan"),
     "inplay_seconds": float("nan"), "gap_ratio": float("nan"),
     "n_inversions": float("nan"), "api_calls": 28645},
    {"id": 5, "day": date(2026, 8, 1), "n_markets": 54, "n_matched": 48,
     "match_rate": 0.8889, "n_pbp_common": 1653, "n_pbp_ok": 568,
     "pbp_coherence": 0.3436, "gap_seconds": 341836.36477303505,
     "inplay_seconds": 350890.36265707016, "gap_ratio": 0.9742,
     "n_inversions": float("nan"), "api_calls": 33866},
    {"id": 6, "day": date(2026, 8, 2), "n_markets": 83, "n_matched": 49,
     "match_rate": 0.5904, "n_pbp_common": 1204, "n_pbp_ok": 444,
     "pbp_coherence": 0.3688, "gap_seconds": 543359.7065548897,
     "inplay_seconds": 571201.1665539742, "gap_ratio": 0.9513,
     "n_inversions": float("nan"), "api_calls": 35296},
    {"id": 7, "day": date(2026, 8, 3), "n_markets": 88, "n_matched": 60,
     "match_rate": 0.6818, "n_pbp_common": 1233, "n_pbp_ok": 617,
     "pbp_coherence": 0.5004, "gap_seconds": 667384.553593874,
     "inplay_seconds": 686569.8906400204, "gap_ratio": 0.9721,
     "n_inversions": float("nan"), "api_calls": 38249},
    {"id": 8, "day": date(2026, 8, 4), "n_markets": 121, "n_matched": 83,
     "match_rate": 0.686, "n_pbp_common": 1743, "n_pbp_ok": 1083,
     "pbp_coherence": 0.6213, "gap_seconds": 459615.27536058426,
     "inplay_seconds": 734982.036698103, "gap_ratio": 0.6253,
     "n_inversions": float("nan"), "api_calls": 36349},
    {"id": 9, "day": date(2026, 8, 5), "n_markets": 55, "n_matched": 40,
     "match_rate": 0.7273, "n_pbp_common": 1056, "n_pbp_ok": 526,
     "pbp_coherence": 0.4981, "gap_seconds": 157274.57521533966,
     "inplay_seconds": 312761.20657014847, "gap_ratio": 0.5029,
     "n_inversions": float("nan"), "api_calls": 34373},
    {"id": 10, "day": date(2026, 8, 6), "n_markets": 49, "n_matched": 32,
     "match_rate": 0.6531, "n_pbp_common": 613, "n_pbp_ok": 241,
     "pbp_coherence": 0.3931, "gap_seconds": 154333.76186680794,
     "inplay_seconds": 299136.4854776859, "gap_ratio": 0.5159,
     "n_inversions": float("nan"), "api_calls": 33325},
]

# Six lignes REELLES de TeNNet_test.live_matches, choisies pour ce qu'elles
# separent -- la table en compte 1 153 :
#
# - 3799286 et 3802032 portent le MEME `match_id` : la source a donne DEUX
#   `event_id` a une seule rencontre (2 cas sur 1 153 au prelevement), et
#   l'un est apparie quand l'autre ne l'est pas. C'est la preuve, en
#   donnees, qu'un lecteur du point par point qui n'accepterait qu'un seul
#   identifiant rendrait la moitie du match : 2 points sous 3799286,
#   105 sous 3802032.
# - 3801784 apparait DEUX FOIS, aux jours 08-04 et 08-05 : un match a
#   cheval sur deux journees. 1 153 lignes ne sont donc pas 1 153 matchs.
# - 3807294 est le cas NON APPARIE : `id_market`, `ID_MATCH` et
#   `p1_is_home` tous NULL a la fois. C'est l'etat de 737 lignes sur 1 153.
# - Les circuits (`atp`/`wta`) et les ligues (quatre distinctes ici) ne sont
#   pas codes en dur dans la page : ils se tirent de ces valeurs.
# - "Christopher O'Connell" porte une APOSTROPHE, dans la donnee elle-meme.
LIGNES_REELLES_MATCHS = [
    {"id": 1048, "day": date(2026, 8, 2), "event_id": "3799286",
     "match_id": "11517-24721-21346-4", "id_market": None, "ID_MATCH": None,
     "participant1": "James Duckworth", "participant2": "Christopher O'Connell",
     "p1_is_home": None, "league": "National Bank Open - Montreal",
     "tour_type": "atp", "start_ts": 1785688200, "matched": 0,
     "ambiguous_market": 0},
    {"id": 1097, "day": date(2026, 8, 3), "event_id": "3802032",
     "match_id": "11517-24721-21346-4", "id_market": "1.260674706",
     "ID_MATCH": "dC66M7wf", "participant1": "James Duckworth",
     "participant2": "Christopher O'Connell", "p1_is_home": 1.0,
     "league": "National Bank Open - Montreal", "tour_type": "atp",
     "start_ts": 1785774600, "matched": 1, "ambiguous_market": 0},
    {"id": 1209, "day": date(2026, 8, 4), "event_id": "3801784",
     "match_id": "18455-52254-16739-5", "id_market": "1.260713970",
     "ID_MATCH": "EZqCkwaJ", "participant1": "Aryna Sabalenka",
     "participant2": "Moyuka Uchijima", "p1_is_home": 1.0,
     "league": "National Bank Open - Toronto", "tour_type": "wta",
     "start_ts": 1785855600, "matched": 1, "ambiguous_market": 0},
    {"id": 1210, "day": date(2026, 8, 5), "event_id": "3801784",
     "match_id": "18455-52254-16739-5", "id_market": "1.260713970",
     "ID_MATCH": "EZqCkwaJ", "participant1": "Aryna Sabalenka",
     "participant2": "Moyuka Uchijima", "p1_is_home": 1.0,
     "league": "National Bank Open - Toronto", "tour_type": "wta",
     "start_ts": 1785855600, "matched": 1, "ambiguous_market": 0},
    {"id": 1272, "day": date(2026, 8, 6), "event_id": "3807291",
     "match_id": "13447-50118-21923-5", "id_market": "1.260774584",
     "ID_MATCH": "dfqFQIfD", "participant1": "Damir Dzumhur",
     "participant2": "Mathys Erhard", "p1_is_home": 1.0,
     "league": "Grodzisk Mazowiecki Challenger", "tour_type": "atp",
     "start_ts": 1786003200, "matched": 1, "ambiguous_market": 0},
    {"id": 1277, "day": date(2026, 8, 6), "event_id": "3807294",
     "match_id": "110995-93848-21926-5", "id_market": None, "ID_MATCH": None,
     "participant1": "Yannick Theodor Alexandrescou",
     "participant2": "Petr Brunclik", "p1_is_home": None,
     "league": "Plovdiv 2 Challenger", "tour_type": "atp",
     "start_ts": 1786006800, "matched": 0, "ambiguous_market": 0},
]

# UNE SEPTIEME ligne REELLE de live_matches (id 91), tenue A PART des six
# ci-dessus : elle porte une CINQUIEME ligue (`W15 Savitaipale`, 27 lignes
# dans la table) et une journee (2026-07-29) qu'aucune des six n'a. C'est
# exactement ce qu'il faut pour prouver qu'une valeur de filtre vient des
# DONNEES et non d'une liste ecrite dans le code : on l'ajoute au jeu, la
# ligue et le jour doivent apparaitre dans les choix. Une liste en dur ne
# bougerait pas.
LIGNE_REELLE_MATCH_AUTRE_LIGUE = {
    "id": 91, "day": date(2026, 7, 29), "event_id": "3783658",
    "match_id": "14316-80678-17188-4", "id_market": None, "ID_MATCH": None,
    "participant1": "Valentini Grammatikopoulou",
    "participant2": "Cara Korhonen", "p1_is_home": None,
    "league": "W15 Savitaipale", "tour_type": "wta",
    "start_ts": 1785308400, "matched": 0, "ambiguous_market": 0,
}

# Lignes REELLES de TeNNet_test.live_points, pour les DEUX `event_id` du
# meme match (11517-24721-21346-4, cf. ci-dessus) : c'est ce couple qui
# discrimine un lecteur mono-identifiant. Les `recv_ts` sont conserves a la
# precision de la base -- ils sont tous DIFFERENTS, donc un tri casse se
# voit ; 3799286 est ANTERIEUR a 3802032, donc l'entrelacement chronologique
# des deux identifiants est verifiable.
#
# `indicator` vaut « 0,0 » sur la premiere ligne de chaque identifiant puis
# « 1,0 » : la valeur bouge, une colonne figee au premier releve se verrait.
LIGNES_REELLES_POINTS = [
    {"id": 159649, "day": date(2026, 8, 2), "event_id": "3799286",
     "recv_ts": 1785689065.8099902, "score": "0-0", "points": "0-0",
     "indicator": "0,0", "status": "InPlay"},
    {"id": 159747, "day": date(2026, 8, 2), "event_id": "3799286",
     "recv_ts": 1785689428.3790305, "score": "0-0", "points": "0-0",
     "indicator": "1,0", "status": "InPlay"},
    {"id": 167076, "day": date(2026, 8, 3), "event_id": "3802032",
     "recv_ts": 1785773066.148995, "score": "0-0", "points": "0-0",
     "indicator": "1,0", "status": "InPlay"},
    {"id": 169606, "day": date(2026, 8, 3), "event_id": "3802032",
     "recv_ts": 1785786368.638749, "score": "0-0", "points": "15-0",
     "indicator": "1,0", "status": "InPlay"},
    {"id": 169611, "day": date(2026, 8, 3), "event_id": "3802032",
     "recv_ts": 1785786385.7547333, "score": "0-0", "points": "30-0",
     "indicator": "1,0", "status": "InPlay"},
]

# Le DERNIER point recu pour 3802032 (id 170791) : le match est fini --
# 6-3, 6-1 -- et son `status` dit pourtant encore « InPlay ». La collecte
# s'est arretee la, elle n'a jamais recu de trame « Finished ». C'est cette
# ligne qui interdit de reprendre le statut du dernier releve pour afficher
# un match archive : elle ferait passer une rencontre du 3 aout pour un
# match en cours.
LIGNE_REELLE_POINT_FINAL = {
    "id": 170791, "day": date(2026, 8, 3), "event_id": "3802032",
    "recv_ts": 1785795905.3878095, "score": "6-3,6-1", "points": "0-0",
    "indicator": "0,1", "status": "InPlay",
}

# ── Un match RECENT, celui qui a encore ses cotes ─────────────────────
#
# event_id 3807291 (Damir Dzumhur vs Mathys Erhard, Grodzisk Mazowiecki
# Challenger) est deja dans LIGNES_REELLES_MATCHS ci-dessus, apparie et
# collecte le 2026-08-06. Il porte 368 lignes de `live_series` et 62 de
# `live_points` -- c'est le cas OPPOSE a 3802032, qui n'a plus que ses
# points : la retention de `live_series` (~2,6 jours au 2026-08-07, du
# 04-08 13:50 au 07-08 09:04) couvre l'un et plus l'autre.
#
# Quatre lignes prelevees sur les 368, choisies pour ce qu'elles separent :
#
# - la premiere (id 55818) n'a AUCUNE cote bookmaker (NULL) alors que
#   l'exchange en a deja : les six series ne commencent pas ensemble, et
#   une figure qui exigerait les six ne tracerait rien ;
# - les deux suivantes portent `evenement = 'fin_de_jeu'` -- les traits
#   verticaux du graphique -- et des cotes qui BOUGENT dans le bon sens
#   (1,24 -> 1,42 -> 1,58 quand le joueur a perd des jeux) : une
#   permutation entre back a et back b se verrait ;
# - la derniere (id 57531) a TOUTES ses cotes a NULL, l'etat de fin de
#   collecte : elle ne doit produire aucun point sur la courbe, jamais un
#   prix a zero -- qui se lirait comme une certitude.
LIGNES_REELLES_SERIE_RECENTE = [
    {"id": 55818, "event_id": "3807291", "ts": 1786021326.333186,
     "back_odds_a": 1.24, "lay_odds_a": 1.25, "back_odds_b": 5.0,
     "lay_odds_b": 5.2, "book_odds_a": float("nan"),
     "book_odds_b": float("nan"), "score": "0-0", "points": "0-0",
     "server": None, "evenement": None},
    {"id": 56003, "event_id": "3807291", "ts": 1786021946.697545,
     "back_odds_a": 1.42, "lay_odds_a": 1.43, "back_odds_b": 3.3,
     "lay_odds_b": 3.4, "book_odds_a": 1.375, "book_odds_b": 2.975,
     "score": "0-1", "points": "0-0", "server": "1",
     "evenement": "fin_de_jeu"},
    {"id": 56095, "event_id": "3807291", "ts": 1786022192.2400916,
     "back_odds_a": 1.58, "lay_odds_a": 1.59, "back_odds_b": 2.68,
     "lay_odds_b": 2.72, "book_odds_a": 1.51, "book_odds_b": 2.5175,
     "score": "0-2", "points": "0-0", "server": "0",
     "evenement": "fin_de_jeu"},
    {"id": 57531, "event_id": "3807291", "ts": 1786027217.4271064,
     "back_odds_a": None, "lay_odds_a": None, "back_odds_b": None,
     "lay_odds_b": None, "book_odds_a": None, "book_odds_b": None,
     "score": "3-6,6-6", "points": "1-2", "server": "1", "evenement": None},
]

# Trois lignes REELLES de `live_points` pour ce meme 3807291 : le premier
# releve et les deux derniers. Le dernier score (3-6, 6-6) est celui que le
# bandeau doit afficher pour un match archive -- il vient de `live_points`,
# pas de `live_matches`, qui ne porte NI score NI statut.
LIGNES_REELLES_POINTS_RECENTS = [
    {"id": 194730, "day": date(2026, 8, 6), "event_id": "3807291",
     "recv_ts": 1786021320.038717, "score": "0-0", "points": "0-0",
     "indicator": "0,0", "status": "InPlay"},
    {"id": 195056, "day": date(2026, 8, 6), "event_id": "3807291",
     "recv_ts": 1786026829.9940543, "score": "3-6,6-6", "points": "0-2",
     "indicator": "1,0", "status": "InPlay"},
    {"id": 195061, "day": date(2026, 8, 6), "event_id": "3807291",
     "recv_ts": 1786026840.3442178, "score": "3-6,6-6", "points": "1-2",
     "indicator": "0,1", "status": "InPlay"},
]

# Deux lignes REELLES de `live_points` pour 3807294 (Yannick Theodor
# Alexandrescou vs Petr Brunclik, Plovdiv 2 Challenger) -- la ligne NON
# APPARIEE de LIGNES_REELLES_MATCHS : `id_market`, `ID_MATCH` et
# `p1_is_home` tous NULL, l'etat de 737 lignes sur 1 153. Le match a bien
# ete joue et collecte (190 points, 7-5 6-3), il n'a simplement jamais eu
# de marche exchange. C'est le cas qui separe « pas de cotes parce que la
# retention est passee » de « pas de cotes parce qu'il n'y en a jamais eu »
# -- deux absences que confondre ferait accuser la collecte d'un trou
# qu'elle n'a pas.
LIGNES_REELLES_POINTS_NON_APPARIE = [
    {"id": 195470, "day": date(2026, 8, 6), "event_id": "3807294",
     "recv_ts": 1786031358.3813124, "score": "0-0", "points": "0-0",
     "indicator": "0,0", "status": "InPlay"},
    {"id": 196564, "day": date(2026, 8, 6), "event_id": "3807294",
     "recv_ts": 1786038538.4482582, "score": "7-5,6-3", "points": "0-0",
     "indicator": "1,0", "status": "InPlay"},
]
