# Flux continu de la page « En direct » — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** La page « En direct » se met à jour sans se griser, et ses flèches de mouvement cessent d'être fausses.

**Architecture:** Trois gestes indépendants. (1) `fusionner_series` ne replie plus deux identifiants qu'on ne lui a pas déclarés appartenant au même match — c'est la correction d'un défaut de justesse mesuré. (2) La liste lit ses mouvements par un lecteur dédié, sans fusion : 341 ms → 16 ms, le cycle passe très en dessous du seuil de 500 ms au-delà duquel Streamlit grise. (3) Une feuille de style éteint le grisement pour de bon, et un battement plus un surlignage des seules valeurs qui changent remplacent le signal ainsi supprimé.

**Tech Stack:** Python 3.12, Streamlit 1.52.2, pandas 2.3, pytest, Chrome headless piloté par le protocole DevTools.

**Spec:** [`docs/superpowers/specs/2026-08-10-flux-continu-page-en-direct-design.md`](../specs/2026-08-10-flux-continu-page-en-direct-design.md)

## Global Constraints

- **Interpréteur et tests.** `poetry run` ne marche PAS ici : le projet s'appelle `tenentviz` dans `pyproject.toml` mais le venv qui porte les dépendances est `tennet-BfZcHEB2-py3.12`. Toutes les commandes de ce plan utilisent :
  `PY=/home/ubuntu/.cache/pypoetry/virtualenvs/tennet-BfZcHEB2-py3.12/bin/python`
- **Aucune dépendance nouvelle.** Tout est déjà installé (`websocket-client`, `google-chrome` présents et fonctionnels — les 294 tests passent en 39 s, tests navigateur compris).
- **Langue.** Code, noms de fonctions, docstrings, messages d'assertion et noms de tests en **français**, sans accents dans les identifiants Python — c'est la convention de tout le dépôt.
- **Docstrings.** Ce dépôt écrit POURQUOI, jamais QUOI. Chaque docstring cite le défaut constaté ou la mesure qui justifie la règle. Un commentaire qui paraphrase le code est un défaut de style ici.
- **Rétrocompatibilité des structures.** `rendu()` et `lignes()` sont appelés par `pages/live.py`, `tests/test_navigateur.py` et `tests/test_pages_live.py`. Toute clé nouvelle dans la structure doit être **optionnelle** (`.get()`), sinon les bancs existants cassent.
- **Point de départ.** Arbre propre sur `main`, `294 passed`. Chaque tâche se termine sur `294+ passed`.

---

### Task 1 : `fusionner_series` refuse de mélanger deux matchs

Corrige le défaut du §3 de la spec : la fonction groupe sur `ts` seul, la liste lui passe six matchs, le publieur les écrit au même horodatage, et 62 % des lignes sont écrasées.

**Files:**
- Modify: `live_data.py:1290-1332` (`fusionner_series`), `live_data.py:781-820` (`charger_serie`)
- Test: `tests/test_live_data.py` (ajouts après `test_charger_serie_replie_les_horodatages_doubles`, ligne ~1372)

**Interfaces:**
- Produces: `fusionner_series(df: pd.DataFrame, famille=None) -> pd.DataFrame`. `famille` est un itérable d'`event_id` déclarés appartenir à une même rencontre. `None` = aucune déclaration = aucun repliement entre identifiants distincts.
- Produces: `charger_serie(event_id, lecteur=None) -> pd.DataFrame` — signature inchangée, mais passe désormais `famille=surs` à la fusion.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_live_data.py`, à la suite de `test_charger_serie_replie_les_horodatages_doubles` :

```python
def test_deux_MATCHS_au_meme_instant_ne_se_replient_PAS():
    """Le defaut du 2026-08-10, mesure contre TeNNet_test : la liste passait
    les six matchs en cours a `charger_serie`, le publieur les ecrit tous
    dans le meme cycle donc au MEME `ts`, et la fusion -- qui groupait sur
    `ts` seul -- n'en gardait qu'un. 342 horodatages sur 439 etaient
    partages, 62 % des lignes ecrasees, et la survivante empruntait ses
    colonnes vides aux AUTRES matchs. Trois matchs sur six perdaient leur
    fleche de mouvement, et l'une des trois restantes pointait a l'envers.
    """
    df = pd.DataFrame([
        _pt(100.0, "0-0", "0-0", event_id="A", back_odds_a=3.10),
        _pt(100.0, "1-6,1-2", "40-40", event_id="B", back_odds_a=10.00),
        _pt(100.0, "6-4,0-1", "0-0", event_id="C", back_odds_a=1.34),
    ])
    out = fusionner_series(df)
    assert len(out) == 3, "aucun match n'a le droit d'en absorber un autre"
    assert set(out["event_id"]) == {"A", "B", "C"}
    # Chacun garde SES cotes : le comblement des colonnes vides ne doit
    # jamais traverser la frontiere d'un match.
    par_id = out.set_index("event_id")["back_odds_a"].to_dict()
    assert par_id == {"A": 3.10, "B": 10.00, "C": 1.34}


def test_une_FAMILLE_declaree_se_replie_toujours():
    """Le comportement du 2026-08-04 doit survivre : la source attribue
    parfois deux `event_id` a une seule rencontre, l'un portant la cote
    bookmaker que l'autre n'a pas. On garde le score le PLUS AVANCE et on
    comble les trous avec l'autre vue -- mais seulement entre identifiants
    qu'on a explicitement declares parents."""
    df = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", event_id="1", book_odds_a=1.85),
        _pt(100.0, "3-4", "0-15", event_id="2"),
    ])
    out = fusionner_series(df, famille=["1", "2"])
    assert len(out) == 1
    assert out.iloc[0]["score"] == "3-4", "le score le plus avance"
    assert out.iloc[0]["book_odds_a"] == 1.85, "la cote book de l'AUTRE vue"


def test_un_identifiant_HORS_famille_reste_a_part():
    """Declarer une famille n'ouvre pas la porte a tout le reste : un match
    etranger present dans le meme tableau garde ses lignes."""
    df = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", event_id="1"),
        _pt(100.0, "3-4", "0-15", event_id="2"),
        _pt(100.0, "6-0", "40-0", event_id="etranger"),
    ])
    out = fusionner_series(df, famille=["1", "2"])
    assert len(out) == 2, out.to_dict("records")
    assert set(out["event_id"]) == {"2", "etranger"}


def test_sans_colonne_event_id_la_fusion_groupe_sur_le_temps():
    """Une serie sans identifiant ne permet PAS de distinguer deux matchs :
    on ne peut alors que grouper sur l'instant. C'est le seul cas ou le
    comportement d'avant subsiste, et il ne se produit jamais en service --
    `charger_serie` et `charger_mouvements` lisent toujours `event_id`."""
    df = pd.DataFrame([_pt(100.0, "2-4", "0-0"), _pt(100.0, "3-4", "0-15")])
    out = fusionner_series(df)
    assert len(out) == 1
    assert out.iloc[0]["score"] == "3-4"


def test_charger_serie_declare_la_famille_qu_il_a_demandee():
    """`charger_serie` promet « la serie d'UN match » : les identifiants
    qu'il recoit sont, par construction, une famille."""
    doubles = pd.DataFrame([
        _pt(100.0, "2-4", "0-0", event_id="1", book_odds_a=1.85),
        _pt(100.0, "3-4", "0-15", event_id="2"),
        _pt(200.0, "3-4", "30-15", event_id="1"),
    ])
    out = charger_serie("1,2", lecteur=lambda schema, query: doubles)
    assert len(out) == 2, out.to_dict("records")
    assert out.iloc[0]["score"] == "3-4"
    assert out.iloc[0]["book_odds_a"] == 1.85
    assert list(out["ts"]) == [100.0, 200.0], "la serie reste dans l'ordre du temps"
