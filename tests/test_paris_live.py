"""Les paris de production sur la page « En direct »."""

import pytest

from paris_live import COMMISSION_ORBITX, cash_out, cote_du_pari


def test_le_cash_out_d_un_LAY_est_le_meme_que_la_selection_gagne_ou_perde():
    """C'est cette EGALITE, et non une estimation, qui autorise a n'afficher
    qu'un seul chiffre.

    Couvrir un lay de mise S a la cote O, c'est backer au prix courant O' pour
    une mise S x O / O'. On recalcule ici les deux issues a la main, sans
    reutiliser la formule du module -- sinon on comparerait le code a
    lui-meme, le defaut qui a laisse passer l'affichage en UTC.
    """
    S, O, Op = 100.0, 2.00, 4.00
    couverture = S * O / Op                      # la mise de couverture
    si_perd = S - couverture                     # le lay gagne, le back perd
    si_gagne = -S * (O - 1) + couverture * (Op - 1)
    assert si_perd == pytest.approx(si_gagne)
    assert cash_out("lay", S, O, Op) == pytest.approx(si_perd * (1 - COMMISSION_ORBITX))


def test_le_cash_out_d_un_BACK_est_symetrique():
    S, O, Op = 100.0, 4.00, 2.00
    couverture = S * O / Op
    si_gagne = S * (O - 1) - couverture * (Op - 1)
    si_perd = -S + couverture
    assert si_gagne == pytest.approx(si_perd)
    assert cash_out("back", S, O, Op) == pytest.approx(si_gagne * (1 - COMMISSION_ORBITX))


def test_un_lay_PERDANT_rend_un_montant_negatif_SANS_commission():
    """La commission porte sur les gains NETS : elle ne s'applique pas a une
    perte. L'appliquer la ferait afficher une perte plus petite qu'elle
    n'est -- une erreur qui va toujours dans le sens qui rassure."""
    # Le prix s'est effondre : notre lay est perdant.
    perte = cash_out("lay", 100.0, 2.00, 1.25)
    assert perte == pytest.approx(100.0 * (1 - 2.00 / 1.25))
    assert perte < 0


def test_le_cas_REEL_mesure_le_2026_08_10():
    """Cez Cretu / M Moeller : dix lay sur Moeller, back courant 1,14.

    LE MONTANT EST L'APPARIE, PAS LE DEMANDE, et c'est une correction. Sur ces
    dix paris, `stake` totalise 256,18 mais `potential_profit` -- le montant
    reellement APPARIE -- 254,10. Le cash-out vaut donc -179,02 et non -180,50 :
    le chiffre annonce au proprietaire le 2026-08-10 etait calcule sur le
    demande.

    Ce n'est pas une nuance sur ce match-la. Sur 30 410 lay, 2 645 (8,7 %) ont
    un demande different de l'apparie, et `ID_BET 31421` demande 200,00 pour
    0,18 apparie -- mille cent fois trop.
    """
    got = cash_out("lay", 254.10, 1.9432, 1.14)
    assert got == pytest.approx(-179.02, abs=0.05)


def test_sans_prix_courant_il_n_y_a_PAS_de_cash_out():
    """Un marche muet ne vaut pas zero : zero serait un montant, et faux."""
    assert cash_out("lay", 100.0, 2.0, None) is None
    assert cash_out("lay", 100.0, 2.0, 0.0) is None


def test_un_sens_INCONNU_ne_produit_aucun_chiffre():
    """Ni back ni lay : on ne devine pas de quel cote va l'argent."""
    assert cash_out("place", 100.0, 2.0, 3.0) is None
    assert cash_out(None, 100.0, 2.0, 3.0) is None


