"""Les paris de production, rattaches aux matchs en direct.

Lecture SEULE sur le schema `TeNNet`. Ce module n'ecrit nulle part et ne passe
aucun ordre : il montre une position, il ne l'engage pas.
"""

import unicodedata

import pandas as pd

#: Le schema de PRODUCTION, en LECTURE SEULE. Les paris n'existent que la.
SCHEMA_PRODUCTION = "TeNNet"

#: Les colonnes lues, nommees une fois. `SELECT *` embarquerait vingt-deux
#: colonnes dont deux tiers ne servent pas, et masquerait un changement de
#: schema derriere un KeyError lointain.
COLONNES_PARIS = (
    "ID_BET", "ID_MARKET", "side_back_lay", "bet_libelle", "odds", "stake",
    "potential_profit", "liability", "created_at",
)

#: Commission de l'exchange, relevee dans ses propres trames
#: (`"commission": 3.00`, seule valeur observee sur la collecte du 2026-08-10).
#:
#: C'est une CONSTANTE et non une valeur lue : l'app lit `live_now`, qui ne
#: porte pas ce champ, et l'y faire remonter est un autre chantier. Mieux vaut
#: une valeur assumee, datee, qu'une promesse que le code ne tient pas. Le jour
#: ou le taux change, c'est cette ligne qu'il faut corriger.
COMMISSION_ORBITX = 0.03


def cash_out(side_back_lay, mise, cote, cote_courante,
             avec_commission: bool = True) -> float | None:
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

    ELLE SE PRELEVE UNE FOIS PAR MARCHE, ET NON PAR PARI -- la trame de
    l'exchange porte `"commission": 3.00` une seule fois, au niveau du marche.
    Une position batie en plusieurs fois pendant que le prix bouge a donc des
    jambes des DEUX signes, et la prelever jambe par jambe la ferait mordre
    sur les gagnantes sans que les perdantes la reduisent. Mesure du
    2026-08-11 sur les cinq lay reels de Facundo Mena a 2,68 : 0,6007 au lieu
    de 0,6426, soit six pour cent de trop. `avec_commission=False` rend le
    montant BRUT, pour que l'appelant somme d'abord et preleve ensuite.

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
    if not avec_commission:
        return brut
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

    ET IL JOUE DANS LES DEUX SENS, parce que le PARI aussi est coupe : 1 232
    libelles sur 30 459 (4 %) font 23 caracteres pile. Le defaut est apparu EN
    SERVICE le 2026-08-11 -- « Nikolas Sanchez Izquier » contre le participant
    « Sanchez Izquierdo », que l'exchange publie en entier -- et trois comptes
    y avaient de l'argent. Il ne se voyait pas dans l'historique, ou
    `Betfair_links` coupe les DEUX cotes de la meme facon.

    AUCUN SEUIL DE LONGUEUR sur ce sens-la : 14 % des libelles tronques
    finissent par un jeton de moins de quatre lettres (« Marcelo Tomas Barrios
    V », « Paulo Andre Saraiva Dos »), et un seuil les refuserait.

    Volontairement PAUVRE, et pas par negligence : elle sert a poser un montant
    sur la bonne ligne, jamais a orienter des cotes. Une erreur ici affiche une
    position au mauvais endroit ; le refus, lui, n'affiche rien. Rapprocher les
    noms par ressemblance confondrait « Molleker » et « Moller », qui se sont
    affiches cote a cote le 2026-08-11 et portent chacun leurs paris.

    Mesuree sur les 8 990 paires (pari, match) reelles de tout l'historique :
    8 990 resolues, 0 ambigue, 0 muette. Ouvrir le prefixe dans les deux sens
    n'a change qu'UN SEUL resultat, celui qu'on visait.

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
            # L'autre sens : c'est la SELECTION qui est coupee.
            trouve = next((x for x in restants if jeton.startswith(x)), None)
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