```

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
PY=/home/ubuntu/.cache/pypoetry/virtualenvs/tennet-BfZcHEB2-py3.12/bin/python
$PY -m pytest tests/test_live_data.py -k "MATCHS_au_meme_instant or FAMILLE_declaree or HORS_famille" -v
```

Attendu : `test_deux_MATCHS_au_meme_instant_ne_se_replient_PAS` **FAIL** (`assert 1 == 3`) — c'est le défaut d'aujourd'hui, reproduit. `test_une_FAMILLE_declaree_se_replie_toujours` et `test_un_identifiant_HORS_famille_reste_a_part` **FAIL** avec `TypeError: fusionner_series() got an unexpected keyword argument 'famille'`.

**Si le premier test passe au vert d'emblée, arrêter et le signaler** : cela voudrait dire que le défaut mesuré ne se reproduit pas, et le reste du plan repose dessus.

- [ ] **Step 3: Implémenter**

Dans `live_data.py`, remplacer intégralement `fusionner_series` (lignes 1290-1332) :

```python
def fusionner_series(df: pd.DataFrame, famille=None) -> pd.DataFrame:
    """Une ligne par INSTANT, pour les identifiants qu'on a declares parents.

    ``charger_serie`` lit tous les identifiants d'un meme match (cf.
    ``fusionner_doublons``). Chacun ecrit sa propre ligne a CHAQUE cycle du
    publieur, donc au MEME horodatage : sans repliement, le tableau point par
    point affiche deux lignes par instant, portant des scores differents.
    Constate a l'usage le 2026-08-04.

    Mesure sur les deux matchs concernes : les deux vues sont d'accord sur
    les cotes de l'exchange dans 100 % des cas (c'est le meme marche), mais
    en desaccord sur le score dans 77 % des instants doubles -- et l'ecart
    porte sur un JEU ENTIER 5 et 30 fois. La cote du bookmaker, elle, n'est
    presente que d'UN cote (45 et 77 fois) : c'est precisement pour ne pas la
    perdre qu'on lit les deux identifiants.

    On garde donc, par instant, le score le PLUS AVANCE, et pour chaque autre
    colonne la premiere valeur renseignee. Jamais de moyenne : deux vues d'un
    meme carnet ne se moyennent pas, l'une est simplement en retard.

    ``famille`` DECLARE quels identifiants sont parents, et c'est la seule
    facon de le savoir : ``live_series`` ne porte aucune colonne « match »,
    l'appartenance vient de ``live_now.event_ids`` et de nulle part ailleurs.
    Sans declaration, deux identifiants distincts ne se replient JAMAIS.

    C'est la correction du defaut du 2026-08-10 : la fonction groupait sur
    ``ts`` SEUL, ce qui revenait a tenir un horodatage commun pour une
    appartenance commune. La page « En direct » lui passait les six matchs en
    cours d'un coup ; le publieur les ecrit dans le meme cycle, donc au meme
    instant. Mesure contre ``TeNNet_test`` : 342 horodatages sur 439 partages
    entre plusieurs matchs, 726 lignes sur 1165 ecrasees -- 62 % -- et les
    survivantes comblaient leurs colonnes vides avec les valeurs d'un AUTRE
    match. Trois matchs sur six perdaient leur fleche de mouvement, et l'une
    des trois restantes pointait a l'envers.
    """
    if df is None or df.empty or "ts" not in df.columns:
        return df if df is not None else pd.DataFrame()
    declaree = {str(e) for e in (famille or [])}
    if "event_id" in df.columns:
        # Les membres declares partagent la cle vide : eux seuls se replient
        # entre eux. Tout autre identifiant garde la sienne, donc sa ligne.
        parente = df["event_id"].map(
            lambda e: "" if str(e) in declaree else str(e))
    else:
        # Sans identifiant, rien ne permet de distinguer deux matchs : on ne
        # peut que grouper sur l'instant. N'arrive jamais en service.
        parente = pd.Series("", index=df.index)
    travail = df.assign(_parente=parente)
    if not travail.duplicated(subset=["_parente", "ts"]).any():
        return df.reset_index(drop=True)
    sorties = []
    for _, groupe in travail.groupby(["_parente", "ts"], sort=True):
        if len(groupe) == 1:
            sorties.append(groupe.iloc[0])
            continue
        rangs = [
            avancement(l.get("score"), l.get("points"))
            for _, l in groupe.iterrows()
        ]
        base = groupe.iloc[rangs.index(max(rangs))].copy()
        for colonne in groupe.columns:
            if colonne in ("score", "points", "ts", "event_id", "_parente"):
                continue
            if pd.isna(base.get(colonne)):
                renseignees = groupe[colonne].dropna()
                if not renseignees.empty:
                    base[colonne] = renseignees.iloc[0]
        sorties.append(base)
    # Le tri sur `ts` est desormais EXPLICITE. Il l'etait implicitement tant
    # qu'on groupait sur `ts` seul ; grouper d'abord par parente le perdrait,
    # et les series de deux identifiants doivent s'entrelacer dans le temps
    # -- sans quoi la courbe revient en arriere au milieu du graphique.
    return (pd.DataFrame(sorties)
            .drop(columns=["_parente"])
            .sort_values("ts", kind="stable")
            .reset_index(drop=True))
```

Puis, dans `charger_serie` (`live_data.py`), remplacer la dernière ligne :

```python
    # Chaque identifiant ecrit sa ligne au MEME horodatage a chaque cycle :
    # sans ce repliement, le tableau point par point montrerait deux lignes
    # par instant, avec des scores en desaccord jusqu'a un jeu entier.
    #
    # La famille est DECLAREE : cette fonction promet « la serie d'un match »,
    # donc les identifiants qu'elle a recus sont parents par construction.
    # Sans cette declaration la fusion ne replierait plus rien -- c'est le
    # sens meme de la correction du 2026-08-10.
    return fusionner_series(df, famille=surs)
```

- [ ] **Step 4: Lancer la suite entière**

```bash
$PY -m pytest tests/ -q
```

Attendu : `299 passed`. Les tests existants `test_deux_vues_du_meme_instant_gardent_la_PLUS_AVANCEE`, `test_l_ordre_des_lignes_ne_decide_de_rien` et `test_une_serie_a_un_seul_identifiant_est_rendue_intacte` restent verts : leurs fixtures `_pt` ne posent pas d'`event_id`, donc le repli sur l'instant s'applique.

- [ ] **Step 5: Commit**

```bash
git add live_data.py tests/test_live_data.py
git commit -m "fix: la fusion des series ne replie plus deux matchs distincts

Elle groupait sur \`ts\` SEUL alors que sa docstring parle des identifiants
d'un meme match. La page « En direct » lui passait les six matchs en cours
d'un coup ; le publieur les ecrit dans le meme cycle, donc au meme instant.
Mesure contre TeNNet_test : 342 horodatages sur 439 partages, 726 lignes sur
1165 ecrasees, et les survivantes empruntaient leurs colonnes vides aux
autres matchs.

L'appartenance est desormais DECLAREE. Elle ne pouvait pas etre devinee :
live_series ne porte aucune colonne « match »."
```

