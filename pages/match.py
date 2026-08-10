"""Page « Match » : le bilan de la collecte, les matchs passes, le detail.

DEUX NIVEAUX sur un seul ecran (design du 2026-08-07, §5) :

- en haut, la FLOTTE -- le bilan quotidien de la collecte (`bilan_collecte`,
  qui n'etait appele par aucune page) puis la liste filtrable des matchs
  deja joues (`live_matches`) ;
- en dessous, LE MATCH CHOISI -- le rendu de `detail_match`, partage avec la
  page « En direct ». On y arrive en choisissant dans la liste, et le choix
  vit dans `st.query_params` : c'est ce qui rend un match partageable par
  son URL, et ce qui permet d'y arriver depuis ailleurs.

DEUX TAUX D'APPARIEMENT circulent ici et ne comptent pas la meme chose (§4
du design) : celui du bilan porte sur les MARCHES vus en jeu, hors
appariements ambigus (65,3 % le 2026-08-06) ; celui de la liste porte sur
les MATCHS identifies, exchange ou pas (416 sur 1 153 au prelevement). Les
deux sont justes, ils repondent a deux questions differentes, et chacun
s'affiche avec son denominateur. Les melanger produirait un chiffre que
personne ne pourrait rattraper.

Le graphique superpose SIX series en cotes -- back et lay des deux joueurs,
plus le consensus bookmaker des deux cotes. Tout est en cotes, donc sur une
echelle commune : c'est ce qu'on paie reellement.
"""

import time

import pandas as pd
import streamlit as st

from bilan_collecte import afficher as afficher_bilan
from detail_match import afficher
from flux_continu import CSS_FLUX
from live_data import (
    charger_bilan_qa,
    charger_matchs,
    charger_matchs_passes,
    charger_points,
    charger_serie,
)

st.set_page_config(layout="wide")

if not st.session_state.get("logged_in", False):
    st.write("Connectez-vous pour voir les matchs et le bilan de collecte.")
    st.stop()

#: Le meme message partout : une base injoignable (reseau, identifiants,
#: table absente...) rend un texte lisible, JAMAIS une trace Python.
BASE_INJOIGNABLE = "Base de donnees injoignable. Reessayez plus tard."

#: Les trois etats du filtre d'appariement. « Tous » d'abord : un filtre
#: pose par defaut cacherait des lignes sans que personne l'ait demande.
TOUS, APPARIES, NON_APPARIES = "Tous", "Appariés", "Non appariés"

#: Couverture MESUREE de `live_series` le 2026-08-07 : 45 179 lignes entre
#: le 04-08 a 13:50 et le 07-08 a 09:04, quand `live_points` en porte dix
#: jours. Valeur d'AFFICHAGE seulement -- rien ici ne la compare a une
#: date : c'est l'absence REELLE de serie qui declenche le message, jamais
#: ce nombre. La retention n'est pas un reglage, elle resulte de la purge
#: cote PoC : ce nombre derivera, et le texte le donne pour ce qu'il est,
#: un ordre de grandeur.
COUVERTURE_SERIES = "environ 2,6 jours"

#: Ce que la page dit quand la courbe manque PARCE QUE la serie n'a pas ete
#: gardee -- plutot qu'un graphique vide, qui se lirait comme une panne.
#:
#: Ce n'est PAS une perte de donnee mais une limite d'ACCES : les cotes de
#: ces matchs existent toujours dans les fichiers bruts du collecteur, et
#: c'est cette page qui ne peut pas les lire -- elle ne voit que la base.
#: Le dire de travers dans l'autre sens (« les cotes anciennes sont
#: perdues ») ferait rouvrir un chantier qui n'a pas lieu d'etre, et
#: laisserait croire a une contrainte sur la modelisation, qui travaille
#: sur les fichiers bruts et n'est pas concernee.
COTES_NON_CONSERVEES = (
    "Pas de cotes conservées pour ce match : `live_series` ne remonte qu'à "
    f"{COUVERTURE_SERIES} en base, et ce match est plus ancien. Ce n'est "
    "pas une perte — les cotes brutes de cette rencontre existent toujours "
    "du côté du collecteur, dans des fichiers que cette page n'a pas moyen "
    "de lire : elle ne voit que la base. Le point par point, lui, remonte à "
    "dix jours et reste affiché dans son onglet."
)