# ---------------------------------------------------------------------------
# De quel cote porte le pari
#
# TOUTES les fixtures ci-dessous sont PRELEVEES sur les paris et les matchs
# reels (`TeNNet.Bet`, `TeNNet.Betfair_links`, `TeNNet_test.live_now`), jamais
# inventees. La regle a par ailleurs ete passee sur 1 830 paires (pari, match)
# reelles des 45 derniers jours : 1 830 resolues, 0 ambigue, 0 muette.
# ---------------------------------------------------------------------------


def test_le_cote_du_pari_se_lit_sur_les_CAS_REELS():
    """Quatre paris reels du 2026-08-10, avec les noms tels que les DEUX
    sources les ecrivent -- la selection en entier, le participant souvent
    abrege ou reduit au patronyme."""
    assert cote_du_pari("Denis Yevseyev", "Yevseyev", "Purtseladze") == "a"
    assert cote_du_pari("Saba Purtseladze", "Yevseyev", "Purtseladze") == "b"
    assert cote_du_pari("Marvin Moeller", "Cez Cretu", "M Moeller") == "b"
    assert cote_du_pari("Sasikumar Mukund", "Kokoro Isomura",
                        "Mukund Sasikumar") == "b"


def test_un_ACCENT_ne_fait_pas_perdre_le_pari():
    """Marche 1.260661227, trois lay reels : le pari dit « Kellovský », la
    source des participants dit « Kellovsky ». Mesure du 2026-08-11 :
    `bet_libelle` porte les accents, `live_now.participant*` n'en porte AUCUN
    sur trente lignes. Sans depouillement, ces trois paris ne se poseraient sur
    aucune ligne."""
    assert cote_du_pari("Dominik Kellovský", "Dominik Kellovsky",
                        "Joao Victor Couto Loure") == "a"


def test_un_participant_TRONQUE_par_la_source_ne_designe_pas_a_tort():
    """« Mat Pucinelli de Almeid » et « Joao Victor Couto Loure » sont releves
    tels quels : la source coupe les noms longs (la colonne, elle, est un
    `text` -- la troncature vient donc de l'exchange, et elle durera).

    Un nom coupe est un PREFIXE, et un prefixe attrape plus large : le test
    verifie qu'il n'attrape pas le mauvais joueur."""
    assert cote_du_pari("Florian Broska", "Mat Pucinelli de Almeid",
                        "Fl Broska") == "b"
    assert cote_du_pari("Dominik Kellovský", "Joao Victor Couto Loure",
                        "Dominik Kellovsky") == "b"


def test_deux_patronymes_PROCHES_restent_distincts():
    """« Molleker » et « Moller » se sont affiches cote a cote sur la page le
    2026-08-11, et « Rudolf Molleker » comme « Elmer Moller » sont deux paris
    reels. Deux lettres les separent.

    CE TEST INTERDIT LA DISTANCE D'EDITION. Si l'on rapproche un jour les noms
    par ressemblance -- la piste ouverte pour « San  Sin » contre « Sanhui
    Shin » -- il tombera, et c'est ce qu'on lui demande : poser une mise sur la
    mauvaise ligne est pire que ne pas la poser."""
    assert cote_du_pari("Rudolf Molleker", "Molleker", "Moller") == "a"
    assert cote_du_pari("Elmer Moller", "Molleker", "Moller") == "b"


def test_les_DOUBLES_se_designent_par_l_EQUIPE():
    """Zaar/Zimmermann contre Brockmann/Kraus : un match reel qui porte des
    paris reels des DEUX cotes. La paire s'ecrit d'un bloc, sans espace autour
    de la barre."""
    assert cote_du_pari("Zaar/Zimmermann", "Zaar/Zimmermann",
                        "Brockmann/Kraus") == "a"
    assert cote_du_pari("Brockmann/Kraus", "Zaar/Zimmermann",
                        "Brockmann/Kraus") == "b"