---

### Task 2 : `charger_mouvements`, le lecteur que la liste attendait

**Files:**
- Modify: `live_data.py` (nouvelle fonction après `charger_serie`, ~ligne 821)
- Test: `tests/test_live_data.py`

**Interfaces:**
- Consumes: `_identifiants_surs`, `_litteral_liste`, `SCHEMA` (Task 1 ne les touche pas).
- Produces: `charger_mouvements(event_id, lecteur=None) -> pd.DataFrame` — colonnes `event_id, ts, back_odds_a, lay_odds_a, back_odds_b, lay_odds_b`, **aucune fusion**.
- Produces: `COLONNES_MOUVEMENT: tuple[str, ...]`

- [ ] **Step 1: Écrire les tests qui échouent**

```python
def test_charger_mouvements_ne_lit_que_les_colonnes_du_MOUVEMENT():
    """341 ms mesurees pour la liste, dont 289 en fusion et 48 en SQL. La
    liste n'a besoin que du sens des prix : six colonnes, aucune fusion.
    Mesure du 2026-08-10 : 16 ms au lieu de 341."""
    vues = {}
    def lecteur(schema, query):
        vues["query"] = query
        return pd.DataFrame()
    charger_mouvements("1,2", lecteur=lecteur)
    q = vues["query"]
    assert "SELECT *" not in q, "la liste ne lit pas quatorze colonnes pour six"
    for colonne in ("event_id", "ts", "back_odds_a", "lay_odds_a",
                    "back_odds_b", "lay_odds_b"):
        assert colonne in q, colonne
    assert "'1', '2'" in q, q
    assert q.rstrip().endswith("ORDER BY ts"), q


def test_charger_mouvements_ne_replie_RIEN():
    """C'est tout l'objet de ce lecteur : `mouvements_de_prix` regroupe par
    `event_id`, et `lignes()` refusionne ensuite les identifiants d'un match.
    Replier ici couterait 289 ms pour detruire l'information."""
    brut = pd.DataFrame([
        {"event_id": "A", "ts": 100.0, "back_odds_a": 3.10, "lay_odds_a": 3.2,
         "back_odds_b": 1.46, "lay_odds_b": 1.5},
        {"event_id": "B", "ts": 100.0, "back_odds_a": 10.0, "lay_odds_a": 11.0,
         "back_odds_b": 1.07, "lay_odds_b": 1.1},
    ])
    out = charger_mouvements("A,B", lecteur=lambda schema, query: brut)
    assert len(out) == 2, "deux matchs au meme instant restent deux lignes"


def test_charger_mouvements_n_interroge_pas_la_base_pour_rien():
    """`IN ()` est une erreur de syntaxe MySQL : sans identifiant
    exploitable, on ne pose pas la question. Meme regle que `charger_serie`."""
    appels = []
    charger_mouvements("", lecteur=lambda s, q: appels.append(q))
    charger_mouvements(None, lecteur=lambda s, q: appels.append(q))
    assert appels == [], appels


def test_charger_mouvements_partage_la_regle_de_surete_SQL():
    """La regle qui rend la ligne SQL sure est ecrite UNE fois
    (`_identifiants_surs`). Pour une regle de SECURITE, le cote oublie serait
    celui qu'on ne verrait jamais."""
    vues = {}
    charger_mouvements("1' OR '1'='1", lecteur=lambda s, q: vues.setdefault("q", q))
    entre_parentheses = vues["q"].split("IN (")[1].split(")")[0]
    # Une seule valeur, entre deux quotes, et pas une quote de plus : le
    # litteral ne peut pas se refermer.
    assert entre_parentheses.count("'") == 2, entre_parentheses
```

Ajouter `charger_mouvements` à la liste d'imports en tête de `tests/test_live_data.py`.

- [ ] **Step 2: Lancer les tests et vérifier qu'ils échouent**

```bash
$PY -m pytest tests/test_live_data.py -k charger_mouvements -v
```

Attendu : **collection error** — `ImportError: cannot import name 'charger_mouvements' from 'live_data'`.

- [ ] **Step 3: Implémenter**

Insérer dans `live_data.py`, juste après `charger_serie` :

```python
#: Les seules colonnes dont le SENS d'un prix a besoin. `SELECT *` en lisait
#: quatorze pour en utiliser six.
COLONNES_MOUVEMENT = ("event_id", "ts", "back_odds_a", "lay_odds_a",
                      "back_odds_b", "lay_odds_b")


def charger_mouvements(event_id, lecteur=None) -> pd.DataFrame:
    """Ce qu'il faut, et rien de plus, pour dire quels prix remuent.

    La liste appelait ``charger_serie`` pour toute la liste des matchs en
    cours, uniquement pour nourrir ``mouvements_de_prix``. Mesure du
    2026-08-10 : 341 ms, dont 48 de SQL et **289 de fusion** -- 85 % du cycle
    dans une boucle pandas ligne a ligne. Or la liste n'a jamais eu besoin de
    la fusion : ``mouvements_de_prix`` regroupe par ``event_id``, et
    ``lignes()`` refusionne ensuite les identifiants d'un meme match. Et la
    fusion, appliquee a plusieurs matchs, DETRUISAIT l'information (cf.
    ``fusionner_series``). Ce lecteur-ci : 16 ms.

    La fenetre temporelle n'est volontairement PAS reduite. ``live_series``
    ecrit au CHANGEMENT et non a cadence fixe -- ecarts medians de 8 a 101 s
    selon le match, trous mesures jusqu'a 1354 s. Une fenetre de dix minutes
    perdrait le releve de reference d'avant la fenetre de mouvement, donc des
    fleches. La lenteur n'etait pas dans le volume lu.

    ``lecteur`` est injectable pour les tests ; en service il vaut
    ``read_sql_query``. Import differe, meme motif que ``charger_serie``.
    """
    lire = lecteur if lecteur is not None else _lecteur_par_defaut()
    surs = _identifiants_surs(event_id)
    if not surs:
        return pd.DataFrame()
    liste = _litteral_liste(surs)
    df = lire(
        SCHEMA,
        f"SELECT {', '.join(COLONNES_MOUVEMENT)} FROM live_series "
        f"WHERE event_id IN ({liste}) ORDER BY ts",
    )
    return df if df is not None else pd.DataFrame()
```

- [ ] **Step 4: Lancer la suite**

```bash
$PY -m pytest tests/ -q
```
Attendu : `303 passed`.

- [ ] **Step 5: Commit**

```bash
git add live_data.py tests/test_live_data.py
git commit -m "feat: un lecteur qui ne rapporte que le sens des prix

341 ms pour la liste, dont 289 en fusion -- une fusion dont elle n'avait pas
besoin et qui, sur plusieurs matchs, detruisait l'information. Six colonnes,
aucun repli : 16 ms mesurees."
```

---

### Task 3 : la liste cesse d'appeler `charger_serie`

**Files:**
- Modify: `pages/live.py:207-209`
- Test: `tests/test_pages_live.py`

**Interfaces:**
- Consumes: `charger_mouvements` (Task 2), `fusionner_series(..., famille=...)` (Task 1).

- [ ] **Step 1: Écrire le test qui échoue**

Ce test prouve l'effet visible du défaut : les six matchs gardent leur flèche. Ajouter à `tests/test_pages_live.py`. Lire d'abord les 60 premières lignes du fichier pour reprendre son mécanisme d'injection (`live_data` est monkeypatché module-level, `html_liste(at)` concatène le HTML rendu).

