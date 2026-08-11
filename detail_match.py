"""Le detail d'un match : score, cotes, statistiques, recit, point par point.

Ce module est PARTAGE : la page « En direct » l'affiche sous la liste quand on
selectionne une ligne, et la page « Match » l'affiche seule. Ecrire le rendu
deux fois garantirait qu'une correction n'atterrisse que d'un cote -- c'est le
genre d'ecart qui ne se voit qu'a l'usage, longtemps apres.

Il ne fait AUCUNE lecture de base : on lui passe la ligne du match et sa serie.
C'est ce qui permet a l'appelant de decider quand et comment lire, et de
proteger cette lecture lui-meme.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from live_data import (
    SEUILS_PAR_FLUX,
    age_a_la_lecture,
    chronologie,
    duree_courte,
    ecart_en_ticks,
    en_datetime,
    fraicheur,
    points_uniques,
    probabilite_implicite,
)
from utils import to_paris

PASTILLE = {"frais": "🟢", "perime": "🔴", "inconnu": "⚪"}

#: Les quatre compteurs publies par le PoC, avec leur libelle a l'ecran.
COMPTEURS = (
    ("aces", "aces"),
    ("doubles_fautes", "doubles fautes"),
    ("pct_1er_service", "1er service"),
    ("pct_conversion_bp", "conversion bp"),
)


def _val(ligne, cle, defaut="—"):
    """Un champ, sans jamais ecrire « nan ».

    NaN est VRAI au sens booleen : `ligne.get(cle) or defaut` laisserait
    passer le flottant que pandas rend pour un NULL SQL et l'afficherait
    litteralement.
    """
    v = ligne.get(cle)
    return defaut if v is None or pd.isna(v) else v


def _cote(ligne, cle) -> str:
    v = ligne.get(cle)
    return "—" if v is None or pd.isna(v) else f"{float(v):.2f}"


def bandeau_score(m) -> None:
    """Le score, les points, et qui sert -- ce qu'on lit en premier."""
    p1, p2 = str(_val(m, "participant1", "?")), str(_val(m, "participant2", "?"))
    srv = m.get("server")
    balle = ("🎾 " if str(srv) == "0" else "", "🎾 " if str(srv) == "1" else "")
    st.markdown(f"### {balle[0]}{p1}  ·  {balle[1]}{p2}")
    st.caption(f"{_val(m, 'league', '')} — {_val(m, 'status', '')}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Score", str(_val(m, "score")))
    c2.metric("Points", str(_val(m, "points")))
    proba = probabilite_implicite(
        m.get("back_odds_a"), m.get("lay_odds_a"),
        m.get("back_odds_b"), m.get("lay_odds_b"),
    )
    # La probabilite, pas la cote : « 1,38 contre 2,92 » ne dit pas
    # spontanement « 69 % ». Elle n'ajoute rien, elle rend lisible.
    c3.metric(
        "Marché donne (a)",
        "—" if proba is None else f"{proba:.0%}",
        help="Milieu des fourchettes back/lay des deux joueurs, marge retirée "
             "par normalisation proportionnelle. Absente si un côté manque : "
             "une probabilité tirée d'un seul joueur serait la marge déguisée.",
    )


def bandeau_cotes(m) -> None:
    """Les deux fourchettes, et l'ECART en ticks -- le cout d'execution."""
    lignes = []
    for suffixe, joueur in (("a", _val(m, "participant1", "a")),
                            ("b", _val(m, "participant2", "b"))):
        ticks = ecart_en_ticks(m.get(f"back_odds_{suffixe}"), m.get(f"lay_odds_{suffixe}"))
        lignes.append({
            "joueur": str(joueur),
            "back": _cote(m, f"back_odds_{suffixe}"),
            "lay": _cote(m, f"lay_odds_{suffixe}"),
            "écart (ticks)": "—" if ticks is None else ticks,
            "books": _cote(m, f"book_odds_{suffixe}"),
        })
    st.dataframe(
        pd.DataFrame(lignes), hide_index=True, width="stretch",
        column_config={
            "écart (ticks)": st.column_config.Column(
                help="Distance back/lay comptée en crans de l'échelle de "
                     "l'exchange, pas en valeur absolue : 0,05 vaut cinq crans "
                     "à 1,50 et un seul à 3,50. C'est le coût payé à chaque "
                     "aller-retour, et un carnet large signale un marché peu "
                     "suivi ou une photo périmée. Vide si le carnet est croisé.",
            ),
        },
    )


