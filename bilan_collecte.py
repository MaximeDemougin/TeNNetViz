"""Le bilan de collecte : trois alarmes qui sonnaient en silence.

`Live/qa_report.py` calcule chaque nuit trois indicateurs de sante de la
collecte et les ecrit dans `TeNNet_test.live_qa_daily` depuis le
2026-07-28. Les seuils, eux, vivent dans `Live/config.py`. Les trois sont
franchis TOUS LES JOURS depuis dix jours -- et rien, nulle part, ne les
affichait. Ce module ne decore pas : il rend visible ce qui sonnait sans
bruit.

Il ne CALCULE aucun indicateur (§7 du design) : les recalculer ici creerait
deux verites qui divergeraient. Il ne fait AUCUNE lecture de base non plus,
comme `detail_match` -- on lui passe le bilan deja lu, et c'est l'appelant
qui decide quand lire et qui protege cette lecture.

Les deux pieges d'affichage que ce module existe pour eviter :

- **Le denominateur nul.** Quatre journees (28 au 31 juillet 2026) n'ont vu
  aucun marche in-play : leur taux d'appariement est ABSENT, pas nul. Il se
  lit « pas de mesure », jamais « 0 % ». Quatre journees peintes en rouge
  pour n'avoir rien eu a mesurer noieraient l'information vraie des six
  autres, et apprendraient au lecteur a ignorer le rouge.
- **Le sens du seuil.** Deux MINIMA et un MAXIMUM. Il est porte par
  `INDICATEURS_QA` cote `live_data`, jusqu'a la COULEUR du delta :
  `delta_color="inverse"` pour un maximum, sans quoi la baisse du taux de
  trou entre le 3 et le 4 aout -- le seul vrai gain de ces dix jours, la
  fenetre exacte de la correction d'authentification -- s'afficherait en
  rouge.
"""

import pandas as pd
import streamlit as st

from live_data import (
    CONFORME,
    HORS_SEUIL,
    INDICATEURS_QA,
    SANS_MESURE,
    bilan_juge,
)

#: Memes pastilles que les flux de la page « En direct »
#: (`detail_match.PASTILLE`) : un vert, un rouge, un blanc pour « je ne
#: sais pas ». Le blanc n'est pas un demi-rouge -- c'est l'absence de
#: mesure, et elle a sa couleur a elle.
PASTILLE_QA = {CONFORME: "🟢", HORS_SEUIL: "🔴", SANS_MESURE: "⚪"}

#: Les mots, exactement. « — » (le tiret utilise ailleurs pour un champ
#: vide) se lirait comme « rien » ; ici il faut lire « on n'a pas mesure ».
SANS_MESURE_TEXTE = "pas de mesure"


def _absente(valeur) -> bool:
    """NULL relu depuis MySQL arrive en NaN flottant, pas en None -- et NaN
    est VRAI au sens booleen, donc `valeur or defaut` le laisserait passer
    et afficherait litteralement « nan ». Meme piege que partout ailleurs
    dans ce depot."""
    return valeur is None or pd.isna(valeur)


def _pourcentage(valeur) -> str:
    """Un taux en pourcentage a une decimale, ou l'aveu qu'il n'y en a pas.

    La virgule decimale plutot que le point : c'est un affichage francais,
    et 65.3 se lit mal a cote de 65,3.
    """
    if _absente(valeur):
        return SANS_MESURE_TEXTE
    return f"{float(valeur) * 100:.1f} %".replace(".", ",")


def _entier(valeur) -> str:
    """Un compte, ou l'aveu qu'il n'a pas ete fait.

    `n_inversions` vaut NULL sur neuf des dix journees et 0 sur la dixieme.
    Rendre les NULL par « 0 » annoncerait « aucune inversion detectee » dix
    jours de suite alors que le controle n'a tourne qu'une fois -- un
    succes silencieux, exactement ce que `_sum_or_missing` refuse cote PoC.
    Le zero du 28 juillet, lui, est une vraie mesure et reste.
    """
    if _absente(valeur):
        return SANS_MESURE_TEXTE
    return f"{int(valeur):,}".replace(",", " ")


def _seuil_texte(spec) -> str:
    """« au moins 90 % » ou « au plus 5 % » -- le sens, en toutes lettres.

    C'est la seule forme du sens que le lecteur voit. Un seuil affiche sans
    sa direction ne permet pas de juger le chiffre a cote.
    """
    borne = "au moins" if spec.sens == "min" else "au plus"
    return f"{borne} {spec.seuil * 100:.0f} %"


def _entete(indicateur: str) -> str:
    """Le libelle d'une colonne : l'indicateur, SON denominateur, SON seuil.

    Deux taux d'appariement circulent dans cette page et ne comptent pas la
    meme chose (§4 du design) : 65,3 % sur les marches vus en jeu (hors
    ambigus), 36 % sur tous les matchs identifies. Sans son denominateur,
    un pourcentage ne veut rien dire -- et les melanger produirait un
    chiffre faux que personne ne pourrait rattraper.
    """
    spec = INDICATEURS_QA[indicateur]
    return f"{spec.libelle} — {spec.denominateur} (seuil : {_seuil_texte(spec)})"