```python
def test_les_six_matchs_gardent_leur_FLECHE(monkeypatch):
    """Le defaut du 2026-08-10 : la page passait les six matchs a
    `charger_serie`, dont la fusion groupait sur `ts` seul. Le publieur les
    ecrit dans le meme cycle, au meme instant -- trois matchs sur six
    perdaient leur fleche, et l'une des trois restantes pointait a l'envers.

    On regarde le HTML REELLEMENT pousse, pas un calcul rejoue.
    """
    maintenant = time.time()
    matchs = pd.DataFrame([
        {**LIGNE_REELLE_INPLAY, "event_id": str(i), "event_ids": str(i),
         "participant1": f"J{i}a", "participant2": f"J{i}b",
         "updated_ts": maintenant}
        for i in range(6)
    ])
    # Chaque match a bouge : un releve avant la fenetre de deux minutes, un
    # dedans, tous au MEME horodatage d'un match a l'autre -- c'est la
    # collision que le publieur produit reellement.
    releves = []
    for i in range(6):
        releves.append({"event_id": str(i), "ts": maintenant - 300,
                        "back_odds_a": 2.0, "lay_odds_a": 2.1,
                        "back_odds_b": 2.0, "lay_odds_b": 2.1})
        releves.append({"event_id": str(i), "ts": maintenant - 10,
                        "back_odds_a": 3.0, "lay_odds_a": 3.1,
                        "back_odds_b": 1.5, "lay_odds_b": 1.6})
    serie = pd.DataFrame(releves)

    monkeypatch.setattr(live_data, "charger_matchs", lambda *a, **k: matchs)
    monkeypatch.setattr(live_data, "charger_mouvements", lambda *a, **k: serie)

    at = AppTest.from_file("pages/live.py", default_timeout=30)
    at.session_state["logged_in"] = True
    at.run()
    html = html_liste(at)
    assert html.count("hausse") >= 6, \
        f"tous les matchs doivent porter une hausse, vu {html.count('hausse')}"
    assert html.count("baisse") >= 6, \
        f"tous les matchs doivent porter une baisse, vu {html.count('baisse')}"
```

**Note pour l'implémenteur :** `test_pages_live.py` a déjà son propre mécanisme de substitution de `charger_matchs` (voir `_DERNIER` et les `monkeypatch` en place). **Reprendre le mécanisme existant du fichier** plutôt que celui esquissé ci-dessus s'ils diffèrent — le test doit ressembler à ses voisins.

- [ ] **Step 2: Vérifier qu'il échoue**

```bash
$PY -m pytest tests/test_pages_live.py -k FLECHE -v
```
Attendu : **FAIL** — la page appelle encore `charger_serie`, donc la substitution de `charger_mouvements` n'a aucun effet, et la fusion écrase les six matchs en un.

- [ ] **Step 3: Implémenter**

Dans `pages/live.py`, remplacer le bloc `try` des lignes 207-212 :

```python
        try:
            serie = charger_mouvements(",".join(en_cours["event_ids"].astype(str)))
            bouge = mouvements_de_prix(serie, maintenant)
        except Exception:
            # Le mouvement est un CONFORT : son absence ne doit pas emporter
            # la liste, qui elle porte le score et les prix.
            bouge = {}
```

Remplacer aussi le commentaire qui le précède (lignes 204-206) :

```python
        # Le SENS du dernier mouvement de chaque prix. Une seule requete pour
        # toute la liste, SANS repli : `charger_serie` fusionnait, ce qui
        # coutait 289 ms des 341 du cycle -- et surtout ecrasait 62 % des
        # lignes en prenant un horodatage commun pour un match commun. Six
        # colonnes, aucune fusion : 16 ms mesurees le 2026-08-10.
```

Et dans le bloc d'import en tête de fichier, ajouter `charger_mouvements` à la liste importée depuis `live_data` (garder l'ordre alphabétique du bloc existant : après `charger_matchs`).

- [ ] **Step 4: Vérifier**

```bash
$PY -m pytest tests/ -q
```
Attendu : `304 passed`.

- [ ] **Step 5: Commit**

```bash
git add pages/live.py tests/test_pages_live.py
git commit -m "fix: les six matchs de la liste retrouvent leur fleche

La liste lisait sa serie par charger_serie, dont la fusion prenait un
horodatage commun pour un match commun. Trois matchs sur six perdaient leur
fleche de mouvement, un quatrieme pointait a l'envers."
```

---

### Task 4 : la feuille du flux continu, et le CSS qui sort du fragment

**Files:**
- Create: `flux_continu.py`
- Create: `tests/test_flux_continu.py`
- Modify: `pages/live.py` (injection hors du fragment), `pages/match.py` (injection)

**Interfaces:**
- Produces: `flux_continu.CSS_FLUX: str` — la feuille de style à injecter une fois par page.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_flux_continu.py` :

```python
"""Le rafraichissement continu : ce qui empeche la page de se griser, et ce
qui remplace le signal ainsi supprime.

Ces tests gardent des SELECTEURS INTERNES a Streamlit, releves dans le bundle
1.52.2 et non de memoire. Une montee de version peut les deplacer : c'est
`tests/test_navigateur.py` qui le constatera, mais ceux-ci disent au moins ce
qu'on visait et pourquoi.
"""

from flux_continu import CSS_FLUX


def test_la_feuille_neutralise_le_GRISEMENT():
    """Streamlit 1.52.2 : STALE_STYLES = {opacity: .33} pose apres 500 ms sur
    tout `[data-testid="stElementContainer"][data-stale="true"]`. C'est ce
    grisement, et rien d'autre, qui donnait a la page son air de F5."""
    assert '[data-stale="true"]' in CSS_FLUX
    assert "opacity: 1 !important" in CSS_FLUX


def test_la_feuille_n_eteint_QUE_l_homme_qui_court():
    """Le meme widget porte « Connecting... » et l'avis de session perdue.
    Le masquer en entier echangerait une gene contre un silence dangereux."""
    assert '[data-testid="stStatusWidgetRunningIcon"]' in CSS_FLUX
    # La regle est portee par `:has()`, donc conditionnee a l'icone. Une
    # regle sur `.stStatusWidget` nu masquerait aussi la deconnexion.
    for ligne in CSS_FLUX.splitlines():
        if "stStatusWidget" in ligne and "display" in ligne:
            assert ":has(" in ligne, f"regle trop large : {ligne.strip()}"
```

- [ ] **Step 2: Vérifier l'échec**

```bash
$PY -m pytest tests/test_flux_continu.py -v
```
Attendu : **collection error** — `ModuleNotFoundError: No module named 'flux_continu'`.

- [ ] **Step 3: Implémenter**

Créer `flux_continu.py` :

```python
"""Le rafraichissement qui ne se voit pas -- et le battement qui le remplace.

La page « En direct » se grisait entierement toutes les quinze secondes, puis
se rallumait. Ce n'etait PAS un rechargement : c'est un comportement du
frontal Streamlit, lisible dans son bundle 1.52.2 --

    STALE_TRANSITION_PARAMS = "1s ease-in 0.5s"
    STALE_STYLES = { opacity: .33, transition: `opacity 1s ease-in 0.5s` }

Des qu'un rerun passe 500 ms, tout element pas encore recalcule descend a 33 %
d'opacite. Le cycle en coutait ~350 -- juste sous le seuil, d'ou une gene
intermittente qui s'aggravait avec le nombre de matchs, c'est-a-dire les soirs
ou l'on regarde.

Ce module vit a part de `liste_dense` : il sert AUSSI `pages/match.py`, qui ne
dessine aucune liste. L'ecrire deux fois garantirait qu'une correction
n'atterrisse que d'un cote -- la regle que ce depot tient deja pour
`detail_match`.
"""