def bandeau_fraicheur(m, maintenant: float) -> None:
    """Une pastille par flux, avec son age effectif et son seuil."""
    colonnes = st.columns(len(SEUILS_PAR_FLUX))
    for col, (flux, (cle, seuil, libelle, question)) in zip(colonnes, SEUILS_PAR_FLUX.items()):
        age = age_a_la_lecture(m.get(cle), m.get("updated_ts"), maintenant)
        col.metric(
            libelle.replace(" -- ", " · "),
            f"{PASTILLE[fraicheur(age, seuil)]} {duree_courte(age)}",
            help=f"{question} Seuil propre à ce flux : {seuil:.0f} s.",
        )


#: Chaque serie : son libelle, sa couleur, et si elle s'affiche d'emblee.
#:
#: Le LAY est masque par defaut -- six courbes d'un coup rendent le
#: graphique illisible, et c'est le back qui porte la lecture. Masque ne veut
#: pas dire supprime : un clic sur la legende le rallume, ce qui n'est pas la
#: meme chose que de le retirer.
SERIES = (
    # Les DEUX joueurs partagent la couleur du metier -- bleu pour le back,
    # rose pour le lay -- et se distinguent par la clarte. Trop proches, les
    # deux courbes de back se confondaient.
    ("back_odds_a", "back a", "#3B82F6", True),
    ("back_odds_b", "back b", "#A9C9FA", True),
    ("lay_odds_a", "lay a", "#E06A98", "legendonly"),
    ("lay_odds_b", "lay b", "#F6C2D6", "legendonly"),
    ("book_odds_a", "books a", "#32b296", "legendonly"),
    ("book_odds_b", "books b", "#6FCFB8", "legendonly"),
)


def figure_cotes(serie):
    """La figure des cotes, ou ``None`` si rien n'est traçable.

    Echelle LOGARITHMIQUE : 3 a 4 % des releves depassent la cote 20 (maximum
    observe 990 en lay) et ces extremes sont ceux de la FIN de match. En
    lineaire ils ecrasent l'echelle des 97 % autres. Le log donne le meme
    espace vertical a un meme mouvement RELATIF -- l'echelle naturelle d'un
    prix -- et ne cache aucune donnee.

    Les valeurs absentes ne produisent AUCUN point : un prix a zero se
    lirait comme une certitude.
    """
    if serie is None or len(serie) == 0 or "ts" not in serie.columns:
        return None
    # L'axe du temps a l'heure de PARIS, comme la colonne « heure » de
    # la liste : deux echelles differentes sur la meme page se liraient
    # comme un decalage du match, pas comme un defaut d'affichage.
    temps = to_paris(pd.to_datetime(serie["ts"], unit="s"))
    # Le SCORE de l'instant, au survol : une courbe de cotes seule ne dit pas
    # ce qui l'a fait bouger. Affiche en dur sur l'axe il serait illisible --
    # vingt etiquettes sur un match -- alors qu'au survol il est la quand on
    # le cherche et absent le reste du temps.
    contexte = pd.DataFrame({
        "score": (serie["score"] if "score" in serie.columns else "").fillna("")
        if "score" in serie.columns else [""] * len(serie),
        "points": (serie["points"] if "points" in serie.columns else "").fillna("")
        if "points" in serie.columns else [""] * len(serie),
    })
    fig = go.Figure()
    trace = False
    for colonne, libelle, couleur, visible in SERIES:
        if colonne not in serie.columns:
            continue
        valeurs = pd.to_numeric(serie[colonne], errors="coerce")
        if not valeurs.notna().any():
            continue
        trace = True
        garde = valeurs.notna()
        fig.add_trace(go.Scatter(
            x=temps[garde], y=valeurs[garde], name=libelle,
            mode="lines", line=dict(color=couleur, width=1.8, shape="hv"),
            visible=visible, connectgaps=False,
            customdata=contexte[garde].to_numpy(),
            hovertemplate=(f"{libelle} %{{y:.2f}}"
                           "  ·  %{customdata[0]}  %{customdata[1]}"
                           "<extra></extra>"),
        ))
    if not trace:
        return None
    # Les fins de jeu, lues et non deduites : un repere faux serait pire
    # qu'aucun repere.
    if "evenement" in serie.columns:
        for _, r in serie[serie["evenement"].notna()].iterrows():
            fig.add_vline(
                x=to_paris(pd.to_datetime(r["ts"], unit="s")),
                line=dict(color="rgba(128,140,150,0.35)", width=1, dash="dot"),
            )
    fig.update_layout(
        template="plotly_dark", height=340,
        # L'axe des dates porte une seconde ligne (« Aug 5, 2026 ») :
        # sans marge basse elle se fait couper.
        margin=dict(l=8, r=8, t=28, b=34),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12, x=0, bgcolor="rgba(0,0,0,0)",
                    font=dict(size=11)),
        font=dict(size=11),
    )
    fig.update_xaxes(showgrid=False, title=None,
                     linecolor="rgba(128,128,128,0.25)")
    fig.update_yaxes(type="log", title=None, gridcolor="rgba(128,128,128,0.12)",
                     zeroline=False)
    return fig