def test_le_DOUBLE_ESPACE_de_la_source_ne_fabrique_pas_un_jeton():
    """« San  Sin » est releve tel quel dans `Betfair_links`, et s'affiche tel
    quel. Decoupe sur `" "`, il rendrait un jeton VIDE -- et un jeton vide
    prefixe n'importe quoi, donc il designerait les deux joueurs."""
    assert cote_du_pari("San Sin", "San  Sin", "Arutiunian") == "a"


def test_une_selection_AMBIGUE_ne_designe_aucun_cote():
    """Deux joueuses que la selection designe toutes les deux : poser le
    montant reviendrait a tirer le cote au sort.

    LA COMPOSITION EST REELLE meme si le cas ne s'est pas encore produit --
    Jessica et Tatiana Pieri se rencontrent (`Betfair_links`), et `live_now`
    reduit sept lignes sur trente au seul patronyme. Le jour ou les deux se
    rejoignent, on n'affiche pas de cash-out ; la mise, elle, ne depend
    d'aucun cote et reste affichee."""
    assert cote_du_pari("Jessica Pieri", "Pieri", "Pieri") is None


def test_une_selection_INCONNUE_ne_designe_aucun_cote():
    assert cote_du_pari("Rafael Nadal", "Yevseyev", "Purtseladze") is None
    assert cote_du_pari(None, "Yevseyev", "Purtseladze") is None
    assert cote_du_pari("Denis Yevseyev", None, None) is None


def test_un_jeton_de_la_selection_ne_sert_QU_UNE_FOIS():
    """Un jeton du participant consomme un jeton DISTINCT de la selection.

    LA FORME EST CONSTRUITE, et il faut le dire : sur 5 042 paires (pari,
    match) reelles, retirer cette contrainte ne change AUCUN resultat, parce
    qu'aucun libelle de pari en simple ne tient en un seul mot -- les seuls
    libelles d'un mot sont les paires de double (« Ebden/Ram »).

    On la garde parce qu'elle ne peut que RESSERRER la regle. Sans elle,
    « M Moeller » designerait un « Moeller » seul ; le jour ou la source
    raccourcit un libelle, la mise de Marvin Moeller partirait sur la ligne
    d'Elmer Moller, qui s'affiche a deux lignes de la sienne.
    """
    from paris_live import _designe

    assert _designe("Marvin Moeller", "M Moeller") is True
    assert _designe("Moeller", "M Moeller") is False


# ---------------------------------------------------------------------------
# Lire les paris du compte connecte
# ---------------------------------------------------------------------------


def test_la_lecture_ne_demande_QUE_les_marches_a_l_ecran():
    """On n'ouvre pas l'historique des paris pour afficher dix matchs. Et le
    schema interroge est `TeNNet`, en LECTURE SEULE."""
    import pandas as pd

    from paris_live import charger_paris

    vues = {}

    def lecteur(schema, requete, params=None):
        vues.update(schema=schema, requete=requete, params=params)
        return pd.DataFrame(columns=["ID_BET"])

    charger_paris(1, ["1.260944641", "1.260910091"], lecteur=lecteur)
    assert vues["schema"] == "TeNNet"
    assert set(vues["params"].values()) >= {"1.260944641", "1.260910091", 1}
    assert "status = 1" in vues["requete"]
    assert "FROM Bet" in vues["requete"]
    for interdit in ("INSERT", "UPDATE", "DELETE", "REPLACE", "DROP"):
        assert interdit not in vues["requete"].upper()


def test_le_compte_est_LIE_et_non_interpole():
    """Un pari est prive. Si l'identifiant de compte se collait dans le texte
    de la requete, il suffirait d'y glisser autre chose pour lire les paris de
    quelqu'un d'autre -- les trois comptes vivent dans la meme table."""
    import pandas as pd

    from paris_live import charger_paris

    vues = {}

    def lecteur(schema, requete, params=None):
        vues.update(requete=requete, params=params)
        return pd.DataFrame(columns=["ID_BET"])

    charger_paris("8 OR 1=1", ["1.260944641"], lecteur=lecteur)
    assert "OR 1=1" not in vues["requete"]
    assert "8 OR 1=1" in vues["params"].values()
    # Lier le compte ne sert a rien si la requete ne s'en sert pas pour
    # FILTRER. Le marche 1.258126887 porte 31 paris des TROIS comptes : sans
    # cette clause, la page les afficherait tous.
    assert "ID_USER = :compte" in vues["requete"], (
        "le compte est lie mais pas filtre : les paris des autres comptes "
        "remonteraient"
    )


