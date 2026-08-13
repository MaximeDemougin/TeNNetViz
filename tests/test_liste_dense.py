

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


# ── La position du compte sur la ligne ───────────────────────────────────
#
# Les paris de production, poses sur la ligne du joueur parie. Fixture
# PRELEVEE : Yevseyev / Purtseladze, marche 1.260944641, huit lay reels du
# 2026-08-10.


def _match_parie(**surcharges):
    base = {
        "event_id": "3818322", "participant1": "Yevseyev",
        "participant2": "Purtseladze", "score": "1-0", "points": "15-0",
        "back_odds_a": 1.30, "lay_odds_a": 1.32,
        "back_odds_b": 4.20, "lay_odds_b": 4.40,
        "league": "Astana Challenger", "tour_type": "atp",
        "start_timestamp": 1786449600.0, "updated_ts": 1786449600.0,
        "age_exchange_s": 2.0,
    }
    base.update(surcharges)
    return base


def test_la_position_se_pose_sur_la_ligne_du_JOUEUR_parie():
    """Un match parie d'un seul cote n'affiche qu'un montant, sur la bonne
    ligne. Le poser sur l'autre joueur inverserait la lecture -- et les deux
    joueurs sont a deux lignes d'ecart, pas a deux pages."""
    import pandas as pd

    from liste_dense import lignes

    pos = {"3818322": {"a": {"cash_out": -31.9}, "b": None,
                       "non_rattaches": []}}
    ligne = lignes(pd.DataFrame([_match_parie()]),
                   maintenant=1786449600.0, positions=pos)[0]
    assert ligne["joueurs"][0]["cash_out"] == -31.9
    assert ligne["joueurs"][1]["cash_out"] is None


def test_sans_position_la_colonne_reste_VIDE():
    """Une liste dense ne se remplit pas de cases inutiles : pas de tiret,
    rien. Le tiret est reserve a une donnee ABSENTE -- une cote qu'on
    attendait -- pas a une donnee SANS OBJET, comme la position d'un match sur
    lequel on n'a rien parie.

    L'assertion porte sur la CELLULE, pas sur la page : chercher « position »
    dans tout le HTML repondrait « present » a cause de l'entete de colonne.
    """
    import pandas as pd

    from liste_dense import lignes, rendu

    html = rendu(lignes(pd.DataFrame([_match_parie()]),
                        maintenant=1786449600.0, positions={}))
    cellule = html.split('<span class="position">')[2].split("</span></span>")[0]
    assert "€" not in cellule
    assert "—" not in cellule
    assert not any(c.isdigit() for c in cellule)


def test_le_signe_du_cash_out_est_LISIBLE_dans_le_rendu():
    """Un gain et une perte ne doivent pas se lire pareil : c'est la seule
    chose que l'oeil cherche sur cette colonne. Le signe se lit sur la CLASSE
    et pas seulement sur le texte, pour que la feuille de style puisse les
    peindre differemment."""
    import pandas as pd

    from liste_dense import lignes, rendu

    df = pd.DataFrame([_match_parie()])
    perte = rendu(lignes(df, maintenant=1786449600.0,
                         positions={"3818322": {"a": {"cash_out": -178.6},
                                                "b": None,
                                                "non_rattaches": []}}))
    gain = rendu(lignes(df, maintenant=1786449600.0,
                        positions={"3818322": {"a": {"cash_out": 42.5},
                                               "b": None,
                                               "non_rattaches": []}}))
    assert "perte" in perte and "gain" not in perte
    assert "gain" in gain and "perte" not in gain
    # LE SIGNE EST ECRIT, et pas seulement peint. Le vert et le rouge le
    # DOUBLENT ; s'ils le remplacaient, un daltonien lirait un gain pour une
    # perte -- c'est la meme regle que la lettre « b »/« l » sur les prix.
    assert "-179" in perte, (
        "le signe n'est pas ecrit : seule la couleur distinguerait un gain "
        "d'une perte"
    )
    assert "+42" in gain