#: Le motif PAR DEFAUT d'une courbe absente : la rencontre n'a jamais eu de
#: marche exchange. C'est le cas majoritaire en direct, et le seul que ce
#: module puisse constater tout seul.
SANS_MARCHE = "Ce match n'a pas de marché apparié : score seul."


def graphique_cotes(serie, jeux, absence: str | None = None) -> None:
    """Le graphique, ou le message qui dit pourquoi il n'y en a pas.

    ``absence`` laisse l'APPELANT expliquer une absence que lui seul peut
    expliquer. Une serie vide se lit « pas de marche apparie » pour un match
    du direct, mais « la retention de ``live_series`` ne remonte pas jusqu'a
    ce match » pour une archive : afficher le premier motif sur le second
    accuserait la collecte d'un trou qu'elle n'a pas. Un motif faux est pire
    qu'un motif absent -- il envoie chercher au mauvais endroit.
    """
    try:
        fig = figure_cotes(serie)
    except Exception:
        st.error("Impossible d'afficher le graphique de cotes pour ce match.")
        return
    if fig is None:
        st.info(absence or SANS_MARCHE)
        return
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})


def bandeau_statistiques(m) -> None:
    """Les quatre compteurs, les deux joueurs cote a cote."""
    presents = [(cle, lib) for cle, lib in COMPTEURS
                if not pd.isna(m.get(f"{cle}_a")) or not pd.isna(m.get(f"{cle}_b"))]
    if not presents:
        # Un FAIT, pas une panne : la source ne publie pas encore de compteur
        # pour ce match (debut de match, tour mineur).
        st.caption("Aucune statistique publiée pour ce match.")
        return
    lignes = [{
        "": lib,
        str(_val(m, "participant1", "a")): _val(m, f"{cle}_a"),
        str(_val(m, "participant2", "b")): _val(m, f"{cle}_b"),
    } for cle, lib in presents]
    st.dataframe(pd.DataFrame(lignes), hide_index=True, width="stretch")


