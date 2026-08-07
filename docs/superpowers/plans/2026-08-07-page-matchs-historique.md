# Page « Match » — parcours du passé et bilan de collecte — plan

> **Pour les agents :** SOUS-COMPÉTENCE REQUISE — `superpowers:subagent-driven-development`.

**But :** faire de `pages/match.py` un écran à deux niveaux — le bilan de
collecte et la liste filtrable des matchs passés, puis le détail du match
choisi.

**Spec :** `docs/superpowers/specs/2026-08-07-page-matchs-historique-design.md`.
Elle fait foi ; ce plan ne fait que l'exécuter.

**Pile :** Streamlit, pandas, MySQL `TeNNet_test` en LECTURE SEULE.

## Contraintes globales

- **Aucune écriture en base.** La page lit. Le schéma `TeNNet_test` est
  partagé avec le PoC ; le schéma `TeNNet` est celui de la production et n'est
  jamais touché.
- **Aucun indicateur recalculé** : `Live/qa_report.py` les calcule déjà et les
  écrit dans `live_qa_daily`. Les recalculer créerait deux vérités qui
  divergeraient.
- **TDD strict, puis MUTATION TESTING.**
- **Fixtures PRÉLEVÉES sur la base réelle**, jamais inventées, et
  **DISCRIMINANTES**. Le dépôt a déjà ses fixtures réelles dans
  `tests/fixtures_reelles.py`.
- **Le dépôt GitHub est PUBLIC** et un push sur `main` déclenche un
  déploiement. Aucune donnée de pari, aucun identifiant de compte, aucun
  secret dans une fixture.
- Commentaires et texte source en **français sans accents** ; l'affichage
  utilisateur les porte.
- Interpréteur :
  `/home/ubuntu/.cache/pypoetry/virtualenvs/tennet-BfZcHEB2-py3.12/bin/python`
- Suite : `python -m pytest tests/ -q` — **222 verts** au départ.

## Les tables, telles qu'elles sont

```
live_qa_daily   (10 l., 10 j.) day, n_markets, n_matched, match_rate,
                n_pbp_common, n_pbp_ok, pbp_coherence, gap_seconds,
                inplay_seconds, gap_ratio, n_inversions, api_calls
live_matches    (1153 l., 10 j.) day, event_id, match_id, id_market, ID_MATCH,
                participant1, participant2, p1_is_home, league, tour_type,
                start_ts, matched, ambiguous_market
live_points     (176 208 l., 10 j.) day, event_id, recv_ts, score, points,
                indicator, status
live_series     (45 178 l., ~2,6 j. SEULEMENT) event_id, ts, cotes...
```

---

### Tâche 1 : les trois lecteurs

**Fichiers :** `live_data.py`, `tests/test_live_data.py`

**Interfaces produites**, consommées par les tâches 2 à 4 :

```python
def charger_bilan_qa(lecteur=None) -> pd.DataFrame          # live_qa_daily
def charger_matchs_passes(lecteur=None) -> pd.DataFrame     # live_matches
def charger_points(event_id, lecteur=None) -> pd.DataFrame  # live_points
```

Suivre **exactement** le motif de `charger_matchs` (`live_data.py:706`) et
`charger_serie` (`live_data.py:730`) : `SCHEMA`, lecteur injectable, import
différé de `read_sql_query`.

**Le piège déjà payé sur `charger_serie`** (`live_data.py:754`) : `event_id`
vient de l'URL. Il est nettoyé de toutes ses apostrophes avant d'entrer dans
la requête. Reprendre la même précaution pour `charger_points`.

- [ ] **Étape 1** — les tests d'abord, avec un lecteur bouchonné qui distingue
  les tables par leur nom dans la requête, comme le fait déjà
  `tests/test_pages_match.py::_mock_lecteur`. Faire rougir.
- [ ] **Étape 2** — implémenter.
- [ ] **Étape 3** — mutations : `SCHEMA` remplacé par un littéral ; nettoyage
  d'apostrophe retiré ; table confondue avec une autre.
- [ ] **Étape 4** — commit.

---

### Tâche 2 : le bilan, et ses trois seuils

**Fichiers :** `live_data.py` (constantes + jugement), `bilan_collecte.py`
(nouveau, le rendu), `tests/test_bilan_collecte.py`

**Les seuils vivent dans un AUTRE dépôt** (`/home/ubuntu/TeNNetPy/Live/config.py`,
`QA_MIN_MATCH_RATE = 0.90`, `QA_MIN_PBP_COHERENCE = 0.95`,
`QA_MAX_GAP_RATIO = 0.05`) que la viz n'importe pas.