# ── Ce qui s'affiche sans jamais ecrire « nan » ───────────────────────
#
# NaN est VRAI au sens booleen (``bool(float("nan")) is True``), donc
# ``valeur or defaut`` laisse passer le flottant que pandas rend pour un
# NULL SQL et ``str`` l'ecrit litteralement « nan » a l'ecran -- pas une
# absence, un texte errone. ``pd.isna`` traite None, NaN et NaT comme
# absents, ce que le booleen ne fait pas.


def _absente(valeur) -> bool:
    return valeur is None or pd.isna(valeur)


def _texte(ligne, cle: str, defaut: str = "—") -> str:
    valeur = ligne.get(cle)
    return defaut if _absente(valeur) else str(valeur)


def _champ(m, cle: str, defaut: str) -> str:
    """Lit un champ d'affichage sans jamais rendre le texte "nan"."""
    valeur = m.get(cle)
    return str(valeur) if pd.notna(valeur) else defaut


def _heure(ts) -> str:
    """L'heure de debut annoncee, en UTC comme tout le reste de la base."""
    if _absente(ts):
        return "—"
    try:
        return pd.to_datetime(float(ts), unit="s").strftime("%H:%M")
    except (TypeError, ValueError, OverflowError):
        return "—"


def _etiquette_passe(ligne) -> str:
    """« 2026-08-06 · P1 vs P2 — Ligue », le libelle du selecteur.

    Le JOUR et la LIGUE en font partie : deux rencontres des memes joueurs a
    deux dates -- ou le meme match a cheval sur deux journees -- seraient
    sinon indiscernables dans la liste deroulante.
    """
    joueurs = f"{_texte(ligne, 'participant1', '?')} vs " \
              f"{_texte(ligne, 'participant2', '?')}"
    texte = f"{_texte(ligne, 'day', '')} · {joueurs}".strip(" ·")
    ligue = _texte(ligne, "league", "")
    return f"{texte} — {ligue}" if ligue != "—" and ligue else texte


# ── Les filtres : TIRES DES DONNEES, jamais ecrits ici ────────────────


def valeurs_de_filtre(df, colonne: str, decroissant: bool = False) -> list:
    """Les valeurs distinctes d'une colonne, en texte et triees.

    Ecrire les choix dans le code (``["atp", "wta"]``) serait faux le jour
    ou un troisieme circuit apparait -- et personne ne le verrait : la page
    continuerait a n'offrir que ce qu'elle connaissait deja, et les lignes
    du nouveau circuit seraient invisibles a tout filtre. Les tirer des
    donnees fait apparaitre la nouvelle valeur toute seule.

    Les absences sont RETIREES avant la conversion en texte, pas apres :
    l'ordre inverse fabriquerait la chaine "nan" comme valeur de filtre.
    """
    if df is None or df.empty or colonne not in df.columns:
        return []
    return sorted({str(v) for v in df[colonne].dropna()}, reverse=decroissant)


def apparies(df) -> pd.Series:
    """Vrai, ligne a ligne, pour les matchs apparies a un marche.

    ``matched`` est le 0/1 ecrit par le PoC. Une valeur ABSENTE compte comme
    « non apparie » : une absence n'est pas un appariement, et la compter
    comme tel gonflerait le taux affiche juste en dessous.
    """
    if df is None or df.empty or "matched" not in df.columns:
        return pd.Series(False, index=getattr(df, "index", None))
    return pd.to_numeric(df["matched"], errors="coerce").fillna(0) == 1


