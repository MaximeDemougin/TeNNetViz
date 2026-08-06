"""Ce que seul un vrai navigateur peut dire : ou le clic atterrit.

Cette page a livre DEUX defauts purement visuels que 169 tests verts n'ont
pas vus, parce qu'aucun ne regardait un rendu :

- les pastilles de fraicheur n'avaient aucune couleur -- la feuille de style
  colorait « ok / tiede / mort » quand le HTML ecrit « frais / perime /
  inconnu » ;
- le clic ne portait pas sur la ligne. Streamlit enveloppe chaque element
  dans un `stElementContainer` pose en `position: relative` ; c'etait donc
  LUI, et non la ligne, qui servait de reference a `inset: 0`. Le bouton
  faisait 16 px de large et tombait 57 px SOUS sa propre ligne.

Aucun de ces deux defauts n'est visible depuis l'arbre de rendu de
`AppTest` : les conteneurs nommes n'y figurent pas, et rien n'y applique le
CSS. Il faut un moteur de rendu, une geometrie, et la question que pose
`elementFromPoint` : si l'on clique ce pixel, qui recoit le clic ?

Le test se saute proprement si `google-chrome` n'est pas installe -- il ne
doit jamais rendre la suite dependante d'un navigateur.
"""

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

CHROME = shutil.which("google-chrome") or shutil.which("chromium")
websocket = pytest.importorskip("websocket", reason="websocket-client absent")
pytestmark = pytest.mark.skipif(CHROME is None, reason="aucun navigateur installe")

RACINE = Path(__file__).resolve().parent.parent

#: L'application de banc : elle importe le VRAI module et appelle les MEMES
#: fonctions que `pages/live.py`. On ne mesure pas une imitation du rendu.
BANC = '''
import sys, time
sys.path.insert(0, {racine!r})
import pandas as pd
import streamlit as st
from liste_dense import CSS, cle_bouton, cle_carte, cle_ligne, lignes, rendu

st.set_page_config(layout="wide")
_c = {{
    "status": "InPlay", "age_score_s": 2.0, "age_exchange_s": 2.0,
    "age_books_s": 2.0, "age_books_flux_s": 2.0, "age_stats_s": 2.0,
    "updated_ts": time.time(), "points": "30-0", "server": "0",
    "back_odds_a": 1.5, "lay_odds_a": 1.56, "back_odds_b": 2.6, "lay_odds_b": 2.74,
    "league": "Hagen Challenger", "tour_type": "atp",
}}
# Des lignes de hauteurs et de largeurs INEGALES : un nom tres long, un match
# a cinq sets, un match sans cotes. Une fixture ou toutes les lignes se
# ressemblent ne dirait rien du cas ou le bouton doit epouser SA ligne.
_matchs = [
    {{**_c, "event_id": "m0", "participant1": "A", "participant2": "B",
      "score": "6-4,3-2", "start_timestamp": time.time() - 600}},
    {{**_c, "event_id": "m1", "score": "6-4,3-6,7-6,2-6,8-6",
      "participant1": "Yannick Theodor Alexandrescou de la Tres Longue Lignee",
      "participant2": "C", "start_timestamp": time.time() - 500}},
    # Une BALLE DE BREAK : sans elle le banc ne pouvait pas voir que le
    # badge orange decale les chiffres par rapport a un point ordinaire.
    {{**_c, "event_id": "m3", "participant1": "G", "participant2": "H",
      "score": "6-4,3-2", "points": "30-40", "start_timestamp": time.time() - 300}},
    {{**_c, "event_id": "m2", "participant1": "D", "participant2": "E",
      "score": "1-0", "start_timestamp": time.time() - 400,
      "back_odds_a": None, "lay_odds_a": None,
      "back_odds_b": None, "lay_odds_b": None}},
]
_struct = lignes(pd.DataFrame(_matchs), time.time())
st.markdown(CSS, unsafe_allow_html=True)
# Les lignes vivent DANS une carte de tournoi, comme sur la page : un banc
# qui les dessine a nu ne voit pas ce que la carte change. Regler l'ecart
# entre matchs en CSS plutot que par `gap` a fait retomber le conteneur de
# ligne a 30 px pour un contenu de 46 -- le bouton n'en couvrait plus que
# les deux tiers -- et ce banc-ci, sans carte, restait vert.
for _s in ("en-cours", "termines"):
  with st.container(border=True, gap=None, key=cle_carte(_s, 0)):
    for _l in _struct:
        with st.container(key=cle_ligne(_s, _l["event_id"])):
            st.markdown(rendu([_l], "", entetes=False, section=_s),
                        unsafe_allow_html=True)
            if st.button("Ouvrir " + _l["event_id"], key=cle_bouton(_s, _l["event_id"])):
                st.session_state["clic"] = _s + "/" + _l["event_id"]
st.write("dernier clic :", st.session_state.get("clic", "aucun"))
'''

