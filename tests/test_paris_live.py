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
    """Cez Cretu / M Moeller : 10 lay sur Moeller, 256,18 EUR de mise, cote
    moyenne 1,935, back courant 1,14. Chiffre annonce au proprietaire."""
    got = cash_out("lay", 256.18, 1.935, 1.14)
    assert got == pytest.approx(-178.6, abs=1.0)


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