Il faut donc les dupliquer — **et le dépôt a déjà sa convention pour ça** :
`live_data.py:230`, `SEUIL_BATTEMENT_ARRETE_S`, duplique une constante du PoC
avec un commentaire qui nomme la source de vérité et dit que le couplage n'est
pas garanti. **Suivre ce précédent, commentaire compris.** Un seuil dupliqué
en silence dérive sans que personne ne le voie.

Le sens de chaque seuil, à écrire dans le code : `match_rate` et
`pbp_coherence` sont des **minima** (en dessous = mauvais), `gap_ratio` est un
**maximum** (au-dessus = mauvais). Se tromper de sens inverserait le verdict.

**Le piège du dénominateur nul.** Quatre jours (07-28 au 07-31) ont
`n_markets = 0` et `match_rate = NULL`. Ils doivent se lire **« pas de
mesure »**, jamais « 0 % ». Un jour sans mesure affiché comme un jour
catastrophique ferait fuir de la vraie information.

`n_inversions` vaut `None` sur **toutes** les lignes : ne pas afficher une
colonne vide comme si elle valait zéro.

- [ ] **Étape 1** — test : un jour à `n_markets = 0` ne rend PAS un verdict
  « hors seuil ». Faire rougir.
- [ ] **Étape 2** — test : `gap_ratio` à 0,516 est hors seuil (maximum à 0,05)
  ET `match_rate` à 0,653 est hors seuil (minimum à 0,90). Les deux sens.
- [ ] **Étape 3** — implémenter le jugement puis le rendu.
- [ ] **Étape 4** — mutations : les deux sens de seuil inversés (une mutation
  chacun) ; le dénominateur nul traité comme zéro ; un seuil changé de valeur.
- [ ] **Étape 5** — commit.

---

### Tâche 3 : la liste filtrable

**Fichiers :** `pages/match.py`, `tests/test_pages_match.py`

Filtres, **tous tirés des données, jamais codés en dur** : jour, circuit
(`atp`/`wta`), ligue (50 valeurs), apparié ou non.

**Les deux taux d'appariement ne se mélangent pas** (spec §4) : le 65 % du
bilan porte sur les **marchés vus en jeu, hors ambigus** ; le 36 % de la liste
porte sur **tous les matchs identifiés**. Chacun s'affiche avec son
dénominateur. Un test doit interdire qu'on présente l'un pour l'autre.

- [ ] **Étape 1** — test : les valeurs de filtre viennent des données (ajouter
  une ligue à la fixture la fait apparaître dans les choix). Faire rougir.
- [ ] **Étape 2** — test : filtrer sur un circuit ne laisse que lui.
- [ ] **Étape 3** — implémenter.
- [ ] **Étape 4** — mutations : liste de circuits codée en dur ; filtre
  inversé ; filtre ignoré.
- [ ] **Étape 5** — commit.

---

### Tâche 4 : le détail, en second niveau

**Fichiers :** `pages/match.py`, `tests/test_pages_match.py`

**Réutiliser `detail_match.afficher(m, serie, maintenant)`** — ne pas le
réécrire. On y arrive en choisissant dans la liste ; `st.query_params` reste
le support du choix, comme aujourd'hui.

**La limite dure de `live_series`** (~2,6 jours) : au-delà, il n'y a pas de
cotes. La page doit le **DIRE** — « pas de cotes conservées pour ce match, la
rétention est de 2,6 jours » — et **jamais** afficher un graphique vide. Une
absence silencieuse se lit comme une panne, et le dépôt tient à ce qu'une
source qui ne sait plus le dise.

Le point par point vient de `live_points` (10 jours), donc il reste
disponible quand les cotes ne le sont plus.

- [ ] **Étape 1** — test : un match ancien, sans série, affiche le message et
  pas un graphique vide. Faire rougir.
- [ ] **Étape 2** — test : un match récent affiche bien ses cotes.
- [ ] **Étape 3** — implémenter.
- [ ] **Étape 4** — mutations : message d'absence retiré ; graphique rendu
  malgré une série vide ; point par point non affiché quand les cotes manquent.
- [ ] **Étape 5** — commit.

---

### Tâche 5 : vérification en service

- [ ] Suite complète verte.
- [ ] Lancer un Streamlit **sur un port libre** (8502), jamais sur le 8501 qui
  est servi. Vérifier les deux niveaux sur les vraies données.
- [ ] Arrêter la fumée en visant **le PID exact du python** — `pkill` tuerait
  le shell appelant, et tuer l'enveloppe orphelinerait le python.
- [ ] **Ne pas pousser.** La mise en ligne est une décision du propriétaire ;
  le dépôt est public et un push sur `main` déclenche un déploiement.