CSS_FLUX = """
<style>
  /* Le grisement de Streamlit, eteint. L'ancien contenu reste PLEINEMENT
     lisible jusqu'a ce que le nouveau le remplace : c'est tout ce que
     « streaming » veut dire ici. Les 289 ms de fusion supprimees par
     ailleurs mettent deja le cycle sous le seuil des 500 ms -- cette regle
     est la ceinture, et elle tient seule les soirs a quarante matchs. */
  [data-testid="stElementContainer"][data-stale="true"] {
    opacity: 1 !important; transition: none !important;
  }
  /* L'homme qui court, et LUI SEUL. Le meme widget porte « Connecting... »
     et l'avis de session perdue : le masquer en entier echangerait une gene
     contre un silence dangereux. */
  .stStatusWidget:has([data-testid="stStatusWidgetRunningIcon"]) { display: none; }
</style>
"""
```

- [ ] **Step 4: Vérifier**

```bash
$PY -m pytest tests/test_flux_continu.py -v
```
Attendu : `2 passed`.

- [ ] **Step 5: Brancher les deux pages**

Dans `pages/live.py` : ajouter l'import `from flux_continu import CSS_FLUX`, puis **après le bloc de connexion** (le `st.stop()` de la ligne 42, pour ne rien injecter à un visiteur non connecté) et avant la définition des cadences :

```python
# La feuille du flux continu et celle de la liste sont injectees UNE fois,
# au chargement. Elles vivaient dans le fragment, donc reemises a chaque
# cycle : un `<style>` de plus toutes les quinze secondes, pour un resultat
# identique.
st.markdown(CSS_FLUX, unsafe_allow_html=True)
st.markdown(CSS, unsafe_allow_html=True)
```

Et **supprimer** la ligne `st.markdown(CSS, unsafe_allow_html=True)` qui se trouve dans `zone_donnees` (ligne 197).

Dans `pages/match.py` : ajouter `from flux_continu import CSS_FLUX` au bloc d'imports, et l'injecter une fois juste avant l'appel `niveau_1()` :

```python
# Le detail se rafraichit tout seul lui aussi : meme grisement, meme remede.
st.markdown(CSS_FLUX, unsafe_allow_html=True)
```

- [ ] **Step 6: Vérifier la suite entière**

```bash
$PY -m pytest tests/ -q
```
Attendu : `306 passed`. Si `tests/test_pages_match.py` compte les éléments markdown de la page, il faudra ajuster son compte — c'est une conséquence attendue, pas une régression.

- [ ] **Step 7: Commit**

```bash
git add flux_continu.py tests/test_flux_continu.py pages/live.py pages/match.py
git commit -m "feat: la page cesse de se griser a chaque cycle

STALE_STYLES du frontal Streamlit descend a 33 % d'opacite des qu'un rerun
passe 500 ms. Une regle l'eteint ; une autre eteint l'homme qui court sans
toucher a l'avis de deconnexion, porte par le meme widget.

Le CSS de la liste sort du fragment au passage : il etait reemis a chaque
cycle pour un resultat identique."
```

---

### Task 5 : le battement

**Files:**
- Modify: `flux_continu.py` (ajout de `bandeau_battement` et de son style)
- Modify: `pages/live.py` (remplace la légende de la ligne 199-202)
- Test: `tests/test_flux_continu.py`

**Interfaces:**
- Produces: `flux_continu.bandeau_battement(n_matchs: int, maintenant: float) -> str` — un fragment HTML.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
import pandas as pd

from flux_continu import CSS_FLUX, bandeau_battement


def test_le_bandeau_porte_l_HEURE_du_chargement():
    """Supprimer le grisement supprime le seul signe que les donnees bougent.
    L'heure affichee est celle du chargement REUSSI cote serveur : si le
    cycle s'arrete, elle se fige, et ca se voit."""
    html = bandeau_battement(6, 1786352606.0)
    attendue = pd.to_datetime(1786352606.0, unit="s").strftime("%H:%M:%S")
    assert attendue in html
    assert "6" in html


def test_le_bandeau_s_accorde_avec_la_colonne_HEURE_de_la_liste():
    """Les deux doivent lire l'horodatage de la meme facon, sans quoi un
    match paraitrait commencer apres l'heure affichee en tete de page."""
    from liste_dense import _heure

    assert _heure(1786352606.0)[:5] in bandeau_battement(1, 1786352606.0)


def test_le_battement_rejoue_a_CHAQUE_cycle():
    """Une animation posee sur un element que Streamlit RECREE a chaque cycle
    rejoue a chaque cycle : c'est un battement. Une boucle infinie
    (`animation-iteration-count: infinite`) tournerait aussi sur une page
    morte et ne prouverait rien."""
    assert "@keyframes battement" in CSS_FLUX
    assert "infinite" not in CSS_FLUX
```

- [ ] **Step 2: Vérifier l'échec**

```bash
$PY -m pytest tests/test_flux_continu.py -v
```
Attendu : `ImportError: cannot import name 'bandeau_battement'`.

- [ ] **Step 3: Implémenter**

Dans `flux_continu.py`, ajouter `import html` et `import pandas as pd` en tête, puis :

```python
def bandeau_battement(n_matchs: int, maintenant: float) -> str:
    """Le signal de vie qui remplace le grisement.

    Une pastille qui bat une fois par cycle et l'heure du dernier chargement
    reussi. L'animation est posee sur un element que Streamlit RECREE a chaque
    cycle : elle rejoue donc a chaque cycle, et seulement alors. Une boucle
    infinie tournerait aussi sur une page morte, et ne dirait rien.

    L'heure vient de `maintenant`, l'instant du chargement cote serveur, et
    se lit avec le meme idiome que la colonne « heure » de la liste
    (`liste_dense._heure`) : les deux doivent s'accorder, sans quoi un match
    paraitrait commencer apres l'heure affichee en tete de page.
    """
    heure = pd.to_datetime(float(maintenant), unit="s").strftime("%H:%M:%S")
    return (f'<div class="battement"><u></u><span>{html.escape(heure)}</span>'
            f'<span>· {int(n_matchs)} match(s) en cours</span></div>')
```

Et dans `CSS_FLUX`, avant la balise `</style>` fermante :

```css
  /* Le battement. Il joue UNE fois, a la creation de l'element -- donc une
     fois par cycle. */
  @keyframes battement {
    0% { opacity: .2; } 12% { opacity: 1; } 100% { opacity: .2; }
  }
  .battement {
    display: flex; align-items: baseline; gap: .5rem;
    font-size: .82rem; opacity: .75; margin: 0 0 .5rem .1rem;
  }
  .battement u {
    width: .5rem; height: .5rem; border-radius: 50%;
    background: #32b296; text-decoration: none;
    animation: battement 1s ease-out;
  }
```

- [ ] **Step 4: Vérifier**

```bash
$PY -m pytest tests/test_flux_continu.py -v
```
Attendu : `5 passed`.

- [ ] **Step 5: Brancher la page**

Dans `pages/live.py`, remplacer la légende (lignes 199-202) :

