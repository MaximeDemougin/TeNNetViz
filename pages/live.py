"""Page liste : ce qui se joue maintenant, et si la collecte capte.

La colonne de fraicheur est la raison d'etre de cette page. Le capteur de
cotes a affiche « 52 marches suivis » pendant des heures sans en alimenter un
seul, et rien nulle part ne le signalait -- il a fallu une semaine pour le
voir. Ici, ca se lit d'un coup d'oeil.

Une LIGNE par match, pas une carte : on compare ainsi les cotes verticalement
d'un match a l'autre, ce que des cartes empilees ne permettent pas. Le detail
s'ouvre en FENETRE plutot que sur une autre page -- la liste reste en place
derriere, et on passe d'un match a l'autre sans perdre le contexte ni sa
position dans la page.
"""

import time

import streamlit as st

from detail_match import afficher
from liste_dense import (
    CSS, cle_bouton, cle_carte, cle_ligne, entete_competition,
    entete_tournoi, lignes,
    mouvements_de_prix, rendu,
)
from live_data import (
    SEUIL_BATTEMENT_ARRETE_S,
    a_joue,
    capteur_score_mort,
    charger_matchs,
    charger_serie,
    ordonner_par_tournoi,
    publieur_arrete,
    publieur_ecritures_refusees,
    source_score_figee,
)

st.set_page_config(layout="wide")
st.title("En direct")

if not st.session_state.get("logged_in", False):
    st.write("Connectez-vous pour voir les matchs en direct.")
    st.stop()

CADENCES = {"5 s": 5, "15 s": 15, "60 s": 60, "Manuel": None}
choix = st.sidebar.selectbox(
    "Rafraichissement", list(CADENCES), index=1, key="cadence_live"
)
periode = CADENCES[choix]


def _dessiner(structure, ouvert: str, prefixe: str) -> None:
    """Un tournoi par CARTE, un match par ligne cliquable.

    La carte n'est pas une decoration : elle reprend la surface arrondie et
    surelevee du reste de l'application, et elle borne visuellement un
    tournoi -- ce qu'un simple titre suivi de lignes ne faisait pas des que
    la liste s'allongeait.

    Le clic est porte par un bouton Streamlit a part -- il ne peut pas vivre
    DANS le HTML -- mais il ne recharge pas la page, donc il ne deconnecte
    pas. C'est tout ce que le lien ne savait pas faire. La feuille de style
    l'etale sur toute la ligne et le rend transparent : le clic porte
    partout.
    """
    groupes = []
    for ligne in structure:
        cle = (ligne["tournoi"], ligne["competition"])
        if not groupes or groupes[-1][0] != cle:
            groupes.append((cle, []))
        groupes[-1][1].append(ligne)

    competition = None
    for rang, (_cle, matchs) in enumerate(groupes):
        # Premier niveau : le circuit, annonce une fois pour tous ses
        # tournois. Le badge de l'entete de tournoi le repetait.
        if matchs[0]["competition"] != competition:
            competition = matchs[0]["competition"]
            st.markdown(entete_competition(matchs[0]), unsafe_allow_html=True)
        with st.container(border=True, gap=None, key=cle_carte(prefixe, rang)):
            st.markdown(entete_tournoi(matchs[0]), unsafe_allow_html=True)
            for ligne in matchs:
                # Un conteneur NOMME : Streamlit en derive une classe CSS,
                # seul point d'accroche pour etaler le bouton sur la ligne
                # entiere et le rendre transparent. `cle_ligne` est partagee
                # avec la feuille de style : elles ne peuvent pas diverger.
                with st.container(key=cle_ligne(prefixe, ligne["event_id"])):
                    st.markdown(
                        rendu([ligne], ouvert, entetes=False, section=prefixe),
                        unsafe_allow_html=True)
                    noms = " contre ".join(j["nom"] for j in ligne["joueurs"])
                    # Invisible a l'ecran, ce libelle reste le SEUL que lit un
                    # lecteur d'ecran : « Ouvrir » quinze fois de suite ne
                    # designerait rien.
                    if st.button(f"Ouvrir {noms}",
                                 key=cle_bouton(prefixe, ligne["event_id"])):
                        st.session_state["match_ouvert"] = ligne["event_ids"]
                        st.rerun()


def _refermer() -> None:
    """Oublier le match ouvert quand la fenetre se ferme.

    Sans cela, l'etat resterait pose : le rafraichissement automatique
    rouvrirait la fenetre quelques secondes apres qu'on l'a fermee, et elle
    deviendrait impossible a quitter.
    """
    st.session_state["match_ouvert"] = ""


@st.dialog("Detail du match", width="large", on_dismiss=_refermer)
def _fenetre(m, serie, maintenant: float) -> None:
    """Le detail en fenetre de dialogue.

    Il s'affichait sous la liste, ce qui obligeait a derouler toute la page
    pour le lire puis a remonter pour changer de match. Une fenetre garde la
    liste en place et se ferme d'un geste.
    """
    afficher(m, serie, maintenant)