def _delta(valeurs) -> str | None:
    """L'ecart en points avec la derniere mesure precedente, ou rien.

    Rien -- et surtout pas « 0,0 pt », qui se lirait comme une stabilite
    CONSTATEE -- dans deux cas : la derniere journee n'est pas mesuree
    (comparer une absence a une mesure ne dit rien), ou il n'existe pas
    deux mesures a comparer.

    Les journees sans mesure sont SAUTEES, pas comptees comme des zeros :
    le 1er aout se compare a la derniere journee mesuree, pas au 31 juillet
    qui n'a rien mesure.

    La COULEUR de cet ecart n'est pas decidee ici mais par
    `delta_color` (voir `afficher`), et c'est la que le sens du seuil
    s'applique.
    """
    valeurs = list(valeurs)
    if not valeurs or _absente(valeurs[-1]):
        return None
    mesurees = [float(v) for v in valeurs if not _absente(v)]
    if len(mesurees) < 2:
        return None
    ecart = (mesurees[-1] - mesurees[-2]) * 100
    if ecart == 0:
        return "0,0 pt"
    return f"{ecart:+.1f} pt".replace(".", ",")


def tableau_bilan(bilan: pd.DataFrame) -> pd.DataFrame:
    """Le bilan mis en forme, une ligne par journee, dans l'ordre du temps.

    Chronologique et non l'inverse : c'est le sens dans lequel une tendance
    se lit, et c'est la tendance que ce tableau porte -- le taux de trou
    tombe de 97 % a 51 % entre le 3 et le 5 aout.

    Chaque taux part avec sa pastille de verdict : le chiffre seul ne dit
    pas s'il est bon, et le seuil est dans l'en-tete de la colonne.
    """
    if bilan is None or bilan.empty:
        return pd.DataFrame()
    juge = bilan_juge(bilan)
    sortie = pd.DataFrame()
    sortie["Jour"] = [str(j) for j in juge["day"]] if "day" in juge else ""
    sortie["Marchés vus en jeu"] = [
        _entier(v) for v in juge.get("n_markets", [None] * len(juge))
    ]
    for indicateur in INDICATEURS_QA:
        valeurs = juge.get(indicateur, [None] * len(juge))
        verdicts = juge[f"verdict_{indicateur}"]
        sortie[_entete(indicateur)] = [
            f"{PASTILLE_QA[verdict]} {_pourcentage(valeur)}"
            for valeur, verdict in zip(valeurs, verdicts)
        ]
    sortie["Inversions détectées"] = [
        _entier(v) for v in juge.get("n_inversions", [None] * len(juge))
    ]
    sortie["Appels API"] = [
        _entier(v) for v in juge.get("api_calls", [None] * len(juge))
    ]
    return sortie


def afficher(bilan: pd.DataFrame) -> None:
    """Le bilan a l'ecran : la derniere journee en tete, puis les dix.

    Ne lit rien : `bilan` est deja charge (`live_data.charger_bilan_qa`).
    Meme partage que `detail_match` -- c'est l'appelant qui decide quand
    lire et qui protege cette lecture.
    """
    st.subheader("Santé de la collecte")
    if bilan is None or bilan.empty:
        st.info(
            "Aucun bilan de collecte pour l'instant. `qa_report` l'écrit "
            "chaque nuit dans `live_qa_daily` ; s'il reste vide, c'est lui "
            "qu'il faut aller voir."
        )
        return

    juge = bilan_juge(bilan)
    dernier = juge.iloc[-1]
    jour = dernier["day"] if "day" in juge.columns else "la dernière journée"

    colonnes = st.columns(len(INDICATEURS_QA))
    for colonne, (nom, spec) in zip(colonnes, INDICATEURS_QA.items()):
        verdict = dernier[f"verdict_{nom}"]
        valeurs = juge[nom] if nom in juge.columns else [None] * len(juge)
        with colonne:
            st.metric(
                f"{PASTILLE_QA[verdict]} {spec.libelle}",
                _pourcentage(dernier.get(nom)),
                delta=_delta(valeurs),
                # LE SENS, jusqu'a la couleur. Sur un MAXIMUM, une baisse
                # est un gain : sans « inverse », la chute du taux de trou
                # du 3 au 4 aout -- la correction d'authentification --
                # s'afficherait en rouge, et la page annoncerait une panne
                # le jour d'une reparation.
                delta_color="normal" if spec.sens == "min" else "inverse",
                help=f"Seuil : {_seuil_texte(spec)} {spec.denominateur}. "
                     "Écart avec la dernière journée mesurée, en points.",
            )

    hors = [
        (nom, spec) for nom, spec in INDICATEURS_QA.items()
        if dernier[f"verdict_{nom}"] == HORS_SEUIL
    ]
    if hors:
        details = "\n".join(
            f"- **{spec.libelle}** : {_pourcentage(dernier.get(nom))} "
            f"pour un seuil {_seuil_texte(spec)} {spec.denominateur}"
            for nom, spec in hors
        )
        st.error(
            f"**{len(hors)} indicateur(s) hors seuil le {jour}.** Ces seuils "
            "sont ceux du PoC de collecte (`Live/config.py`) ; les franchir "
            "ne casse rien, mais la matière collectée vaut moins que "
            f"prévu.\n\n{details}"
        )

    st.dataframe(tableau_bilan(bilan), hide_index=True, width="stretch")
    st.caption(
        "Une ligne par journée, de la plus ancienne à la plus récente. "
        "« pas de mesure » n'est pas « 0 % » : une journée sans marché vu "
        "en jeu n'a rien à mesurer."
    )