def test_un_identifiant_de_marche_HOSTILE_reste_dans_les_PARAMETRES():
    """`read_sql_query(schema, query, params)` LIE les paramètres nommes
    `:nom` -- sa propre docstring le dit. Rien de ce qui vient d'ailleurs n'a
    donc a etre colle dans le texte de la requete, ni assaini a la main.
    """
    import pandas as pd

    from paris_live import charger_paris

    vues = {}

    def lecteur(schema, requete, params=None):
        vues.update(requete=requete, params=params)
        return pd.DataFrame(columns=["ID_BET"])

    hostile = "1.26' OR '1'='1"
    charger_paris(1, [hostile, "1.260\\"], lecteur=lecteur)
    assert "'" not in vues["requete"]
    assert "\\" not in vues["requete"]
    assert hostile in vues["params"].values()


def test_sans_marche_a_l_ecran_AUCUNE_requete_n_est_emise():
    """Une requete a vide s'executerait a chaque rafraichissement pour rien."""
    from paris_live import charger_paris

    appels = []
    charger_paris(1, [], lecteur=lambda *a, **k: appels.append(1))
    assert appels == []


def test_sans_utilisateur_AUCUNE_requete_n_est_emise():
    """Pas de session, pas de paris -- et surtout pas les paris de tout le
    monde : la table en porte trois comptes."""
    from paris_live import charger_paris

    appels = []
    charger_paris(None, ["1.260944641"], lecteur=lambda *a, **k: appels.append(1))
    assert appels == []


def test_sans_pari_les_COLONNES_attendues_sont_quand_meme_la():
    """L'appelant lit `df["stake"]` sans regarder si le tableau est vide. Un
    tableau sans colonnes le ferait tomber en `KeyError` les jours ou aucun
    pari n'est en cours -- c'est-a-dire la plupart."""
    import pandas as pd

    from paris_live import charger_paris

    vide = charger_paris(1, [], lecteur=lambda *a, **k: None)
    for colonne in ("ID_BET", "ID_MARKET", "side_back_lay", "bet_libelle",
                    "odds", "stake", "potential_profit", "liability"):
        assert colonne in vide.columns
    rien = charger_paris(1, ["1.260944641"],
                         lecteur=lambda *a, **k: pd.DataFrame())
    assert "stake" in rien.columns


# ---------------------------------------------------------------------------
# La position du compte sur chaque match affiche
#
# Fixtures PRELEVEES sur le marche 1.260944641 (Yevseyev / Purtseladze,
# 2026-08-10) : huit lay reels, quatre de chaque cote.
# ---------------------------------------------------------------------------


def _match(**surcharges):
    base = {
        "event_id": "3818322", "id_market": "1.260944641",
        "participant1": "Yevseyev", "participant2": "Purtseladze",
        "back_odds_a": 1.30, "lay_odds_a": 1.32,
        "back_odds_b": 4.20, "lay_odds_b": 4.40,
        "status": "InPlay",
    }
    base.update(surcharges)
    return base


def _pari(**surcharges):
    """ID_BET 31402, releve tel quel."""
    base = {
        "ID_BET": 31402, "ID_MARKET": "1.260944641", "side_back_lay": "lay",
        "bet_libelle": "Denis Yevseyev", "odds": 1.72, "stake": 62.58,
        "potential_profit": 62.58, "liability": 45.06,
    }
    base.update(surcharges)
    return base