#: Pour chaque ligne : le bouton epouse-t-il la ligne visible, quels points
#: d'un quadrillage NE tombent PAS dessus, et de combien la zone cliquable
#: deborde de la zone visible.
MESURE = """
(() => {
  const cles = [...document.querySelectorAll('[class*="st-key-ligne-"]')];
  if (!cles.length) return {erreur: document.body.innerText.slice(0, 400)};
  return cles.map(c => {
    const v = c.querySelector(".match"), b = c.querySelector("button");
    if (!v || !b) return {erreur: "ligne sans .match ou sans bouton"};
    const rv = v.getBoundingClientRect(), rb = b.getBoundingClientRect();
    const rc = c.getBoundingClientRect();
    const manques = [];
    for (let fx = 0.02; fx <= 0.99; fx += 0.06) {
      for (const fy of [0.08, 0.5, 0.92]) {
        const el = document.elementFromPoint(rv.left + rv.width * fx,
                                             rv.top + rv.height * fy);
        if (!(el && (el === b || b.contains(el))))
          manques.push([+fx.toFixed(2), fy,
                        el ? el.tagName.toLowerCase() : "rien"]);
      }
    }
    return {
      id: c.className.match(/st-key-(ligne-[\\w-]+)/)[1],
      ecart_haut: Math.round(rb.top - rv.top),
      ecart_hauteur: Math.round(rb.height - rv.height),
      debord_droite: Math.round(rc.right - rv.right),
      debord_bas: Math.round(rc.bottom - rv.bottom),
      manques: manques,
    };
  });
})()
"""


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _Navigateur:
    """Un chrome pilote par le protocole DevTools, le temps d'une mesure."""

    def __init__(self, port):
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--remote-debugging-port={port}", "--window-size=1400,900",
             f"--user-data-dir=/tmp/chrome-test-{port}",
             "--remote-allow-origins=*", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cibles = None
        for _ in range(80):
            try:
                cibles = json.loads(
                    urllib.request.urlopen(f"http://localhost:{port}/json").read())
                if cibles:
                    break
            except Exception:
                time.sleep(0.25)
        assert cibles, "navigateur injoignable"
        self.ws = websocket.create_connection(
            [c for c in cibles if c["type"] == "page"][0]["webSocketDebuggerUrl"],
            timeout=60)
        self._n = 0
        self.cdp("Page.enable")
        self.cdp("Runtime.enable")

    def cdp(self, methode, **params):
        self._n += 1
        self.ws.send(json.dumps({"id": self._n, "method": methode, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self._n:
                assert "error" not in m, m["error"]
                return m.get("result", {})

    def js(self, source):
        r = self.cdp("Runtime.evaluate", expression=source,
                     returnByValue=True, awaitPromise=True)
        assert not r.get("exceptionDetails"), r.get("exceptionDetails")
        return r["result"].get("value")

    def clic(self, x, y):
        for genre in ("mousePressed", "mouseReleased"):
            self.cdp("Input.dispatchMouseEvent", type=genre, x=x, y=y,
                     button="left", clickCount=1)

    def fermer(self):
        try:
            self.ws.close()
        finally:
            self.proc.terminate()
            self.proc.wait(timeout=10)


@pytest.fixture(scope="module")
def rendu_reel(tmp_path_factory):
    """La page servie par un vrai Streamlit, lue par un vrai navigateur."""
    dossier = tmp_path_factory.mktemp("banc")
    app = dossier / "banc.py"
    app.write_text(BANC.format(racine=str(RACINE)))
    port = _port_libre()
    serveur = subprocess.Popen(
        [str(Path(sys.executable).parent / "streamlit"), "run", str(app),
         "--server.port", str(port), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    nav = None
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://localhost:{port}/", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            pytest.skip("le serveur Streamlit n'a pas demarre")
        nav = _Navigateur(_port_libre())
        nav.cdp("Page.navigate", url=f"http://localhost:{port}")
        # Streamlit monte son websocket puis rend : la page est vide avant.
        for _ in range(40):
            time.sleep(0.5)
            if nav.js("document.querySelectorAll('[class*=\"st-key-ligne-\"]').length"):
                time.sleep(1.0)
                break
        else:
            pytest.skip("la page n'a jamais rendu de ligne")
        yield nav
    finally:
        if nav is not None:
            nav.fermer()
        serveur.terminate()
        serveur.wait(timeout=15)


def test_le_bouton_RECOUVRE_exactement_sa_ligne(rendu_reel):
    """Le defaut livre : `inset: 0` se resolvait contre le conteneur
    d'element de Streamlit (16 x 0 px, pose en position relative) et non
    contre la ligne. Le bouton mesurait 16 px de large et tombait 57 px
    SOUS son match -- donc dans la bande du suivant."""
    lignes_ = rendu_reel.js(MESURE)
    assert isinstance(lignes_, list) and lignes_, f"aucune ligne rendue : {lignes_}"
    for ligne in lignes_:
        assert "erreur" not in ligne, ligne["erreur"]
        assert abs(ligne["ecart_haut"]) <= 1, \
            f"{ligne['id']} : le bouton est decale de {ligne['ecart_haut']} px"
        assert abs(ligne["ecart_hauteur"]) <= 1, \
            f"{ligne['id']} : hauteur du bouton hors de {ligne['ecart_hauteur']} px"


def test_le_clic_ATTEINT_le_bouton_partout_sur_la_ligne(rendu_reel):
    """Une ligne se parcourt, elle ne se vise pas : le clic doit porter sur
    toute sa surface, pas sur une zone qu'il faut trouver."""
    for ligne in rendu_reel.js(MESURE):
        assert not ligne["manques"], \
            f"{ligne['id']} : {len(ligne['manques'])} points n'atteignent pas " \
            f"le bouton, p.ex. {ligne['manques'][:3]}"


def test_la_zone_CLIQUABLE_ne_deborde_pas_de_la_zone_visible(rendu_reel):
    """Cliquer dans le vide a droite de la liste ouvrait un match : le
    conteneur restait large de 1240 px quand la ligne visible en fait 1008."""
    for ligne in rendu_reel.js(MESURE):
        assert ligne["debord_droite"] <= 1, \
            f"{ligne['id']} : {ligne['debord_droite']} px cliquables hors du visible"
        assert ligne["debord_bas"] <= 1, \
            f"{ligne['id']} : {ligne['debord_bas']} px cliquables sous la ligne"


def test_un_vrai_clic_ouvre_le_BON_match(rendu_reel):
    """La geometrie ne prouve pas l'effet. Un survol qui intercepte, un
    `pointer-events`, un z-index : rien de tout cela ne se voit dans un
    rectangle."""
    rects = rendu_reel.js("""
      (() => [...document.querySelectorAll('[class*="st-key-ligne-"]')].map(c => {
        const r = c.querySelector('.match').getBoundingClientRect();
        return [c.className.match(/st-key-ligne-([\\w-]+?)\\s|st-key-ligne-([\\w-]+)/)
                  .slice(1).find(Boolean),
                r.left, r.top, r.width, r.height];
      }))()""")
    assert len(rects) >= 2, rects
    attendus, obtenus = [], []
    for ident, x, y, w, h in rects[:4]:
        for fx, fy in ((0.5, 0.5), (0.02, 0.5), (0.98, 0.9)):
            rendu_reel.clic(x + w * fx, y + h * fy)
            time.sleep(1.6)
            vu = rendu_reel.js("""
              (() => {const t = [...document.querySelectorAll(
                 '[data-testid="stMarkdownContainer"]')].map(e => e.innerText)
                 .filter(t => t.startsWith('dernier clic'));
                 return t.length ? t[t.length - 1].split(':').pop().trim() : 'absent';})()""")
            attendus.append(ident.replace("-", "/", 0))
            obtenus.append(vu)
    # `ident` vaut « en-cours-m0 » ; l'app repond « en-cours/m0 ».
    normalise = [a.replace("en-cours-", "en-cours/").replace("termines-", "termines/")
                 for a in attendus]
    rates = [(a, o) for a, o in zip(normalise, obtenus) if a != o]
    assert not rates, f"{len(rates)} clics sur {len(obtenus)} ouvrent le mauvais match : {rates[:3]}"


ESPACEMENT = """
(() => {
  const ligne = document.querySelector('[class*="st-key-ligne-"] .match');
  if (!ligne) return {erreur: "aucune ligne"};
  const out = {piles: {}, colonnes: []};
  // Ecart VERTICAL entre les deux rangees de chaque pile : a hauteur de
  // rangee trop courte, elles se chevauchent et les cases se touchent.
  for (const c of ["noms", "jeux", "pts", "prix"]) {
    const cell = ligne.querySelector("." + c);
    const enf = cell ? [...cell.children] : [];
    if (enf.length >= 2)
      out.piles[c] = Math.round(enf[1].getBoundingClientRect().top
                                - enf[0].getBoundingClientRect().bottom);
  }
  // Ecart HORIZONTAL entre colonnes voisines.
  let prec = null;
  for (const c of ["heure", "noms", "srv", "jeux", "pts", "prix", "ecart", "flux"]) {
    const d = ligne.querySelector("." + c);
    if (!d) continue;
    const r = d.getBoundingClientRect();
    if (prec !== null) out.colonnes.push(Math.round(r.left - prec));
    prec = r.right;
  }
  return out;
})()
"""


def test_les_deux_joueurs_ne_se_CHEVAUCHENT_pas(rendu_reel):
    """La hauteur de rangee est FIXE dans les quatre piles -- c'est elle qui
    fait tomber le second joueur en face de ses propres cotes. Trop courte,
    les rangees se recouvrent : mesure au navigateur, -5 px sur les noms et
    -3 px sur les cases de set, qui se touchaient.

    Aucune assertion sur du CSS ne peut voir cela : la hauteur du contenu
    depend de la police rendue.
    """
    m = rendu_reel.js(ESPACEMENT)
    assert "erreur" not in m, m
    assert m["piles"], "aucune pile a deux rangees mesuree"
    for pile, ecart in m["piles"].items():
        assert ecart >= 2, f"les deux rangees de « {pile} » se touchent ({ecart} px)"


def test_les_rangees_ont_l_AIR_demande(rendu_reel):
    """Celui-ci n'est pas un defaut, c'est une PREFERENCE, et il faut le
    dire : ne pas se chevaucher (test precedent) et respirer sont deux
    exigences differentes. Reglee a 1,15rem la hauteur de rangee ne
    chevauche plus rien -- elle serre seulement, et « ajoute de l'espace »
    reste une demande legitime qu'aucune mesure de defaut ne protege.
    """
    m = rendu_reel.js(ESPACEMENT)
    for pile, ecart in m["piles"].items():
        assert ecart >= 6, f"« {pile} » manque d'air ({ecart} px, attendu 6)"


def test_les_colonnes_RESPIRENT(rendu_reel):
    """Colonnes collees, la ligne devient un mur de chiffres. Le proprietaire
    l'a dit avant que la mesure ne le confirme : 13 px entre colonnes."""
    m = rendu_reel.js(ESPACEMENT)
    assert len(m["colonnes"]) >= 5, m["colonnes"]
    assert min(m["colonnes"]) >= 14, \
        f"colonnes trop serrees : {m['colonnes']}"


def test_le_badge_de_BREAK_ne_decale_pas_les_chiffres(rendu_reel):
    """Le badge portait un rembourrage que le texte nu n'avait pas : le
    « 40 » orange ne tombait pas sous le « 30 » de la ligne du dessus.
    Un chiffre qui saute d'une ligne a l'autre se relit a chaque fois.

    On mesure le bord droit du TEXTE, pas de la boite : c'est lui qu'on lit.
    """
    bords = rendu_reel.js("""
      (() => {
        const out = [];
        for (const m of document.querySelectorAll(".match")) {
          for (const p of m.querySelectorAll(".pts span")) {
            const g = document.createRange(); g.selectNodeContents(p);
            out.push({x: Math.round(g.getBoundingClientRect().right),
                      bp: p.className.includes("bp")});
          }
        }
        return out;
      })()""")
    assert bords, "aucun point mesure"
    assert any(b["bp"] for b in bords), \
        "aucune balle de break dans le banc : le test ne prouve rien"
    x = {b["x"] for b in bords}
    assert len(x) == 1, f"les chiffres ne tombent pas au meme endroit : {sorted(x)}"
