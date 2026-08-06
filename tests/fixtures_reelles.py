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