def test_un_cash_out_a_ZERO_se_lit_comme_un_GAIN_pas_comme_une_perte():
    """Zero n'est pas une perte, et le signe le dirait si la comparaison
    basculait a `> 0`."""
    import pandas as pd

    from liste_dense import lignes, rendu

    html = rendu(lignes(pd.DataFrame([_match_parie()]), maintenant=1786449600.0,
                        positions={"3818322": {"a": {"cash_out": 0.0},
                                               "b": None,
                                               "non_rattaches": []}}))
    assert "perte" not in html


def test_la_position_vieillit_avec_les_COTES_qui_la_calculent():
    """Le cash-out n'a pas de pastille propre, et n'en a pas besoin : il se
    calcule sur les cotes de la MEME ligne. Un prix perime rougit deja la
    pastille d'exchange -- ce test dit que les deux parlent bien du meme
    instant, et interdit qu'on les separe un jour."""
    import pandas as pd

    from live_data import SEUILS_PAR_FLUX
    from liste_dense import lignes

    vieux = SEUILS_PAR_FLUX["f_exchange"][1] + 60.0
    ligne = lignes(pd.DataFrame([_match_parie(age_exchange_s=vieux)]),
                   maintenant=1786449600.0,
                   positions={"3818322": {"a": {"cash_out": -178.6},
                                          "b": None, "non_rattaches": []}})[0]
    assert ligne["joueurs"][0]["cash_out"] == -178.6
    perimes = [f["etat"] for f in ligne["fraicheur"] if f["flux"] == "f_exchange"]
    assert perimes == ["perime"], (
        "la pastille d'exchange ne rougit pas : le montant serait affiche "
        "avec une confiance que le prix ne merite pas"
    )


def test_un_match_TERMINE_montre_encore_ce_qui_etait_ENGAGE():
    """Un match fini n'a plus de cash-out -- il n'y a plus rien a couvrir --
    mais il porte toujours l'argent qu'on y a mis, et il reste affiche six
    heures. Laisser la colonne vide ferait disparaitre la position a la
    seconde ou le match se termine, au moment precis ou l'on veut la relire.

    LE MONTANT EST NEUTRE ET SANS SIGNE : c'est un ENGAGEMENT, pas un
    resultat. Peint en vert ou en rouge, il se lirait comme un gain ou une
    perte.
    """
    import pandas as pd

    from liste_dense import lignes, rendu

    pos = {"3818322": {"a": {"cash_out": None, "mise": 45.06}, "b": None,
                       "non_rattaches": []}}
    html = rendu(lignes(pd.DataFrame([_match_parie(status="Finished")]),
                        maintenant=1786449600.0, positions=pos))
    cellule = html.split('<span class="position">')[2].split("</span></span>")[0]
    assert "45" in cellule
    assert "+" not in cellule and "-" not in cellule
    assert "gain" not in cellule and "perte" not in cellule
    assert "engage" in cellule


def test_le_cash_out_PRIME_sur_l_engagement_quand_il_existe():
    """Tant que le match se joue, c'est la valeur de sortie qui compte. Les
    deux montants dans la meme case se liraient l'un pour l'autre."""
    import pandas as pd

    from liste_dense import lignes, rendu

    pos = {"3818322": {"a": {"cash_out": -178.6, "mise": 45.06}, "b": None,
                       "non_rattaches": []}}
    html = rendu(lignes(pd.DataFrame([_match_parie()]),
                        maintenant=1786449600.0, positions=pos))
    cellule = html.split('<span class="position">')[2].split("</span></span>")[0]
    assert "-179" in cellule
    assert "45" not in cellule


