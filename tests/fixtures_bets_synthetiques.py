"""Paris SYNTHETIQUES, fideles en FORME au retour reel de `data.load_bets`,
mais entierement FICTIFS en VALEUR (identifiants, joueurs, montants).

Ce depot est PUBLIC : contrairement a l'ancienne fixture de l'arbre de
reference (`TeNNetViz/tests/fixtures_bets.py`), qui figeait sept ordres REELS
d'un compte d'argent reel (identifiants de marche Betfair, mises jusqu'a
172,35 EUR, liability, ID_USER), ce module n'en reprend NI la moindre valeur
NI la moindre ligne. Seule la FORME (le jeu de colonnes et leurs dtypes) est
reprise, et elle a ete etablie, pas devinee.

Methode d'etablissement du jeu de colonnes (LECTURE SEULE, aucune ecriture,
aucune ligne de donnee imprimee) :
  1. `SHOW COLUMNS FROM TeNNet.Bet` -- la liste des colonnes propres a la
     table `Bet` (celles que `b.*` deverse), avec leur type SQL.
  2. Un appel reel a `data.load_bets(1)` (le UNION des trois requetes
     men_matchs/women_matchs/double_matchs sur `origin/main`), dont seuls
     `.columns` et `.dtypes` ont ete releves -- jamais `.head()` ni un
     `print()` d'une ligne.
Les deux convergent sur 38 colonnes. Les cinq dont l'enonce demandait la
verification -- `is_ratio_odds_W`, `is_ratio_odds_L`, `score`, `ID_TENNET`,
`side_back_lay` -- sont bien presentes ; elles figurent ci-dessous.

Quatre matchs fictifs (identifiants "TEST0001".."TEST0004", noms de joueurs
inventes, montants ronds -- personne ne peut les confondre avec du reel),
portant les cas que `_prepare_bets_data_cached` (data.py) doit distinguer.
Le groupage se fait sur `(ID_MATCH, Match, player_bet)` -- TROIS colonnes,
pas une seule : `Match` est construit comme `winner_name + " - " +
loser_name`, et `player_bet` depend de qui a gagne le pari (colonne calculee
apres le filtre, donc sans consequence sur les paris deja ecartes).

  TEST0001  groupe ENTIEREMENT NUL -- un seul pari, `stake` = 0. C'est ce
            cas qui faisait lever `ZeroDivisionError` (moyenne ponderee sur
            un groupe dont la somme des poids vaut zero).
  TEST0002  groupe MIXTE -- deux paris sur le MEME joueur (meme
            `(ID_MATCH, Match, player_bet)`), l'un a `stake` = 0, l'autre a
            `stake` = 250,0. Le filtre ne levait pas ici, mais faussait la
            moyenne : la mise nulle pesait zero tout en occupant une ligne.
  TEST0003  groupe NORMAL -- deux paris sur le meme joueur, tous deux a
            `stake` > 0 (10,0 et 300,0), cotes 1,40 et 1,90, ET cotes/mises
            deliberement tres inegales pour que la moyenne PONDEREE et la
            moyenne SIMPLE ne coincident pas. Porte aussi le seul pari
            `side_back_lay` = "back" du jeu (l'ancienne fixture n'avait que
            du "lay") -- le pari "back" (bet=0) et le pari "lay" (bet=1)
            resolvent tous deux sur le meme gagnant (Eve Testone), donc le
            meme groupe, par construction du calcul de `bet_won`.
  TEST0004  pari a `stake` ABSENTE (NaN, pas zero) -- cas que l'ancienne
            fixture ne couvrait pas. `NaN > 0` est faux, donc ce pari doit
            etre ecarte comme les mises nulles ; mais `NaN != 0` est VRAI,
            ce qui est le piege de la mutation #3 (voir le rapport).

Total : 6 paris, 4 matchs, 3 ecartes (TEST0001, le premier pari de TEST0002,
et TEST0004) et 3 conserves (le second pari de TEST0002, les deux de
TEST0003).
"""

from math import nan

from pandas import NaT, Timestamp