```python
    if not en_cours.empty:
        st.markdown(bandeau_battement(len(en_cours), maintenant),
                    unsafe_allow_html=True)
        st.caption("Cliquez une ligne pour ouvrir son detail.")
```

Ajouter `bandeau_battement` à l'import depuis `flux_continu`.

- [ ] **Step 6: Vérifier la suite**

```bash
$PY -m pytest tests/ -q
```
Attendu : `309 passed`. Si un test de `test_pages_live.py` cherche la chaîne `"match(s) en cours"` dans une légende (`at.caption`), il la trouvera désormais dans un markdown : ajuster ce test, en gardant l'assertion sur ce qui est affiché.

- [ ] **Step 7: Commit**

```bash
git add flux_continu.py tests/test_flux_continu.py pages/live.py
git commit -m "feat: un battement remplace le grisement comme signe de vie

Une pastille qui bat une fois par cycle et l'heure du dernier chargement
reussi. L'animation vit sur un element que Streamlit recree a chaque cycle :
elle ne peut pas battre sur une page morte."
```

---

### Task 6 : le surlignage de ce qui vient de changer

**Files:**
- Modify: `flux_continu.py` (`instantane`, `marquer_changements`, styles)
- Modify: `liste_dense.py` (`_prix`, `rendu`)
- Modify: `pages/live.py` (mémoire de session)
- Test: `tests/test_flux_continu.py`

**Interfaces:**
- Produces: `flux_continu.instantane(structure: list) -> dict` — `{event_ids: [{"jeux": tuple, "point": str, "back": float|None, "lay": float|None}, ...]}`
- Produces: `flux_continu.marquer_changements(structure: list, vu: dict) -> list` — pose les clés booléennes `neuf_jeux`, `neuf_point`, `neuf_back`, `neuf_lay` sur chaque joueur ; **mute la structure et la rend**.
- Consumes (par `liste_dense.rendu`) : ces quatre clés, lues avec `.get()` — une structure jamais marquée reste rendue à l'identique.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
from flux_continu import instantane, marquer_changements


def _ligne(event_ids="A", jeux=("6", "4"), point="30", back=2.0, lay=2.1):
    return {
        "event_ids": event_ids,
        "joueurs": [
            {"jeux": list(jeux), "point": point, "back": back, "lay": lay},
            {"jeux": list(jeux), "point": "0", "back": 1.8, "lay": 1.9},
        ],
    }


def test_le_PREMIER_rendu_n_allume_rien():
    """Sans instantane precedent il n'y a rien a comparer. Marquer tout
    ferait s'allumer la liste entiere a l'ouverture, et le signal ne voudrait
    plus rien dire."""
    structure = [_ligne()]
    marquer_changements(structure, {})
    for joueur in structure[0]["joueurs"]:
        assert not any(joueur.get(c) for c in
                       ("neuf_jeux", "neuf_point", "neuf_back", "neuf_lay"))


def test_seule_la_valeur_qui_a_CHANGE_s_allume():
    vu = instantane([_ligne(point="30", back=2.0)])
    structure = [_ligne(point="40", back=2.0)]
    marquer_changements(structure, vu)
    j = structure[0]["joueurs"][0]
    assert j["neuf_point"] is True, "le point a change"
    assert j["neuf_back"] is False, "la cote back n'a pas bouge"
    assert j["neuf_jeux"] is False


def test_une_cote_ABSENTE_ne_clignote_pas_indefiniment():
    """NaN != NaN : compare brut, une cote absente paraitrait changer a
    chaque cycle et la ligne battrait sans fin."""
    vu = instantane([_ligne(back=float("nan"))])
    structure = [_ligne(back=float("nan"))]
    marquer_changements(structure, vu)
    assert structure[0]["joueurs"][0]["neuf_back"] is False


def test_un_match_NOUVEAU_n_est_pas_un_changement():
    """Un match qui entre dans la liste n'a rien « change » : il arrive."""
    vu = instantane([_ligne(event_ids="A")])
    structure = [_ligne(event_ids="B", point="40")]
    marquer_changements(structure, vu)
    assert not structure[0]["joueurs"][0].get("neuf_point")


def test_le_surlignage_joue_une_SEULE_fois():
    assert "@keyframes surlignage" in CSS_FLUX
    assert ".neuf" in CSS_FLUX
```

Le drapeau ne suffit pas : c'est le HTML qu'on regarde à l'écran. Deux tests de plus, dans le même fichier :

```python
def test_le_rendu_pose_la_classe_sur_la_seule_cellule_neuve():
    """La preuve doit porter sur le HTML POUSSE, pas sur le drapeau : c'est
    le HTML qu'on regarde a l'ecran."""
    from liste_dense import rendu

    structure = [{
        "event_id": "A", "event_ids": "A", "debut": 1786352606.0,
        "competition": "ATP", "tournoi": "Test",
        "joueurs": [
            {"nom": "A", "sert": True, "jeux": ["6"], "point": "40",
             "back": 2.0, "lay": 2.1, "bp": False,
             "mvt_back": None, "mvt_lay": None, "neuf_back": True},
            {"nom": "B", "sert": False, "jeux": ["4"], "point": "0",
             "back": 1.8, "lay": 1.9, "bp": False,
             "mvt_back": None, "mvt_lay": None},
        ],
        "ecarts": [1, 1], "fraicheur": [], "morts": [],
    }]
    html = rendu(structure)
    assert html.count("neuf") == 1, "une seule cellule doit s'allumer"
    # Aucune fleche sur ce prix : la classe est donc exactement « b neuf ».
    assert 'class="b neuf"' in html, html


def test_une_structure_jamais_marquee_est_rendue_a_l_identique():
    """`rendu` sert aussi `pages/match.py` et deux bancs de test qui
    n'appellent jamais `marquer_changements`."""
    from liste_dense import lignes, rendu
    import pandas as pd, time

    df = pd.DataFrame([{
        "event_id": "A", "participant1": "A", "participant2": "B",
        "score": "6-4", "points": "30-0", "server": "0",
        "back_odds_a": 2.0, "lay_odds_a": 2.1,
        "back_odds_b": 1.8, "lay_odds_b": 1.9,
        "league": "Test", "tour_type": "atp", "start_timestamp": time.time(),
        "status": "InPlay", "updated_ts": time.time(),
    }])
    assert "neuf" not in rendu(lignes(df, time.time()))