def test_le_montant_qui_compte_est_l_APPARIE_pas_le_DEMANDE():
    """ID_BET 31398, releve tel quel : 57,72 demandes, 4,52 apparies. La
    responsabilite vaut 3,25, soit 4,52 x (1,72 - 1) -- elle suit l'APPARIE.

    Mesure sur 30 410 lay : `liability = potential_profit x (cote - 1)` tient
    30 404 fois, contre 27 782 pour `stake`. Calculer sur le demande gonflerait
    la position d'un facteur mille sur `ID_BET 31421` (200,00 demandes, 0,18
    apparie)."""
    import pandas as pd

    from paris_live import cash_out, positions

    partiel = _pari(ID_BET=31398, odds=1.72, stake=57.72,
                    potential_profit=4.52, liability=3.25)
    pos = positions(pd.DataFrame([partiel]), [_match()])["3818322"]["a"]
    assert pos["cash_out"] == pytest.approx(cash_out("lay", 4.52, 1.72, 1.30))
    assert pos["cash_out"] != pytest.approx(cash_out("lay", 57.72, 1.72, 1.30))
    assert pos["demande"] == pytest.approx(57.72)
    assert pos["mise"] == pytest.approx(3.25)


def test_les_paris_d_un_meme_cote_s_ADDITIONNENT():
    """Chaque couverture est un montant garanti ; leur somme l'est aussi."""
    import pandas as pd

    from paris_live import cash_out, positions

    paris = pd.DataFrame([
        _pari(),
        _pari(ID_BET=31396, odds=1.67, stake=13.81, potential_profit=13.81,
              liability=9.25),
    ])
    pos = positions(paris, [_match()])["3818322"]["a"]
    assert pos["n"] == 2
    assert pos["mise"] == pytest.approx(45.06 + 9.25)
    assert pos["gain"] == pytest.approx(62.58 + 13.81)
    assert pos["cash_out"] == pytest.approx(
        cash_out("lay", 62.58, 1.72, 1.30) + cash_out("lay", 13.81, 1.67, 1.30))


def test_un_match_parie_des_DEUX_cotes_donne_DEUX_positions():
    """Cas reel du 2026-08-10 : Yevseyev ET Purtseladze layes sur le meme
    marche, quatre paris chacun. Ce sont deux positions distinctes, qui se
    couvrent a deux prix differents -- surtout pas leur somme."""
    import pandas as pd

    from paris_live import positions

    paris = pd.DataFrame([
        _pari(),
        _pari(ID_BET=31401, bet_libelle="Saba Purtseladze", odds=2.20,
              stake=61.12, potential_profit=61.12, liability=73.34),
    ])
    pos = positions(paris, [_match()])["3818322"]
    assert pos["a"]["n"] == 1 and pos["b"]["n"] == 1
    assert pos["a"]["cash_out"] != pos["b"]["cash_out"]
    assert pos["a"]["cote_courante"] == 1.30
    assert pos["b"]["cote_courante"] == 4.20


def test_un_lay_se_couvre_sur_le_BACK_courant_du_BON_cote():
    """Fermer un lay, c'est BACKER : le prix a prendre est `back_odds_?` du
    cote parie, et non le lay, ni le prix de l'autre joueur. Les quatre cotes
    de la fixture sont DISTINCTES pour que l'erreur se voie."""
    import pandas as pd

    from paris_live import cash_out, positions

    pos = positions(pd.DataFrame([_pari()]), [_match()])["3818322"]["a"]
    assert pos["cote_courante"] == 1.30
    assert pos["cash_out"] == pytest.approx(cash_out("lay", 62.58, 1.72, 1.30))


