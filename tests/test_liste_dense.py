

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
