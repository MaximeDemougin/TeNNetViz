

def test_une_ligne_SANS_score_rend_le_TIRET_comme_une_cote_absente():
    """Le tiret est le vocabulaire deja employe pour une donnee absente --
    c'est ce que `_prix` fait pour une cote manquante. Une case VIDE se lirait
    comme un defaut d'affichage, pas comme une absence.

    Signale le 2026-08-10 : les matchs sans aucune source de score portent des
    cotes et rien d'autre. `jeux_par_joueur` rend deux listes VIDES sur un
    score illisible, donc la colonne des sets sortait vide.

    Fixture DISCRIMINANTE : les cotes sont PRESENTES et le score ABSENT. Une
    ligne ou tout manque ne dirait pas laquelle des deux colonnes est en cause.
    """
    import pandas as pd

    from liste_dense import lignes, rendu

    df = pd.DataFrame([{
        "event_id": "prod:abc", "participant1": "Jan Opitz",
        "participant2": "Ol Krutykh", "score": None, "points": None,
        "back_odds_a": 1.10, "lay_odds_a": 1.12,
        "back_odds_b": 8.20, "lay_odds_b": 8.80,
        "league": "Hamburg Challenger", "tour_type": "atp",
        "start_timestamp": 1786360000.0, "updated_ts": 1786360600.0,
        "age_exchange_s": 2.0,
    }])
    html = rendu(lignes(df, maintenant=1786360600.0))
    assert "1.10" in html or "1.1" in html, (
        "les cotes ne sont pas rendues : la fixture ne discrimine rien"
    )
    assert "—" in html, (
        "la colonne des sets sort VIDE au lieu du tiret employe partout "
        "ailleurs pour une donnee absente"
    )


# ── Les heures affichees sont celles de PARIS ────────────────────────────
#
# Signale le 2026-08-11 : « les heures de l'app (au moins sur la page direct)
# ne sont pas a l'heure de Paris ».
#
# Cause : `pd.to_datetime(epoch, unit="s")` rend un timestamp NAIF en UTC.
# Le `.strftime()` qui suit affiche donc de l'UTC, alors que la machine et
# l'utilisateur sont a Paris. L'app porte pourtant `utils.to_paris` depuis
# longtemps, et trois autres pages s'en servent deja.
#
# LES DEUX EPOQUES SONT LE COEUR DE CES TESTS. Un correctif qui ajouterait
# deux heures en dur passerait l'ete et se tromperait l'hiver ; seul un couple
# ete/hiver le fait rougir.

TS_ETE = 1786449600    # 2026-08-11 12:00 UTC  ->  14:00 a Paris (CEST, +2)
TS_HIVER = 1800014400  # 2027-01-15 12:00 UTC  ->  13:00 a Paris (CET,  +1)


def test_l_heure_de_depart_est_a_l_heure_de_PARIS():
    from liste_dense import _heure

    assert _heure(TS_ETE) == "14:00"


def test_l_heure_suit_le_CHANGEMENT_D_HEURE():
    """Un decalage code en dur passerait le test precedent et mentirait de
    novembre a mars."""
    from liste_dense import _heure

    assert _heure(TS_HIVER) == "13:00"


def test_une_heure_absente_reste_absente():
    """La conversion ne doit pas transformer un « je ne sais pas » en une
    heure."""
    import pandas as pd

    from liste_dense import _heure

    assert _heure(None) == "--:--"
    assert _heure(pd.NaT) == "--:--"