def test_un_back_se_couvre_sur_le_LAY_courant():
    """Et son montant apparie est `stake` : sur les 47 paris back de
    l'historique, `liability = stake` et `potential_profit = stake x
    (cote - 1)`, 47 fois sur 47. L'asymetrie avec le lay est reelle."""
    import pandas as pd

    from paris_live import cash_out, positions

    dos = _pari(side_back_lay="back", odds=1.72, stake=50.0,
                potential_profit=36.0, liability=50.0)
    pos = positions(pd.DataFrame([dos]), [_match()])["3818322"]["a"]
    assert pos["cote_courante"] == 1.32
    assert pos["cash_out"] == pytest.approx(cash_out("back", 50.0, 1.72, 1.32))


def test_deux_SENS_sur_le_meme_cote_se_couvrent_chacun_sur_SA_colonne():
    """Le cas ne s'est jamais produit -- zero selection porte les deux sens
    dans tout l'historique -- mais prendre le sens du PREMIER pari pour toute
    la position rendrait un montant credible et faux le jour ou il arrive.
    Le prix de couverture se choisit pari par pari."""
    import pandas as pd

    from paris_live import cash_out, positions

    paris = pd.DataFrame([
        _pari(),
        _pari(ID_BET=31403, side_back_lay="back", stake=50.0,
              potential_profit=36.0, liability=50.0),
    ])
    pos = positions(paris, [_match()])["3818322"]["a"]
    assert pos["cash_out"] == pytest.approx(
        cash_out("lay", 62.58, 1.72, 1.30) + cash_out("back", 50.0, 1.72, 1.32))
    assert pos["cote_courante"] is None      # deux prix, aucun a afficher


def test_un_pari_NON_RATTACHE_garde_sa_mise_et_perd_son_cash_out():
    """La mise et le risque ne dependent d'aucun cote : ils restent. Le
    cash-out, lui, exige de savoir sur quel prix se couvrir."""
    import pandas as pd

    from paris_live import positions

    paris = pd.DataFrame([_pari(bet_libelle="Joueur Inconnu")])
    pos = positions(paris, [_match()])["3818322"]
    assert pos["a"] is None and pos["b"] is None
    assert len(pos["non_rattaches"]) == 1
    assert pos["non_rattaches"][0]["liability"] == pytest.approx(45.06)


def test_un_match_TERMINE_n_a_plus_de_cash_out():
    """Il n'y a plus rien a couvrir. La mise et le risque restent."""
    import pandas as pd

    from paris_live import positions

    pos = positions(pd.DataFrame([_pari()]),
                    [_match(status="Finished")])["3818322"]["a"]
    assert pos["cash_out"] is None
    assert pos["mise"] == pytest.approx(45.06)


def test_un_prix_ABSENT_ne_produit_pas_un_cash_out_a_zero():
    """Zero serait un montant, et faux : la position existe toujours."""
    import pandas as pd

    from paris_live import positions

    pos = positions(pd.DataFrame([_pari()]),
                    [_match(back_odds_a=None)])["3818322"]["a"]
    assert pos["cash_out"] is None
    assert pos["cote_courante"] is None
    assert pos["mise"] == pytest.approx(45.06)


def test_la_cote_MOYENNE_est_ponderee_par_l_apparie():
    """Ponderer par le demande donnerait un prix moyen que personne n'a
    obtenu -- `ID_BET 31398` demande 57,72 pour 4,52 apparies."""
    import pandas as pd

    from paris_live import positions

    paris = pd.DataFrame([
        _pari(),
        _pari(ID_BET=31398, odds=1.66, stake=57.72, potential_profit=4.52,
              liability=3.25),
    ])
    pos = positions(paris, [_match()])["3818322"]["a"]
    attendu = (1.72 * 62.58 + 1.66 * 4.52) / (62.58 + 4.52)
    assert pos["cote_moyenne"] == pytest.approx(attendu)


def test_un_match_SANS_pari_n_apparait_pas():
    """La liste est dense : elle ne se remplit pas de cases vides."""
    import pandas as pd

    from paris_live import positions

    assert positions(pd.DataFrame(columns=["ID_MARKET"]), [_match()]) == {}