# ── Les lignes SANS aucune source de score ───────────────────────────────
#
# Signale le 2026-08-13 : « pourquoi on n'a pas les matchs de Hambourg ? ».
# Ils ETAIENT a l'ecran -- mais sans score, sans jeux, et donc invisibles a
# l'oeil qui cherche un match.
#
# Fixture PRELEVEE : Nedic / Taberner et Rehberg / Purtseladze, Hamburg
# Challenger, publies en `exchange_seul` le 2026-08-13. Aucune des trois
# sources de score ne les couvre -- l'API n'a livre que Cincinnati, Astana,
# Toronto et Montreal ce jour-la, le canal OrbitX ne pousse rien pour eux, et
# le capteur WS est en veille depuis le matin.


def _match_cotes_seules(**surcharges):
    base = {
        "event_id": "prod:hbg1", "id_market": "1.261047794",
        "participant1": "Andrej Nedic", "participant2": "Carlos Taberner",
        "score": None, "points": None, "source_score": "exchange_seul",
        "back_odds_a": 2.58, "lay_odds_a": 2.64,
        "back_odds_b": 1.57, "lay_odds_b": 1.60,
        "league": "Hamburg Challenger", "tour_type": "atp",
        "start_timestamp": 1786449600.0, "updated_ts": 1786449600.0,
        "age_score_s": 2.0, "age_exchange_s": 2.0,
    }
    base.update(surcharges)
    return base


def test_la_pastille_de_score_ne_dit_PAS_frais_sans_source_de_score():
    """LE DEFAUT LE PLUS GRAVE DES DEUX, parce qu'il MENT.

    `age_score_s` vaut 2 s sur ces lignes -- l'age du cycle de publication,
    pas celui d'un score. La pastille annoncait donc « frais » pour un match
    dont AUCUNE source ne donne le score. Une pastille verte sur une absence
    est pire qu'une pastille absente : elle affirme.

    « inconnu » est le vocabulaire deja employe par cette liste pour un flux
    dont on ne sait rien.
    """
    from liste_dense import etat_fraicheur

    etats = {f["flux"]: f["etat"]
             for f in etat_fraicheur(_match_cotes_seules(), 1786449600.0)}
    assert etats["f_score"] == "inconnu", etats
    # L'exchange, lui, alimente REELLEMENT cette ligne : sa pastille reste.
    assert etats["f_exchange"] == "frais"


def test_une_ligne_sans_source_de_score_le_DIT():
    """Un tiret muet se lit comme un defaut d'affichage. La ligne doit dire
    ce qu'elle est : un match reel, dont on n'a que les cotes."""
    import pandas as pd

    from liste_dense import lignes, rendu

    html = rendu(lignes(pd.DataFrame([_match_cotes_seules()]),
                        maintenant=1786449600.0))
    assert "cotes seules" in html


def test_une_ligne_AVEC_un_score_ne_porte_NI_marqueur_NI_pastille_inconnue():
    """LE CAS DISCRIMINANT. Sans lui, marquer toutes les lignes passerait le
    test precedent et rendrait le marqueur muet."""
    import pandas as pd

    from liste_dense import etat_fraicheur, lignes, rendu

    avec = _match_cotes_seules(source_score="union", score="6-4, 3-2",
                               points="30-15")
    etats = {f["flux"]: f["etat"] for f in etat_fraicheur(avec, 1786449600.0)}
    assert etats["f_score"] == "frais"
    html = rendu(lignes(pd.DataFrame([avec]), maintenant=1786449600.0))
    assert "cotes seules" not in html


def test_le_marqueur_suit_la_SOURCE_et_non_l_absence_de_score():
    """Un match qui n'a pas encore de score mais dont une source EXISTE
    (premier jeu, l'API l'annonce sans score) ne doit pas etre marque : la
    source est la, elle n'a simplement rien a dire encore."""
    import pandas as pd

    from liste_dense import lignes, rendu

    html = rendu(lignes(pd.DataFrame([_match_cotes_seules(source_score="union")]),
                        maintenant=1786449600.0))
    assert "cotes seules" not in html