def filtrer(df, jours, circuits, ligues, appariement) -> pd.DataFrame:
    """La liste reduite aux lignes retenues.

    Un filtre VIDE ne filtre rien : c'est l'etat de depart, et il doit
    montrer tout ce qui existe. Un filtre par defaut qui cacherait des
    lignes ferait croire a une collecte plus pauvre qu'elle n'est.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    garde = pd.Series(True, index=df.index)
    for colonne, choisies in (("day", jours), ("tour_type", circuits),
                              ("league", ligues)):
        if choisies and colonne in df.columns:
            garde &= df[colonne].astype(str).isin(list(choisies))
    if appariement == APPARIES:
        garde &= apparies(df)
    elif appariement == NON_APPARIES:
        garde &= ~apparies(df)
    return df[garde]


def identifiants_par_match(df) -> dict:
    """``match_id`` -> tous ses ``event_id``, dans l'ordre de la table.

    Calcule UNE fois pour toute la liste : refaire le rapprochement ligne a
    ligne couterait un balayage complet par ligne, soit 1 153 balayages de
    1 153 lignes a chaque rendu de la page.
    """
    groupes = {}
    if df is None or df.empty or "match_id" not in df.columns:
        return groupes
    for cle, identifiant in zip(df["match_id"], df["event_id"]):
        if _absente(cle) or _absente(identifiant):
            continue
        vus = groupes.setdefault(str(cle), [])
        if str(identifiant) not in vus:
            vus.append(str(identifiant))
    return groupes


def identifiants_du_match(groupes, ligne) -> str:
    """TOUS les ``event_id`` de la MEME rencontre, separes par des virgules.

    La source attribue parfois deux identifiants a un seul match -- 2 cas
    sur 1 153 au prelevement du 2026-08-07 -- et ``match_id`` les reunit.
    N'en ouvrir qu'un rendrait la moitie du point par point sans le dire :
    3799286 en porte 2 quand 3802032 en porte 105, pour la meme rencontre.
    ``charger_points`` et ``charger_serie`` savent tous deux lire une liste.
    """
    propre = str(ligne.get("event_id"))
    cle = ligne.get("match_id")
    if _absente(cle):
        return propre
    return ",".join(groupes.get(str(cle), [])) or propre


#: Les deux cles temporelles de la liste, dans l'ordre de priorite. Elles
#: sont BRUTES -- `day` est une date, `start_ts` un epoch -- et non les
#: colonnes affichees : « Jour » et « Début » sont du texte mis en forme, et
#: « 09:00 » se trierait alphabetiquement, donc faux des qu'un format change.
CLES_TEMPORELLES = ("day", "start_ts")


def du_plus_recent(df) -> pd.DataFrame:
    """Le meme tableau, de la journee la plus recente a la plus ancienne.

    Le tri est FAIT ici et non herite de l'``ORDER BY`` du lecteur : celui-ci
    demande deja `day DESC, start_ts DESC`, mais un affichage qui recopie
    l'ordre de son entree se casse en silence des que la lecture change --
    un cache, un regroupement, un filtre, une autre source.

    `kind="stable"` : deux lignes de meme journee ET de meme heure gardent
    leur ordre d'arrivee plutot que d'etre permutees au hasard d'un rendu a
    l'autre. `na_position="last"` : une journee ABSENTE part en fin de
    liste -- lui donner la premiere place reviendrait a la declarer la plus
    recente sur la foi d'un trou.
    """
    cles = [c for c in CLES_TEMPORELLES if c in getattr(df, "columns", [])]
    if not cles:
        return df
    return df.sort_values(cles, ascending=False, kind="stable",
                          na_position="last")


def tableau_liste(df) -> pd.DataFrame:
    """La liste mise en forme : une ligne par (journee, identifiant), la plus
    recente EN TETE.

    Ce n'est PAS une ligne par match -- un match a cheval sur deux journees
    en produit deux, et la source attribue parfois deux identifiants a une
    meme rencontre. Le dire ici plutot que de laisser croire que 1 153
    lignes font 1 153 matchs.

    Le tri passe AVANT `apparies()` : cette colonne-la se calcule sur une
    Serie a part, et la trier apres la decalerait d'un cran -- le match non
    apparie s'afficherait comme apparie.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    df = du_plus_recent(df)
    marques = apparies(df)
    groupes = identifiants_par_match(df)
    return pd.DataFrame({
        "Jour": [_texte(l, "day", "—") for _, l in df.iterrows()],
        "Début": [_heure(l.get("start_ts")) for _, l in df.iterrows()],
        "Match": [f"{_texte(l, 'participant1', '?')} vs "
                  f"{_texte(l, 'participant2', '?')}" for _, l in df.iterrows()],
        "Circuit": [_texte(l, "tour_type", "—") for _, l in df.iterrows()],
        "Ligue": [_texte(l, "league", "—") for _, l in df.iterrows()],
        "Apparié": ["oui" if a else "non" for a in marques],
        "Identifiants": [identifiants_du_match(groupes, l)
                         for _, l in df.iterrows()],
    })