def charger_paris(id_user, id_markets, lecteur=None) -> pd.DataFrame:
    """Les paris MATCHES du compte, pour les SEULS marches donnes.

    `status = 1` seulement : `status = 2` existe (151 paris sur les 30 derniers
    jours, contre 5 140) mais sa signification n'est PAS etablie. On l'ecarte
    en le disant, plutot que de deviner ce qu'il vaut.

    TOUT CE QUI VIENT D'AILLEURS EST LIE, jamais colle dans le texte de la
    requete. `read_sql_query(schema, query, params)` accepte des parametres
    nommes `:nom` et sa propre docstring dit qu'ils previennent l'injection.
    Ce module ne reprend donc PAS l'assainissement a la main de
    `live_data._identifiants_surs`, dont la justification -- « pas d'API de
    parametres bindes exposee » -- est fausse, verifie le 2026-08-11.

    Le compte compte double : la table porte les paris de TROIS comptes, et un
    pari est prive.

    `lecteur` est injectable pour les tests, comme `live_data.charger_matchs`.
    L'import est differe pour la meme raison : `db_utils` fait un `os.chdir`
    des l'import.
    """
    marches = [str(m) for m in (id_markets or []) if m]
    if not marches or id_user is None:
        return pd.DataFrame(columns=list(COLONNES_PARIS))
    if lecteur is None:
        from live_data import _lecteur_par_defaut

        lecteur = _lecteur_par_defaut()
    lies = {f"m{i}": m for i, m in enumerate(marches)}
    trous = ", ".join(f":{nom}" for nom in lies)
    requete = (
        f"SELECT {', '.join(COLONNES_PARIS)} FROM Bet "
        f"WHERE ID_USER = :compte AND status = 1 "
        f"AND ID_MARKET IN ({trous})"
    )
    df = lecteur(SCHEMA_PRODUCTION, requete, {**lies, "compte": id_user})
    if df is None or df.empty:
        return pd.DataFrame(columns=list(COLONNES_PARIS))
    return df.copy()


#: Statuts qui disent qu'il n'y a plus rien a couvrir. Repris de
#: `live_data.charger_matchs`, qui calcule `en_cours` sur le meme jeu.
STATUTS_FINIS = frozenset(
    {"finished", "ended", "completed", "retired", "walkover", "cancelled"}
)


def _nombre(valeur):
    """Le flottant, ou ``None`` -- y compris pour NaN, que pandas seme partout
    et qui contaminerait silencieusement toute somme qui le touche."""
    try:
        f = float(valeur)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def risque(pari):
    """Ce que ce pari peut PERDRE. C'est la colonne `stake`, pour les deux sens.

    CORRIGE LE 2026-08-12, sur signalement du proprietaire confronte a son
    compte reel. Le robot de production remplit `stake` depuis la colonne
    `liability` que l'exchange rapporte pour l'offre appariee
    (`Prod/Bet_auto/utils/functions_bet_auto.py:418-436`) :

        matched = matched[[..., "price", "liability", "side"]]
        matched.columns = [..., "odd_layed", "stake_layed", "side"]

    `stake` porte donc la RESPONSABILITE -- ce qu'on risque -- et non la mise
    du parieur d'en face.

    LES DEUX AUTRES COLONNES MONETAIRES SONT FAUSSES POUR UN LAY, et il faut
    le dire plutot que de s'y fier : le meme robot ecrit
    `liability = stake x (cote - 1)`, une responsabilite calculee sur une
    responsabilite, et `potential_profit = stake`, qui n'est ni un profit ni un
    potentiel. Sur la position Pankin du 2026-08-12, elles annoncaient 84,31 de
    risque la ou le compte en montre 133,98.

    `data.py` n'a jamais utilise ces deux colonnes : il calcule tout depuis
    `stake` et `odds`, et il a raison depuis toujours.
    """
    return _nombre(pari.get("stake"))


def gain_net(side_back_lay, mise, cote) -> float | None:
    """Ce que ce pari RAPPORTE s'il passe, commission deduite.

    LA FORMULE EST CELLE DE `data.py`, et elle n'est pas reecrite ici -- son
    facteur de marge est LU. Deux ecritures de la meme regle divergeraient a la
    premiere correction, et celle-ci porte des euros.

        lay  ->  mise x (1 / (cote - 1)) x marge
        back ->  mise x (cote - 1)       x marge

    Layer a la cote O en risquant `mise`, c'est avoir accepte une mise de
    backer de `mise / (O - 1)` : c'est elle qu'on gagne si la selection perd.
    """
    sens = str(side_back_lay or "").strip().lower()
    if sens not in ("back", "lay"):
        return None
    m, o = _nombre(mise), _nombre(cote)
    if m is None or o is None or o <= 1:
        return None
    from config import BOOKMAKER_MARGIN_FACTOR

    return m * ((o - 1) if sens == "back" else 1 / (o - 1)) * BOOKMAKER_MARGIN_FACTOR


def mise_du_backer(pari):
    """La mise que le parieur d'en face a engagee -- ce qu'un LAY gagne.

    C'est ELLE qui entre dans le calcul de couverture : `cash_out` raisonne en
    termes d'exchange, ou un lay se decrit par la mise acceptee et non par la
    responsabilite. Passer la responsabilite rendrait un montant (cote - 1)
    fois trop petit.
    """
    sens = str(pari.get("side_back_lay") or "").strip().lower()
    m, o = _nombre(pari.get("stake")), _nombre(pari.get("odds"))
    if m is None or o is None:
        return None
    if sens != "lay":
        return m
    return None if o <= 1 else m / (o - 1)


