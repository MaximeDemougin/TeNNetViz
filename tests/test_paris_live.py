"""Les paris de production sur la page « En direct »."""

import pytest

from paris_live import COMMISSION_ORBITX, cash_out


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