def texte_appariement(df) -> str:
    """Le taux d'appariement DE LA LISTE, avec SON denominateur.

    Il porte sur les matchs IDENTIFIES -- tous, y compris ceux que
    l'exchange n'a jamais eus en direct. Le bilan, lui, compte les marches
    vus en jeu hors ambigus : deux denominateurs, deux questions, et deux
    valeurs qui ne se remplacent pas (§4 du design). Le texte nomme la
    difference, sans quoi deux chiffres differents sur le meme ecran se
    liraient comme une incoherence.
    """
    total = 0 if df is None else len(df)
    if not total:
        return ""
    nombre = int(apparies(df).sum())
    part = f"{nombre / total * 100:.1f} %".replace(".", ",")
    return (
        f"{nombre} sur {total} matchs identifiés sont appariés à un marché "
        f"de l'exchange ({part}). Ce taux n'est pas celui du bilan ci-dessus : "
        "le bilan compte les marchés vus en jeu, hors appariements ambigus ; "
        "celui-ci compte les matchs identifiés, exchange ou pas."
    )


# ── Niveau 1 : le bilan, puis la liste ────────────────────────────────


def niveau_1() -> None:
    """Le bilan de collecte, puis la liste filtrable des matchs joues."""
    st.title("Matchs")

    try:
        bilan = charger_bilan_qa()
    except Exception:
        st.error(BASE_INJOIGNABLE)
    else:
        afficher_bilan(bilan)

    st.subheader("Les matchs collectés")
    try:
        passes = charger_matchs_passes()
    except Exception:
        st.error(BASE_INJOIGNABLE)
        return
    if passes.empty:
        st.info(
            "Aucun match collecté pour l'instant. `live_matches` est écrite "
            "par le PoC de collecte ; si elle reste vide, c'est lui qu'il "
            "faut aller voir."
        )
        return

    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    jours = c1.multiselect(
        "Jour", valeurs_de_filtre(passes, "day", decroissant=True),
        key="filtre_jour",
        help="Le jour de COLLECTE, pas celui du tournoi : un match à cheval "
             "sur deux journées apparaît dans les deux.",
    )
    circuits = c2.multiselect(
        "Circuit", valeurs_de_filtre(passes, "tour_type"), key="filtre_circuit",
    )
    ligues = c3.multiselect(
        "Ligue", valeurs_de_filtre(passes, "league"), key="filtre_ligue",
    )
    appariement = c4.radio(
        "Appariement", (TOUS, APPARIES, NON_APPARIES), key="filtre_appariement",
        help="Apparié = la rencontre a été rapprochée d'un marché de "
             "l'exchange. Un match non apparié a été identifié mais jamais "
             "vu en direct : ni cotes, ni marché.",
    )

    choisis = filtrer(passes, jours, circuits, ligues, appariement)
    if choisis.empty:
        st.info("Aucun match ne correspond à ces filtres.")
        return

    st.dataframe(tableau_liste(choisis), hide_index=True, width="stretch",
                 height=min(420, 40 + 35 * len(choisis)))
    st.caption(texte_appariement(choisis))

    groupes = identifiants_par_match(choisis)
    etiquettes = {}
    for _, ligne in choisis.iterrows():
        # Une seule entree par RENCONTRE : les deux journees d'un match a
        # cheval, comme ses deux identifiants, ouvrent la meme chose.
        etiquettes.setdefault(identifiants_du_match(groupes, ligne),
                              _etiquette_passe(ligne))
    ouvrir, _ = st.columns([3, 1])
    choix = ouvrir.selectbox(
        "Ouvrir un match", list(etiquettes),
        format_func=lambda cle: etiquettes[cle], key="choix_match_passe",
    )
    if ouvrir.button("Ouvrir", key="ouvrir_match_passe"):
        # L'URL porte le choix : un match ouvert reste partageable, et on y
        # revient par l'historique du navigateur.
        st.query_params["event_id"] = choix
        st.rerun()


# ── Niveau 2 : le match choisi ────────────────────────────────────────


def _demandes(event_id) -> set:
    """Les identifiants demandes par l'URL, qui peut en porter plusieurs."""
    return {e.strip() for e in str(event_id).split(",") if e.strip()}


