"""Les paris de production, rattaches aux matchs en direct.

Lecture SEULE sur le schema `TeNNet`. Ce module n'ecrit nulle part et ne passe
aucun ordre : il montre une position, il ne l'engage pas.
"""

import unicodedata

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


def _sans_accents(texte) -> str:
    """« Kellovský » -> « Kellovsky ».

    NFKD separe la lettre de son accent ; on jette les accents. Mesure du
    2026-08-11 : `Bet.bet_libelle` porte les accents, `live_now.participant*`
    n'en porte AUCUN sur trente lignes. Sans ce depouillement, les trois lay
    reels sur Kellovsky ne se poseraient sur aucune ligne.

    `unicodedata` et non `unidecode` : ce dernier n'est ni installe ici ni
    declare dans `pyproject.toml`, et la bibliotheque standard suffit sur des
    noms latins.
    """
    decompose = unicodedata.normalize("NFKD", str(texte))
    return "".join(c for c in decompose if not unicodedata.combining(c))


def _jetons(nom) -> list[str]:
    """Les mots d'un nom, sans accents, sans casse, sans espaces en trop.

    « San  Sin » (double espace, releve tel quel dans `Betfair_links`, et
    affiche tel quel) doit rendre DEUX jetons. `split()` sans argument s'en
    charge ; `split(" ")` rendrait un jeton VIDE, et un jeton vide prefixe
    n'importe quoi -- il designerait alors les deux joueurs.
    """
    if not nom:
        return []
    return _sans_accents(nom).lower().split()


def _designe(selection, participant) -> bool:
    """La selection designe-t-elle ce participant ?

    Le participant peut etre un nom COURT (« Yevseyev », « M Moeller ») quand
    la ligne vient de l'exchange ; la selection, elle, porte le nom complet.
    La regle : chaque jeton du participant doit prefixer un jeton DISTINCT de
    la selection, l'ordre etant libre -- « Sasikumar Mukund » designe « Mukund
    Sasikumar », les deux sources ne rangeant pas les noms indiens dans le meme
    ordre.

    Le prefixe couvre aussi la TRONCATURE de la source (« Mat Pucinelli de
    Almeid », « Joao Victor Couto Loure ») : un nom coupe est un prefixe.

    Volontairement PAUVRE, et pas par negligence : elle sert a poser un montant
    sur la bonne ligne, jamais a orienter des cotes. Une erreur ici affiche une
    position au mauvais endroit ; le refus, lui, n'affiche rien. Rapprocher les
    noms par ressemblance confondrait « Molleker » et « Moller », qui se sont
    affiches cote a cote le 2026-08-11 et portent chacun leurs paris.

    Mesuree sur 1 830 paires (pari, match) reelles des 45 derniers jours :
    1 830 resolues, 0 ambigue, 0 muette.

    L'EGALITE EXACTE N'EST PAS ESSAYEE AVANT LE PREFIXE, parce qu'elle ne sert
    a rien : un jeton egal est un jeton prefixe. Sur 5 042 paires reelles
    (120 jours), les deux versions rendent le MEME resultat, ligne pour ligne.
    Le pas supplementaire etait du code que rien ne pouvait atteindre.
    """
    sel, part = _jetons(selection), _jetons(participant)
    if not sel or not part:
        return False
    restants = list(sel)
    for jeton in part:
        trouve = next((x for x in restants if x.startswith(jeton)), None)
        if trouve is None:
            return False
        restants.remove(trouve)
    return True


def cote_du_pari(selection, participant1, participant2) -> str | None:
    """« a », « b », ou ``None`` quand on ne sait pas.

    ``None`` quand la selection ne designe personne, ET quand elle designe les
    DEUX : deux joueuses de meme patronyme rendraient le cote indecidable, et
    le poser reviendrait a le tirer au sort. Meme prudence que
    `orientation_marche_orbitx` cote PoC, qui refuse deja quand les deux
    hypotheses tiennent.
    """
    a = _designe(selection, participant1)
    b = _designe(selection, participant2)
    if a and b:
        return None
    if a:
        return "a"
    if b:
        return "b"
    return None