def bandeau_recit(m) -> None:
    """Le recit jeu par jeu, LE DERNIER JEU EN TETE, avec les BREAKS nommes
    par la source.

    Les breaks ne sont pas deduits : ``evenement_de_score`` refuse de le faire
    parce qu'ils exigent de savoir qui servait, et que le champ serveur de la
    source se contredit dans 13 % des jeux. La chronologie du flux pousse, elle,
    ecrit « holds » ou « breaks ».

    Le sens de lecture n'a pas change -- il etait deja inverse -- mais le tri
    l'est : ``.iloc[::-1]`` retournait des POSITIONS, ce qui ne vaut que tant
    que la source rend ses jeux dans l'ordre. On trie sur ``jeu``, le numero
    de jeu de la source (courant sur tout le match, cf.
    ``Live/ws_tennis.jeux_de_chronologie``), et un jeu sans numero part en
    fin de tableau plutot que de prendre la place du dernier joue.
    """
    jeux = chronologie(m.get("chronologie"))
    if not jeux:
        st.caption("Aucun récit jeu par jeu reçu pour ce match.")
        return
    p1, p2 = str(_val(m, "participant1", "a")), str(_val(m, "participant2", "b"))
    lignes = [{
        "jeu": j.get("jeu"),
        "service": p1 if j.get("serveur") == 0 else p2,
        "issue": "BREAK" if j.get("break") else "tenu",
    } for j in jeux]
    n_breaks = sum(1 for j in jeux if j.get("break"))
    st.caption(f"{len(jeux)} jeux, dont {n_breaks} break(s)")
    table = pd.DataFrame(lignes).sort_values(
        "jeu", ascending=False, kind="stable", na_position="last")
    st.dataframe(table, hide_index=True, width="stretch",
                 height=min(320, 40 + 35 * len(lignes)))


def point_par_point(serie, m) -> None:
    """Un etat de jeu par ligne, LE DERNIER EN TETE, avec les cotes de
    l'instant du point.

    Le sens de lecture n'a pas change -- il etait deja inverse, et c'est
    celui qu'on veut quand on suit un direct -- mais le tri l'est :
    ``.iloc[::-1]`` retournait des POSITIONS, ce qui ne vaut que tant que la
    lecture rend les releves dans l'ordre du temps. On trie sur ``ts``, et
    sur le ``ts`` BRUT (secondes epoch) avant que ``en_datetime`` ne le mette
    en forme -- l'ordre se decide sur la valeur, jamais sur son affichage.

    ``kind="stable"`` : deux etats au meme horodatage gardent leur ordre
    d'arrivee. ``na_position="last"`` : un releve sans horodatage part en
    fin de tableau, il ne peut pas passer pour le dernier point joue.
    """
    replie = points_uniques(serie)
    if replie.empty:
        st.caption("Aucun relevé pour ce match.")
        return
    cotes = ("back_odds_a", "lay_odds_a", "back_odds_b", "lay_odds_b")
    visibles = ["ts", "score", "points", "evenement"] + [c for c in cotes if c in replie.columns]
    st.caption(
        f"{len(replie)} états de jeu ({len(serie)} relevés, les répétitions à "
        f"score inchangé sont repliées). Cotes = celles de l'exchange à "
        f"l'instant du point. a = {_val(m, 'participant1', 'a')}, "
        f"b = {_val(m, 'participant2', 'b')}."
    )
    vue = replie[[c for c in visibles if c in replie.columns]]
    if "ts" in vue.columns:
        vue = vue.sort_values("ts", ascending=False, kind="stable",
                              na_position="last")
    st.dataframe(
        en_datetime(vue),
        width="stretch", hide_index=True,
        column_config={
            "back_odds_a": st.column_config.NumberColumn("back a", format="%.2f"),
            "lay_odds_a": st.column_config.NumberColumn("lay a", format="%.2f"),
            "back_odds_b": st.column_config.NumberColumn("back b", format="%.2f"),
            "lay_odds_b": st.column_config.NumberColumn("lay b", format="%.2f"),
        },
    )


def afficher(m, serie, maintenant: float, absence_cotes: str | None = None) -> None:
    """Le detail complet. ``m`` est une ligne de ``live_now``, ``serie`` sa
    serie temporelle -- deja lues et protegees par l'appelant.

    ``absence_cotes`` est le motif a afficher a la place de la courbe quand
    il n'y en a pas et que l'appelant en sait la raison (voir
    ``graphique_cotes``). Par defaut, ce module dit ce qu'il peut constater
    seul : pas de marche apparie.
    """
    bandeau_score(m)
    bandeau_cotes(m)
    bandeau_fraicheur(m, maintenant)
    onglets = st.tabs(["Cotes", "Statistiques", "Récit des jeux", "Point par point"])
    with onglets[0]:
        graphique_cotes(serie, None, absence_cotes)
    with onglets[1]:
        bandeau_statistiques(m)
    with onglets[2]:
        bandeau_recit(m)
    with onglets[3]:
        point_par_point(serie, m)