def _colonne_de_couverture(pari, cote) -> str:
    """La colonne du prix auquel on FERME.

    Fermer un LAY, c'est BACKER : on prend le back du cote parie. Fermer un
    BACK, c'est LAYER. Se tromper de colonne -- ou de joueur -- rendrait un
    montant credible et faux.
    """
    sens = str(pari.get("side_back_lay") or "").strip().lower()
    return f"{'back' if sens == 'lay' else 'lay'}_odds_{cote}"


def positions(paris, matchs) -> dict:
    """La position du compte sur chaque match affiche.

    Rend un dictionnaire indexe par `event_id`, et n'y met QUE les matchs qui
    portent au moins un pari : une liste dense ne se remplit pas de cases
    vides.

    Les paris d'un meme cote s'ADDITIONNENT -- chaque couverture est un montant
    garanti, leur somme l'est aussi. Un match parie des DEUX cotes donne deux
    positions distinctes, qui se couvrent a deux prix differents : surtout pas
    leur somme.

    LE PRIX DE COUVERTURE SE CHOISIT PARI PAR PARI, et non une fois pour toute
    la position. Aucune selection ne porte les deux sens dans l'historique
    entier, mais prendre le sens du PREMIER pari rendrait, le jour ou cela
    arrive, un montant credible et faux. Quand les paris d'un cote ne se
    couvrent pas tous au meme prix, `cote_courante` reste vide : il n'y en a
    aucune a montrer.
    """
    par_marche: dict[str, list] = {}
    lignes = paris.to_dict("records") if hasattr(paris, "to_dict") else paris
    for pari in lignes:
        cle = str(pari.get("ID_MARKET") or "")
        if cle:
            par_marche.setdefault(cle, []).append(pari)

    out: dict[str, dict] = {}
    rangees = matchs.to_dict("records") if hasattr(matchs, "to_dict") else matchs
    for match in rangees:
        lot = par_marche.get(str(match.get("id_market") or ""))
        if not lot:
            continue
        fini = str(match.get("status") or "").lower() in STATUTS_FINIS
        groupes: dict[str, list] = {"a": [], "b": []}
        non_rattaches = []
        for pari in lot:
            cote = cote_du_pari(pari.get("bet_libelle"),
                                match.get("participant1"),
                                match.get("participant2"))
            (groupes[cote] if cote else non_rattaches).append(pari)

        resultat = {"a": None, "b": None, "non_rattaches": non_rattaches}
        for cote, lot_cote in groupes.items():
            if not lot_cote:
                continue
            engage = sum(risque(p) or 0.0 for p in lot_cote)
            resultat[cote] = {
                "n": len(lot_cote),
                # LE RISQUE EST `stake`, pour les deux sens -- voir `risque()`.
                # Les colonnes `liability` et `potential_profit` de la base
                # sont fausses pour un lay et ne sont plus lues.
                "mise": engage,
                "gain": sum(gain_net(p.get("side_back_lay"), risque(p),
                                     _nombre(p.get("odds"))) or 0.0
                            for p in lot_cote),
                # Ponderee par le RISQUE : c'est lui qu'on engage, donc lui qui
                # dit combien chaque cote pese dans la moyenne.
                "cote_moyenne": (
                    sum((_nombre(p.get("odds")) or 0.0) * (risque(p) or 0.0)
                        for p in lot_cote) / engage if engage else None),
                "cote_courante": None,
                "cash_out": None,
                "paris": lot_cote,
            }
            if fini:
                continue
            colonnes = {_colonne_de_couverture(p, cote) for p in lot_cote}
            prix = [_nombre(match.get(_colonne_de_couverture(p, cote)))
                    for p in lot_cote]
            if len(colonnes) == 1:
                resultat[cote]["cote_courante"] = prix[0]
            # BRUT d'abord, prelevement ENSUITE : la commission se prend une
            # fois sur le NET du marche, pas sur chaque jambe. Une position
            # batie en plusieurs fois a des jambes des deux signes, et la
            # prelever jambe par jambe la ferait mordre sur les gagnantes sans
            # que les perdantes la reduisent -- six pour cent de trop, mesure.
            # LA MISE DU BACKER, et non la responsabilite : `cash_out`
            # raisonne en termes d'exchange, ou un lay se decrit par la mise
            # acceptee. Lui passer la responsabilite rendrait un montant
            # (cote - 1) fois trop petit.
            montants = [cash_out(p.get("side_back_lay"), mise_du_backer(p),
                                 _nombre(p.get("odds")), courant,
                                 avec_commission=False)
                        for p, courant in zip(lot_cote, prix)]
            # Un seul prix manquant et la somme serait fausse d'un pari entier :
            # on ne montre alors AUCUN chiffre plutot qu'un chiffre partiel.
            if montants and all(m is not None for m in montants):
                net = sum(montants)
                resultat[cote]["cash_out"] = (
                    net * (1 - COMMISSION_ORBITX) if net > 0 else net)
        out[str(match.get("event_id") or "")] = resultat
    return out
