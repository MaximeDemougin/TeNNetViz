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
from live_data import (
    charger_bilan_qa,
    charger_matchs,
    charger_matchs_passes,
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


def identifiants_du_match(df, ligne) -> str:
    """TOUS les ``event_id`` de la MEME rencontre, separes par des virgules.

    La source attribue parfois deux identifiants a un seul match -- 2 cas
    sur 1 153 au prelevement du 2026-08-07 -- et ``match_id`` les reunit.
    N'en ouvrir qu'un rendrait la moitie du point par point sans le dire :
    3799286 en porte 2 quand 3802032 en porte 105, pour la meme rencontre.
    ``charger_points`` et ``charger_serie`` savent tous deux lire une liste.
    """
    propre = str(ligne.get("event_id"))
    cle = ligne.get("match_id")
    if _absente(cle) or df is None or "match_id" not in df.columns:
        return propre
    memes = df[df["match_id"].astype(str) == str(cle)]
    vus = []
    for identifiant in memes["event_id"].dropna():
        if str(identifiant) not in vus:
            vus.append(str(identifiant))
    return ",".join(vus) if vus else propre


def tableau_liste(df) -> pd.DataFrame:
    """La liste mise en forme : une ligne par (journee, identifiant).

    Ce n'est PAS une ligne par match -- un match a cheval sur deux journees
    en produit deux, et la source attribue parfois deux identifiants a une
    meme rencontre. Le dire ici plutot que de laisser croire que 1 153
    lignes font 1 153 matchs.
    """
    if df is None or df.empty:
        return pd.DataFrame()
    marques = apparies(df)
    return pd.DataFrame({
        "Jour": [_texte(l, "day", "—") for _, l in df.iterrows()],
        "Début": [_heure(l.get("start_ts")) for _, l in df.iterrows()],
        "Match": [f"{_texte(l, 'participant1', '?')} vs "
                  f"{_texte(l, 'participant2', '?')}" for _, l in df.iterrows()],
        "Circuit": [_texte(l, "tour_type", "—") for _, l in df.iterrows()],
        "Ligue": [_texte(l, "league", "—") for _, l in df.iterrows()],
        "Apparié": ["oui" if a else "non" for a in marques],
        "Identifiants": [identifiants_du_match(df, l) for _, l in df.iterrows()],
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

    etiquettes = {}
    for _, ligne in choisis.iterrows():
        etiquettes.setdefault(identifiants_du_match(choisis, ligne),
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


event_id = st.query_params.get("event_id")

niveau_1()

if event_id:
    st.divider()
    st.subheader("Le match choisi")
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
            st.warning("Ce match n'est plus publie.")
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