```

- [ ] **Step 2: Vérifier l'échec**

```bash
$PY -m pytest tests/test_flux_continu.py -v
```
Attendu : `ImportError: cannot import name 'instantane'`.

- [ ] **Step 3: Implémenter `flux_continu`**

Ajouter à `flux_continu.py` :

```python
def _valeur(v):
    """Un prix comparable d'un cycle a l'autre.

    `NaN != NaN` : compare brut, une cote absente paraitrait changer a chaque
    cycle et sa ligne battrait sans fin.
    """
    if v is None or (isinstance(v, float) and v != v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def instantane(structure) -> dict:
    """Les valeurs volatiles telles qu'on vient de les afficher.

    Le diff se fait cote SERVEUR : `st.markdown` n'execute pas de `<script>`,
    il n'y a pas d'autre voie. Le cout est une comparaison de dictionnaires --
    sans rapport avec les 289 ms de `fusionner_series`, qui etait une boucle
    `iterrows` sur un millier de lignes.
    """
    return {
        ligne["event_ids"]: [
            {"jeux": tuple(j["jeux"]), "point": j["point"],
             "back": _valeur(j["back"]), "lay": _valeur(j["lay"])}
            for j in ligne["joueurs"]
        ]
        for ligne in structure
    }


def marquer_changements(structure, vu: dict):
    """Pose `neuf_*` sur les seules valeurs qui ont change depuis le dernier
    affichage.

    `vu` vide -- premier rendu -- ne marque RIEN : marquer tout ferait
    s'allumer la liste entiere a l'ouverture, et le signal ne voudrait plus
    rien dire. Un match qui ENTRE dans la liste n'a rien change non plus : il
    arrive.

    Ce surlignage ne remplace pas les fleches `hausse`/`baisse` : elles disent
    « ce prix a bouge dans les deux dernieres minutes », lui dit « ceci vient
    de changer sous tes yeux ». Deux echelles de temps, deux marques.
    """
    if not vu:
        return structure
    for ligne in structure:
        avant = vu.get(ligne["event_ids"])
        if not avant:
            continue
        for rang, j in enumerate(ligne["joueurs"]):
            if rang >= len(avant):
                continue
            a = avant[rang]
            j["neuf_jeux"] = tuple(j["jeux"]) != a["jeux"]
            j["neuf_point"] = j["point"] != a["point"]
            j["neuf_back"] = _valeur(j["back"]) != a["back"]
            j["neuf_lay"] = _valeur(j["lay"]) != a["lay"]
    return structure
```

Et dans `CSS_FLUX`, avant `</style>` :

```css
  /* Ce qui vient de changer s'allume une demi-seconde, puis s'eteint. Pose
     sur un element que Streamlit recree : joue une fois, au bon moment. */
  @keyframes surlignage {
    from { background: rgba(50,178,150,0.30); }
    to   { background: transparent; }
  }
  .liste-dense .neuf {
    animation: surlignage .6s ease-out; border-radius: .2rem;
  }
```

- [ ] **Step 4: Implémenter le rendu**

Dans `liste_dense.py`, `_prix` accepte un drapeau :

```python
def _prix(valeur, classe: str, mouvement=None, neuf: bool = False) -> str:
    """Un prix. La lettre « b »/« l » et la fleche viennent de la feuille de
    style : ce sont des redondances visuelles, pas du contenu.

    La lettre double la couleur -- back et lay ne doivent pas se distinguer
    par la seule teinte, sinon un daltonien lit le carnet a l'envers.

    `neuf` marque ce qui vient de changer depuis le dernier affichage. La
    fleche, elle, porte les deux dernieres minutes : deux echelles de temps,
    deux marques.
    """
    if valeur is None or pd.isna(valeur):
        return '<i class="vide">—</i>'
    bouge = f" {mouvement}" if mouvement in ("hausse", "baisse") else ""
    frais = " neuf" if neuf else ""
    return f'<i class="{classe}{bouge}{frais}">{float(valeur):.2f}</i>'
```

Dans `rendu`, remplacer les constructions `points`, `prix` et `jeux` :

```python
        jeux = "".join(
            f'<span><em>{"🎾" if j["sert"] else ""}</em>'
            + '<span class="cases">' + "".join(
                f'<b class="{"encours" if i == n_sets - 1 else ""}'
                f'{" neuf" if j.get("neuf_jeux") and i == n_sets - 1 else ""}">'
                f'{e(v)}</b>'
                for i, v in enumerate(j["jeux"])
            ) + "</span></span>"
            for j in ligne["joueurs"]
        )
```

```python
        points = "".join(
            f'<span class="bp{" neuf" if j.get("neuf_point") else ""}">'
            f'{e(j["point"])}</span>' if j["bp"]
            else f'<span class="{"neuf" if j.get("neuf_point") else ""}">'
                 f'{e(j["point"])}</span>'
            for j in ligne["joueurs"]
        )
        prix = "".join(
            "<span>" + _prix(j["back"], "b", j.get("mvt_back"), j.get("neuf_back"))
            + _prix(j["lay"], "l", j.get("mvt_lay"), j.get("neuf_lay")) + "</span>"
            for j in ligne["joueurs"]
        )
```

**Toutes les lectures passent par `.get()`** : une structure jamais marquée est rendue exactement comme avant, ce que garantit `test_une_structure_jamais_marquee_est_rendue_a_l_identique`.

- [ ] **Step 5: Vérifier**

```bash
$PY -m pytest tests/test_flux_continu.py tests/test_live_data.py -v
```
Attendu : tout vert. L'assertion `html.count("neuf") == 1` est stricte à dessein : elle échoue aussi bien si rien ne s'allume que si tout s'allume, et le message d'échec porte le HTML pour qu'on voie lequel des deux.

- [ ] **Step 6: Brancher la mémoire de session**

Dans `pages/live.py`, dans `zone_donnees`, remplacer l'appel à `_dessiner` de la liste en cours :

```python
        structure = lignes(en_cours, maintenant, bouge)
        # La memoire vit dans la SESSION, une entree par section : les deux
        # listes de la page se marcheraient dessus en partageant la meme.
        marquer_changements(structure, st.session_state.get("vu_en_cours") or {})
        st.session_state["vu_en_cours"] = instantane(structure)
        _dessiner(structure, ouvert, "en-cours")
```

Et pour les matchs terminés, aucune mémoire : ils ne changent plus.

Ajouter `instantane, marquer_changements` à l'import depuis `flux_continu`.

- [ ] **Step 7: Vérifier la suite**

```bash
$PY -m pytest tests/ -q
```
Attendu : `316 passed`.

- [ ] **Step 8: Commit**

```bash
git add flux_continu.py liste_dense.py pages/live.py tests/test_flux_continu.py
git commit -m "feat: seul ce qui vient de changer s'allume

Un instantane des valeurs volatiles vit dans la session ; a chaque cycle on
compare, et la classe \`neuf\` ne tombe que sur les cellules qui ont bouge.
Le premier rendu n'allume rien -- sinon la liste entiere s'allumerait a
l'ouverture et le signal ne voudrait plus rien dire."
```

---

### Task 7 : la preuve au navigateur

Le §9 de la spec : le grisement **est une opacité**. Rien dans `AppTest` ne peut la voir. Et un test qui ne peut pas observer le défaut ne prouve rien — d'où **deux** bancs, l'un sans la feuille (témoin) et l'un avec.

**Files:**
- Modify: `tests/test_navigateur.py`

**Interfaces:**
- Consumes: `flux_continu.CSS_FLUX` (Task 4).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `tests/test_navigateur.py` :

```python
#: Un banc qui GRISE : un fragment dont le cycle depasse deliberement les
#: 500 ms du seuil. Sans ce depassement, Streamlit ne grise pas et le test
#: serait vert sans rien prouver. `{feuille}` recoit CSS_FLUX ou rien.
BANC_FLUX = '''
import sys, time
sys.path.insert(0, {racine!r})
import streamlit as st
from flux_continu import CSS_FLUX

st.set_page_config(layout="wide")
if {avec_feuille}:
    st.markdown(CSS_FLUX, unsafe_allow_html=True)

@st.fragment(run_every=2)
def zone():
    # 1,2 s : bien au-dela des 500 ms apres lesquelles STALE_STYLES tombe.
    time.sleep(1.2)
    st.markdown("<div class='temoin'>" + str(time.time()) + "</div>",
                unsafe_allow_html=True)

zone()
st.write("banc de grisement")
'''

#: L'opacite REELLEMENT calculee sur les conteneurs que Streamlit a marques
#: perimes, et la presence de l'homme qui court.
OPACITE = """
(() => {
  const p = [...document.querySelectorAll(
      '[data-testid="stElementContainer"][data-stale="true"]')];
  return {
    perimes: p.length,
    mini: p.length ? Math.min(...p.map(e => +getComputedStyle(e).opacity)) : null,
    court: !!document.querySelector('[data-testid="stStatusWidgetRunningIcon"]'),
  };
})()
"""


def _banc_flux(tmp_path_factory, avec_feuille):
    """Sert le banc, echantillonne l'opacite pendant plusieurs cycles.

    On ECHANTILLONNE plutot qu'on ne mesure une fois : le grisement n'existe
    qu'entre la 500e milliseconde d'un cycle et sa fin. Une mesure unique
    tomberait presque toujours a cote.
    """
    dossier = tmp_path_factory.mktemp("banc-flux")
    app = dossier / "banc.py"
    app.write_text(BANC_FLUX.format(racine=str(RACINE),
                                    avec_feuille="True" if avec_feuille else "False"))
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
        for _ in range(40):
            time.sleep(0.5)
            if nav.js("document.querySelectorAll('.temoin').length"):
                break
        else:
            pytest.skip("le banc n'a jamais rendu")
        vus, mini, court = 0, 1.0, False
        for _ in range(90):          # ~9 s, soit quatre cycles de 2 s
            m = nav.js(OPACITE)
            if m["perimes"]:
                vus += 1
                if m["mini"] is not None:
                    mini = min(mini, m["mini"])
            court = court or m["court"]
            time.sleep(0.1)
        return {"echantillons_perimes": vus, "opacite_mini": mini, "court": court}
    finally:
        if nav is not None:
            nav.fermer()
        serveur.terminate()
        serveur.wait(timeout=15)


def test_le_banc_VOIT_le_grisement_sans_la_feuille(tmp_path_factory):
    """Le temoin. Sans lui, le test suivant serait vert meme si le banc etait
    incapable d'observer quoi que ce soit -- et « un test qui n'a jamais ete
    rouge ne prouve rien ».

    Mesure du frontal 1.52.2 : STALE_STYLES = {opacity: .33} apres 500 ms.
    """
    m = _banc_flux(tmp_path_factory, avec_feuille=False)
    assert m["echantillons_perimes"] > 0, \
        "le banc n'a jamais vu un conteneur perime : il ne prouve rien"
    assert m["opacite_mini"] < 0.9, \
        f"le grisement ne se produit pas (opacite mini {m['opacite_mini']})"


def test_la_feuille_ETEINT_le_grisement(tmp_path_factory):
    """Le defaut signale : la page se grisait entierement toutes les quinze
    secondes, ce qui lui donnait un air de F5 sans qu'aucun rechargement
    n'ait lieu."""
    m = _banc_flux(tmp_path_factory, avec_feuille=True)
    assert m["echantillons_perimes"] > 0, \
        "aucun conteneur perime : la feuille n'a rien eu a eteindre"
    assert m["opacite_mini"] >= 1.0, \
        f"un conteneur est descendu a {m['opacite_mini']} d'opacite"


def test_l_homme_qui_court_ne_se_montre_plus(tmp_path_factory):
    """Et l'avis de deconnexion, porte par le MEME widget, reste possible :
    la regle est conditionnee a l'icone par `:has()`."""
    assert not _banc_flux(tmp_path_factory, avec_feuille=True)["court"]
```

- [ ] **Step 2: Vérifier l'échec**

```bash
$PY -m pytest tests/test_navigateur.py -k "grisement or homme" -v
```

Attendu : le témoin **passe** (il prouve que le banc voit le défaut), les deux autres **échouent** si l'on retire temporairement l'injection de `CSS_FLUX` — mais comme Task 4 est déjà faite, ils devraient passer directement.

**Contrôle obligatoire :** faire échouer volontairement `test_la_feuille_ETEINT_le_grisement` en commentant les deux règles de `CSS_FLUX`, vérifier qu'il devient ROUGE, puis rétablir. Un test qui n'a jamais été rouge ne prouve rien.

**Si `test_le_banc_VOIT_le_grisement_sans_la_feuille` échoue** (`echantillons_perimes == 0`), s'arrêter et le signaler : cela voudrait dire que Streamlit ne marque pas périmés les éléments d'un fragment, et toute la Task 4 reposerait alors sur une lecture erronée du frontal. Ne pas affaiblir l'assertion pour passer outre.

- [ ] **Step 3: Vérifier la suite entière**

```bash
$PY -m pytest tests/ -q
```
Attendu : `319 passed`. Ces trois tests ajoutent ~30 s : c'est le prix d'un vrai navigateur, déjà payé par les huit tests existants du fichier.

- [ ] **Step 4: Commit**

```bash
git add tests/test_navigateur.py
git commit -m "test: la preuve que la page ne se grise plus

Le grisement EST une opacite : rien dans AppTest ne peut le voir. Deux
bancs, dont un temoin SANS la feuille -- sans lui, le test serait vert meme
si le banc etait incapable d'observer quoi que ce soit."
```

---

## Vérification finale

- [ ] **Suite complète, arbre propre**

```bash
$PY -m pytest tests/ -q
git status --short
```
Attendu : `319 passed`, aucun fichier non commité.

- [ ] **Regarder la page tourner**

Lancer l'application, ouvrir « En direct », choisir la cadence 5 s et observer un match qui bouge :

```bash
$PY -m streamlit run app.py --server.port 8501 --server.headless true
```

Trois choses à constater de l'œil, qu'aucun test ne remplace :
1. la page ne se grise plus à aucun moment ;
2. la pastille du bandeau bat une fois par cycle, et l'heure avance ;
3. un score ou une cote qui change s'allume brièvement — et **seul** lui.

Le point 3 est celui où le dessin peut décevoir : durée, teinte, quelles cellules. C'est une préférence, pas un défaut, et elle se règle en regardant la page.

## Self-review du plan

**Couverture de la spec :**

| § de la spec | tâche |
|---|---|
| §1 le grisement, seuil de 500 ms | Task 4 |
| §2 les 289 ms de fusion | Task 2, Task 3 |
| §3 le défaut de `fusionner_series` | Task 1 |
| §4 l'appartenance déclarée | Task 1 |
| §5 le lecteur dédié, fenêtre non réduite | Task 2, Task 3 |
| §6 la feuille, `:has()`, constante partagée | Task 4 |
| §7 battement + surlignage | Task 5, Task 6 |
| §8 portée `live.py` + `match.py` | Task 4 (match.py reçoit §6 seul) |
| §9 vérification, test rouge d'abord | Task 1 step 2, Task 7 |
| §10 hors périmètre | aucune tâche — c'est le but |

**Cohérence des noms :** `fusionner_series(df, famille=...)`, `charger_mouvements(event_id, lecteur=None)`, `COLONNES_MOUVEMENT`, `CSS_FLUX`, `bandeau_battement(n_matchs, maintenant)`, `instantane(structure)`, `marquer_changements(structure, vu)`, clés `neuf_jeux` / `neuf_point` / `neuf_back` / `neuf_lay`. Employés à l'identique d'une tâche à l'autre.

**Points où l'implémenteur doit s'arrêter plutôt que contourner :**
- Task 1 step 2 — si le test de régression est vert d'emblée.
- Task 7 step 2 — si le banc témoin ne voit pas le grisement.

Dans les deux cas, la mesure qui fonde le plan serait fausse, et il faut le dire plutôt que d'ajuster l'assertion.