def ligne_du_direct(matchs, demandes):
    """La ligne de ``live_now`` qui porte l'un des identifiants, ou None.

    APPARTENANCE au groupe, pas egalite : `charger_matchs` a fusionne les
    identifiants multiples d'une meme rencontre en une ligne portant
    ``event_ids``, et une URL portant l'identifiant secondaire ne
    retrouverait plus son match avec une simple egalite.
    """
    if matchs is None or matchs.empty:
        return None
    colonne = "event_ids" if "event_ids" in matchs.columns else "event_id"
    if colonne not in matchs.columns:
        return None
    appartient = matchs[colonne].map(
        lambda ids: bool(demandes & {i.strip() for i in str(ids).split(",")})
    )
    trouvees = matchs[appartient]
    return None if trouvees.empty else trouvees.iloc[0]


def match_archive(rangee, points) -> pd.Series:
    """La ligne d'affichage d'un match qui n'est plus publie.

    ``live_matches`` ne porte NI score NI statut : le dernier releve de
    ``live_points`` donne le premier. Le statut, lui, n'est PAS repris tel
    quel -- le dernier point du match Duckworth (3 aout, 6-3 6-1, donc fini)
    dit encore « InPlay » parce que la collecte s'est arretee la sans jamais
    recevoir de trame de cloture. L'afficher ferait passer une rencontre
    vieille de quatre jours pour un match en cours.
    """
    ligne = dict(rangee) if rangee is not None else {}
    dernier = None if points is None or points.empty else points.iloc[-1]
    ligne["score"] = None if dernier is None else dernier.get("score")
    ligne["points"] = None if dernier is None else dernier.get("points")
    # Le serveur ne se DEDUIT pas ici : `live_points.indicator` n'est pas le
    # serveur, et le champ serveur de la source se contredit dans 13 % des
    # jeux. Rien plutot qu'une balle posee du mauvais cote.
    ligne["server"] = None
    ligne["status"] = "archivé"
    return pd.Series(ligne)


def rencontre_appariee(rangees) -> bool:
    """La rencontre a-t-elle ete rapprochee d'un marche, sur N'IMPORTE
    laquelle de ses lignes ?

    Une rencontre a plusieurs lignes dans ``live_matches`` -- une par
    journee, et une par identifiant quand la source en a emis deux -- et
    elles ne s'accordent PAS toujours : 3799286 n'est pas apparie quand
    3802032, la meme rencontre, l'est, et c'est sous l'apparie que les cotes
    ont ete ecrites. Juger sur la premiere ligne venue ferait dependre le
    motif affiche de l'ordre de la requete, donc du hasard.

    La reponse decide du MOTIF affiche a la place de la courbe, et se
    tromper de motif est pire que de n'en donner aucun : ca envoie chercher
    au mauvais endroit.
    """
    if rangees is None or len(rangees) == 0:
        return False
    return bool(apparies(rangees).any())


def motif_absence_de_cotes(rangees, serie) -> str | None:
    """Pourquoi il n'y a pas de courbe -- ou None si `detail_match` sait.

    DEUX absences differentes, et les confondre serait mentir :

    - la serie existe (meme sans une seule cote d'exchange : un match jamais
      apparie garde des releves de score), ou la rencontre n'a jamais eu de
      marche -> « pas de marche apparie », le motif que `detail_match` donne
      deja tout seul, et c'est le bon ;
    - la serie est VIDE alors que la rencontre ETAIT appariee -> ce n'est
      pas le marche qui manque, c'est la retention. Laisser le premier motif
      s'afficher accuserait la collecte d'un trou qu'elle n'a pas.
    """
    if serie is not None and not serie.empty:
        return None
    return COTES_NON_CONSERVEES if rencontre_appariee(rangees) else None