# 6 paris synthetiques, jeu de colonnes identique a `data.load_bets()`.
PARIS_SYNTHETIQUES = [
    # TEST0001 -- groupe ENTIEREMENT NUL (mise = 0)
    {
        "ID_BET": 90001,
        "created_at": Timestamp("2026-01-05 10:00:00"),
        "ID_USER": 999,
        "channel": "orbitx",
        "side_back_lay": "lay",
        "bookie": "bookie_test",
        "ID_MATCH": "TEST0001",
        "ID_MARKET": "9.900000001",
        "ID_REF": "900000001",
        "ao_game_id": nan,
        "type": "Match Odds",
        "bet": 1,
        "bet_libelle": "Ana Testone",
        "odds": 1.45,
        "stake": 0.0,
        "pred": nan,
        "value": nan,
        "delta_time_min": 5.0,
        "potential_profit": 0.0,
        "liability": 0.0,
        "match_type": "atp",
        "status": 1,
        "tourney_name": "Test Open",
        "tourney_level": "A",
        "winner_name": "Ana Testone",
        "loser_name": "Bea Testone",
        "round": "R32",
        "surface": "Hard",
        "match_settled": 1,
        "score": "6-4 6-3",
        "tourney_date": Timestamp("2026-01-05 12:00:00"),
        "winner_pred": 1.80,
        "loser_pred": 2.10,
        "is_ratio_odds_W": 0,
        "is_ratio_odds_L": 0,
        "doubles": 0,
        "compet": "atp",
        "ID_TENNET": 1.0,
    },
    # TEST0002 -- groupe MIXTE, premier pari : mise nulle
    {
        "ID_BET": 90002,
        "created_at": Timestamp("2026-02-10 09:00:00"),
        "ID_USER": 999,
        "channel": "orbitx",
        "side_back_lay": "lay",
        "bookie": "bookie_test",
        "ID_MATCH": "TEST0002",
        "ID_MARKET": "9.900000002",
        "ID_REF": "900000002",
        "ao_game_id": nan,
        "type": "Match Odds",
        "bet": 1,
        "bet_libelle": "Carl Testone",
        "odds": 1.50,
        "stake": 0.0,
        "pred": nan,
        "value": nan,
        "delta_time_min": 3.0,
        "potential_profit": 0.0,
        "liability": 0.0,
        "match_type": "atp",
        "status": 1,
        "tourney_name": "Test Open",
        "tourney_level": "A",
        "winner_name": "Carl Testone",
        "loser_name": "Dan Testone",
        "round": "R16",
        "surface": "Clay",
        "match_settled": 1,
        "score": "6-4 6-3",
        "tourney_date": Timestamp("2026-02-10 12:00:00"),
        "winner_pred": 1.90,
        "loser_pred": 2.05,
        "is_ratio_odds_W": 1,
        "is_ratio_odds_L": 0,
        "doubles": 0,
        "compet": "atp",
        "ID_TENNET": 2.0,
    },
    # TEST0002 -- groupe MIXTE, second pari : meme joueur, mise payee
    {
        "ID_BET": 90003,
        "created_at": Timestamp("2026-02-10 09:05:00"),
        "ID_USER": 999,
        "channel": "orbitx",
        "side_back_lay": "lay",
        "bookie": "bookie_test",
        "ID_MATCH": "TEST0002",
        "ID_MARKET": "9.900000002",
        "ID_REF": "900000003",
        "ao_game_id": nan,
        "type": "Match Odds",
        "bet": 1,
        "bet_libelle": "Carl Testone",
        "odds": 1.65,
        "stake": 250.0,
        "pred": nan,
        "value": nan,
        "delta_time_min": 1.0,
        "potential_profit": 162.5,
        "liability": 250.0,
        "match_type": "atp",
        "status": 1,
        "tourney_name": "Test Open",
        "tourney_level": "A",
        "winner_name": "Carl Testone",
        "loser_name": "Dan Testone",
        "round": "R16",
        "surface": "Clay",
        "match_settled": 1,
        "score": "6-4 6-3",
        "tourney_date": Timestamp("2026-02-10 12:00:00"),
        "winner_pred": 1.90,
        "loser_pred": 2.05,
        "is_ratio_odds_W": 1,
        "is_ratio_odds_L": 0,
        "doubles": 0,
        "compet": "atp",
        "ID_TENNET": 2.0,
    },
    # TEST0003 -- groupe NORMAL, premier pari : lay, petite mise
    {
        "ID_BET": 90004,
        "created_at": Timestamp("2026-03-15 08:00:00"),
        "ID_USER": 999,
        "channel": "orbitx",
        "side_back_lay": "lay",
        "bookie": "bookie_test",
        "ID_MATCH": "TEST0003",
        "ID_MARKET": "9.900000003",
        "ID_REF": "900000004",
        "ao_game_id": nan,
        "type": "Match Odds",
        "bet": 1,
        "bet_libelle": "Eve Testone",
        "odds": 1.40,
        "stake": 10.0,
        "pred": nan,
        "value": nan,
        "delta_time_min": 8.0,
        "potential_profit": 8.5,
        "liability": 10.0,
        "match_type": "wta",
        "status": 1,
        "tourney_name": "Test Cup",
        "tourney_level": "G",
        "winner_name": "Eve Testone",
        "loser_name": "Fay Testone",
        "round": "F",
        "surface": "Grass",
        "match_settled": 1,
        "score": "7-6(5) 6-4",
        "tourney_date": Timestamp("2026-03-15 14:00:00"),
        "winner_pred": 1.70,
        "loser_pred": 2.20,
        "is_ratio_odds_W": 0,
        "is_ratio_odds_L": 1,
        "doubles": 0,
        "compet": "wta",
        "ID_TENNET": 3.0,
    },
    # TEST0003 -- groupe NORMAL, second pari : back (le seul du jeu), grosse
    # mise, cote tres differente -- discrimine la moyenne ponderee.
    {
        "ID_BET": 90005,
        "created_at": NaT,
        "ID_USER": 999,
        "channel": "ao",
        "side_back_lay": "back",
        "bookie": "bookie_test",
        "ID_MATCH": "TEST0003",
        "ID_MARKET": "9.900000003",
        "ID_REF": "900000005",
        "ao_game_id": 12345.0,
        "type": "Match Odds",
        "bet": 0,
        "bet_libelle": "Eve Testone",
        "odds": 1.90,
        "stake": 300.0,
        "pred": nan,
        "value": nan,
        "delta_time_min": 2.0,
        "potential_profit": 270.0,
        "liability": 0.0,
        "match_type": "wta",
        "status": 1,
        "tourney_name": "Test Cup",
        "tourney_level": "G",
        "winner_name": "Eve Testone",
        "loser_name": "Fay Testone",
        "round": "F",
        "surface": "Grass",
        "match_settled": 1,
        "score": "7-6(5) 6-4",
        "tourney_date": Timestamp("2026-03-15 14:00:00"),
        "winner_pred": 1.70,
        "loser_pred": 2.20,
        "is_ratio_odds_W": 0,
        "is_ratio_odds_L": 1,
        "doubles": 0,
        "compet": "wta",
        "ID_TENNET": 3.0,
    },
    # TEST0004 -- mise ABSENTE (NaN, pas zero)
    {
        "ID_BET": 90006,
        "created_at": NaT,
        "ID_USER": 999,
        "channel": "orbitx",
        "side_back_lay": "lay",
        "bookie": "bookie_test",
        "ID_MATCH": "TEST0004",
        "ID_MARKET": "9.900000004",
        "ID_REF": "900000006",
        "ao_game_id": nan,
        "type": "Match Odds",
        "bet": 1,
        "bet_libelle": "Gia Testone",
        "odds": 1.55,
        "stake": nan,
        "pred": nan,
        "value": nan,
        "delta_time_min": nan,
        "potential_profit": 0.0,
        "liability": 0.0,
        "match_type": "atp",
        "status": 1,
        "tourney_name": "Test Open",
        "tourney_level": "A",
        "winner_name": "Gia Testone",
        "loser_name": "Hal Testone",
        "round": "R32",
        "surface": "Hard",
        "match_settled": 1,
        "score": "6-4 6-3",
        "tourney_date": Timestamp("2026-04-01 12:00:00"),
        "winner_pred": 1.80,
        "loser_pred": 2.10,
        "is_ratio_odds_W": 0,
        "is_ratio_odds_L": 0,
        "doubles": 0,
        "compet": "atp",
        "ID_TENNET": 4.0,
    },
]
