"""Les paris de production, rattaches aux matchs en direct.

Lecture SEULE sur le schema `TeNNet`. Ce module n'ecrit nulle part et ne passe
aucun ordre : il montre une position, il ne l'engage pas.
"""

#: Commission de l'exchange, relevee dans ses propres trames
#: (`"commission": 3.00`, seule valeur observee sur la collecte du 2026-08-10).
#:
#: C'est une CONSTANTE et non une valeur lue : l'app lit `live_now`, qui ne
#: porte pas ce champ, et l'y faire remonter est un autre chantier. Mieux vaut
#: une valeur assumee, datee, qu'une promesse que le code ne tient pas. Le jour
#: ou le taux change, c'est cette ligne qu'il faut corriger.
COMMISSION_ORBITX = 0.03


def cash_out(side_back_lay, mise, cote, cote_courante) -> float | None:
    """Ce que vaut la position si on la ferme MAINTENANT.

    Couvrir un LAY de mise `S` a la cote `O`, c'est backer au prix courant
    `O'` : le resultat est alors le meme que la selection gagne ou perde, et
    c'est cette EGALITE -- pas une estimation -- qui autorise a n'afficher
    qu'un chiffre.

        lay   ->  S x (1 - O / O')      O' = meilleur BACK (on ferme en backant)
        back  ->  S x (O / O' - 1)      O' = meilleur LAY  (on ferme en layant)

    La commission porte sur les gains NETS : elle ne mord que sur un montant
    POSITIF. L'appliquer a une perte l'afficherait plus petite qu'elle n'est,
    et l'erreur irait toujours dans le sens qui rassure.

    Rend ``None`` -- jamais zero -- quand le prix courant manque : zero serait
    un montant, et faux. Rend ``None`` aussi sur un sens inconnu : on ne devine
    pas de quel cote va l'argent.

    CE N'EST PAS le bouton « cash out » de l'exchange. Celui-ci se calcule sur
    le MEILLEUR prix affiche ; le leur applique son propre ecart et sa
    liquidite. Il est indicatif, et la page doit le dire.
    """
    sens = str(side_back_lay or "").strip().lower()
    if sens not in ("back", "lay"):
        return None
    try:
        mise, cote, courante = float(mise), float(cote), float(cote_courante)
    except (TypeError, ValueError):
        return None
    if courante <= 0 or cote <= 0:
        return None
    brut = (mise * (1 - cote / courante) if sens == "lay"
            else mise * (cote / courante - 1))
    return brut * (1 - COMMISSION_ORBITX) if brut > 0 else brut