def detail_archive(event_id, maintenant: float) -> None:
    """Le detail d'un match qui n'est plus publie, relu dans les tables du
    passe.

    Les cotes vivent ~2,6 jours dans `live_series`, le point par point dix
    jours dans `live_points` : au-dela, le match garde son deroulement et
    perd sa courbe. La page le DIT -- une absence silencieuse se lit comme
    une panne -- et le point par point reste affiche, puisqu'il est la.
    """
    try:
        passes = charger_matchs_passes()
        points = charger_points(event_id)
        serie = charger_serie(event_id)
    except Exception:
        st.error(BASE_INJOIGNABLE)
        return

    demandes = _demandes(event_id)
    trouvees = pd.DataFrame()
    rangee = None
    if not passes.empty and "event_id" in passes.columns:
        trouvees = passes[passes["event_id"].astype(str).isin(demandes)]
        if not trouvees.empty:
            # La ligne la plus RECENTE porte l'identite a afficher : un match
            # a cheval sur deux journees en a deux, et c'est la derniere qui
            # dit quand il s'est vraiment joue.
            if "day" in trouvees.columns:
                trouvees = trouvees.sort_values("day", kind="stable")
            rangee = trouvees.iloc[-1]
    if rangee is None and (points is None or points.empty):
        st.warning(
            "Ce match n'est plus publié, et la collecte n'en a rien gardé : "
            "ni ligne dans `live_matches`, ni point par point."
        )
        return

    m = match_archive(rangee, points)
    st.caption(
        f"Match archivé — {_texte(m, 'day', 'journée inconnue')}, "
        f"{0 if points is None else len(points)} relevés de point par point. "
        "Les pastilles de fraîcheur restent blanches : la collecte de ce "
        "match est terminée, il n'y a plus de flux dont mesurer l'âge."
    )
    # La serie porte les cotes ET l'etat de jeu ; les points ne portent que
    # l'etat de jeu, mais dix jours en arriere. On affiche donc la serie
    # quand elle existe et les points quand elle a disparu -- jamais rien,
    # et jamais un graphique vide.
    if serie is not None and not serie.empty:
        deroulement = serie
    else:
        deroulement = (
            pd.DataFrame() if points is None or points.empty
            else points.rename(columns={"recv_ts": "ts"})
        )
    afficher(m, deroulement, maintenant,
             absence_cotes=motif_absence_de_cotes(trouvees, serie))


event_id = st.query_params.get("event_id")

niveau_1()

if event_id:
    st.divider()
    st.subheader("Le match choisi")
    # CSS_FLUX seulement ICI, autour du detail auto-rafraichi -- jamais sur
    # `niveau_1()`. Ce niveau-la interroge des tables lentes
    # (`charger_matchs_passes`, `charger_points`, `charger_bilan_qa`) sans
    # fragment ni cadence : eteindre le grisement dessus ferait passer une
    # requete lente pour une page figee, et la feuille masque aussi l'homme
    # qui court, qui EST le bouton Stop -- le seul moyen d'interrompre un
    # cycle bloque. Ce n'est que le rafraichissement AUTOMATIQUE du fragment
    # ci-dessous qui devait se faire discret, pas le clic dans l'archive.
    st.markdown(CSS_FLUX, unsafe_allow_html=True)
    if st.button("Fermer le détail", key="fermer_detail"):
        del st.query_params["event_id"]
        st.rerun()

    CADENCES = {"5 s": 5, "15 s": 15, "60 s": 60, "Manuel": None}
    cadence = st.sidebar.selectbox(
        "Rafraichissement", list(CADENCES), index=1, key="cadence_match"
    )
    periode = CADENCES[cadence]

    @st.fragment(run_every=periode)
    def zone_donnees():
        """Le detail, rafraichi tout seul tant qu'il vit dans le direct."""
        maintenant = time.time()
        try:
            matchs = charger_matchs()
        except Exception:
            st.error(BASE_INJOIGNABLE)
            return

        m = ligne_du_direct(matchs, _demandes(event_id))
        if m is None:
            # Plus dans `live_now` : le match est termine et retire (six
            # heures) ou bien plus ancien. Les tables du passe, elles,
            # l'ont encore -- c'est tout l'objet de cette page.
            detail_archive(event_id, maintenant)
            return

        try:
            # TOUS les identifiants du match : la serie est repartie entre
            # eux quand la source en a emis plusieurs.
            serie = charger_serie(_champ(m, "event_ids", "") or event_id)
        except Exception:
            st.error(BASE_INJOIGNABLE)
            return

        # Le rendu vit dans `detail_match`, PARTAGE avec la page « En
        # direct » qui l'affiche sous sa liste. L'ecrire deux fois
        # garantirait qu'une correction n'atterrisse que d'un cote -- un
        # ecart qui ne se voit qu'a l'usage, longtemps apres.
        afficher(m, serie, maintenant)

    zone_donnees()