@st.fragment(run_every=periode)
def zone_donnees():
    maintenant = time.time()
    try:
        matchs = charger_matchs()
    except Exception:
        # Base injoignable (réseau, identifiants, table absente...) : un
        # message explicite, jamais la trace Python brute à l'écran.
        st.error("Base de donnees injoignable. Reessayez plus tard.")
        return

    en_cours = matchs[matchs["en_cours"]] if "en_cours" in matchs.columns else matchs
    # Seuls les matchs COMMENCÉS : un match annoncé mais pas débuté encombre
    # la liste sans rien apprendre -- ni score, ni points, ni cotes qui bougent.
    if {"score", "points"} <= set(en_cours.columns):
        en_cours = en_cours[[
            a_joue(sc, pt) for sc, pt in zip(en_cours["score"], en_cours["points"])
        ]]
    # Une heure INCONNUE va en fin de liste : sans cela, un match dont on
    # ignore l'heure occuperait la première ligne sur la foi d'une absence.
    en_cours = ordonner_par_tournoi(en_cours)

    # Le signal de vie AVANT tout retour anticipé, y compris quand la table est
    # vide : une table vide ne prouve RIEN sur la santé du publieur, et ce
    # retour prématuré a déjà rendu le signal inatteignable une fois.
    if publieur_arrete(en_cours):
        st.error(
            "Le publieur temps reel semble arrete : aucun signe de vie "
            f"depuis plus de {SEUIL_BATTEMENT_ARRETE_S:.0f} s. Les pastilles "
            "des flux normalement actifs vont virer au rouge ; celles deja "
            "blanches (flux jamais recus pour ce match) le restent."
        )
    elif publieur_ecritures_refusees(en_cours):
        st.error(
            "Le publieur temps reel est VIVANT (signe de vie recent) mais "
            "ses ecritures vers la base semblent refusees : les matchs en "
            "cours peuvent rester affiches sans se mettre a jour. Ce n'est "
            "pas le publieur qu'il faut redemarrer -- verifiez sa connexion "
            "a la base (identifiants, reseau)."
        )
    elif source_score_figee():
        st.warning(
            "La source de score REPOND mais ne bouge plus : elle sert son "
            "cache. Le publieur s'en apercoit et refuse de declarer les "
            "matchs termines -- sans cela la liste se viderait toute seule "
            "en pleine soiree. Les scores affiches restent ceux du dernier "
            "etat recu ; la pastille « score » vire au rouge en attendant "
            "que la source reparte."
        )
    elif capteur_score_mort(en_cours):
        st.error(
            "Le capteur de score semble arrete (le publieur, lui, repond "
            "toujours) : plus aucun signe de vie -- fichier de battement "
            f"absent (arret propre) ou perime depuis plus de "
            f"{SEUIL_BATTEMENT_ARRETE_S:.0f} s. Les matchs en cours peuvent "
            "rester affiches sans se mettre a jour tant que ce capteur ne "
            "reprend pas -- ce n'est pas le publieur qu'il faut redemarrer."
        )

    if matchs.empty:
        st.info("Aucun match publie. Le publieur tourne-t-il ?")
        return
    if en_cours.empty:
        # Un MESSAGE, pas un retour : les matchs termines restent consultables
        # six heures, et c'est la qu'on relit un match apres coup. Ce retour
        # anticipe rendait la page entierement vide des le dernier match fini
        # -- l'etat normal une bonne partie de la journee -- et faisait
        # disparaitre la fenetre de detail qu'on etait en train de lire.
        st.info("Aucun match en cours.")

    # Le match ouvert vit dans la SESSION et non dans l'URL : un lien
    # <a href="?..."> rechargeait la page, ce qui cree une nouvelle session
    # Streamlit -- et comme l'authentification de cette application ne vit
    # que dans session_state (le cookie est commente dans pages/login.py),
    # le rechargement DECONNECTAIT. Constate a l'usage.
    ouvert = str(st.session_state.get("match_ouvert") or "")
    st.markdown(CSS, unsafe_allow_html=True)
    if not en_cours.empty:
        st.caption(
            f"{len(en_cours)} match(s) en cours. Cliquez une ligne pour ouvrir "
            "son detail."
        )
        # Le SENS du dernier mouvement de chaque prix. Une seule requete pour
        # toute la liste (426 ms mesurees pour six matchs, a peine plus que
        # pour un seul) : c'est ce qui distingue les lignes qui remuent de
        # celles qui dorment, et rien d'autre dans la page ne le dit.
        try:
            serie = charger_serie(",".join(en_cours["event_ids"].astype(str)))
            bouge = mouvements_de_prix(serie, maintenant)
        except Exception:
            # Le mouvement est un CONFORT : son absence ne doit pas emporter
            # la liste, qui elle porte le score et les prix.
            bouge = {}
        _dessiner(lignes(en_cours, maintenant, bouge), ouvert, "en-cours")

    termines = matchs[~matchs["en_cours"]] if "en_cours" in matchs.columns else matchs.iloc[0:0]
    if not termines.empty:
        # Les matchs finis restent consultables tant que le publieur ne les a
        # pas retires (six heures) : leur serie vit sept jours, et c'est la
        # qu'on relit un match apres coup.
        st.subheader(f"Matchs termines ({len(termines)})")
        _dessiner(lignes(termines, maintenant), ouvert, "termines")

    if not ouvert:
        return
    demandes = {i.strip() for i in ouvert.split(",") if i.strip()}
    colonne = "event_ids" if "event_ids" in matchs.columns else "event_id"
    appartient = matchs[colonne].map(
        lambda ids: bool(demandes & {i.strip() for i in str(ids).split(",")})
    )
    choisi = matchs[appartient]
    if choisi.empty:
        st.info("Ce match n'est plus publie.")
        return
    m = choisi.iloc[0]

    try:
        # TOUS les identifiants du match : la série est répartie entre eux
        # quand la source en a émis plusieurs, et n'en lire qu'un afficherait
        # un demi-graphique sans le dire.
        serie = charger_serie(m.get("event_ids") or m.get("event_id"))
    except Exception:
        st.error("Base de donnees injoignable. Reessayez plus tard.")
        return
    _fenetre(m, serie, maintenant)


zone_donnees()
