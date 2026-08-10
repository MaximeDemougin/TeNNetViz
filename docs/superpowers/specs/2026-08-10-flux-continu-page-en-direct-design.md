# « En direct » cesse de clignoter — et la fusion cesse de mentir — design du 2026-08-10

## 1. Le symptôme, et ce qu'il est vraiment

Toutes les quinze secondes, la page « En direct » se **grise entièrement**
pendant un instant, puis se rallume. L'effet ressemble à un F5. Ce n'en est
pas un : rien n'est rechargé, aucune session n'est perdue.

C'est un comportement documenté du frontal Streamlit 1.52.2, lisible dans son
bundle :

```js
STALE_TRANSITION_PARAMS = "1s ease-in 0.5s"
STALE_STYLES = { opacity: .33, transition: `opacity 1s ease-in 0.5s` }
```

Chaque `[data-testid="stElementContainer"]` porte un attribut `data-stale`.
Dès qu'un rerun dure plus de **500 ms**, tous les éléments pas encore
recalculés descendent à **33 % d'opacité** sur une seconde. L'indicateur
« Running » obéit à un seuil jumeau, `RUNNING_MAN_DISPLAY_DELAY_TIME_MS = 500`.

**Conséquence directe : un cycle qui tient sous 500 ms ne grise jamais.** Le
seuil n'est pas une préférence, c'est une constante du frontal. Tout le design
en découle.

## 2. Le fait qui justifie le chantier

Mesure du 2026-08-10 contre `TeNNet_test`, 11 matchs publiés dont 6 en cours,
process Python établi (connexion chaude) :

| étage du cycle | coût |
|---|---|
| `charger_matchs()` — `live_now`, 11 lignes | 20 ms |
| `charger_serie()` — total | **341 ms** |
| &nbsp;&nbsp;dont SQL `live_series`, 1128 lignes brutes | 48 ms |
| &nbsp;&nbsp;dont `fusionner_series` | **289 ms** |

**85 % du cycle est une boucle pandas ligne à ligne, pas une requête.** Le
premier appel à froid coûte 1417 ms (création du moteur), mais il n'a lieu
qu'une fois par process : ce n'est pas lui qui fait clignoter la page.

Le total, ~350 ms, se tient **juste sous le seuil de 500 ms**. D'où la qualité
du défaut : il ne casse pas, il agace par intermittence — et il s'aggrave avec
le nombre de matchs, c'est-à-dire les soirs où l'on regarde.

## 3. Le défaut que la mesure a découvert

`fusionner_series` groupe sur **`ts` seul** ([`live_data.py:1315`]) :

```python
for _, groupe in df.groupby("ts", sort=True):
```

Sa docstring est pourtant explicite : elle replie les identifiants **d'un même
match**, parce que la source en attribue parfois deux ou trois à une seule
rencontre. Mais [`pages/live.py:208`] lui passe **les six matchs en cours
d'un coup** :

```python
serie = charger_serie(",".join(en_cours["event_ids"].astype(str)))
```

Le publieur écrit tous les matchs dans le même cycle, donc au **même `ts`**.
Relevé réel :

```
ts = 1786352606.1  →  6 matchs distincts au même horodatage
 3816723  score 0-0      pts 0-0     back_a  3.10
 3816727  score 0-0      pts 0-0     back_a  1.03
 3817832  score 1-6,1-2  pts 40-40   back_a 10.00   ← seule survivante
 3818323  score 6-4,0-1  pts 0-0     back_a  1.34
 3818325  score 2-6,0-0  pts 40-40   back_a  4.10
 3818326  score 3-6,0-0  pts 15-0    back_a  2.96
```

La fonction garde la ligne « au score le plus avancé » — tous matchs
confondus — puis comble ses colonnes vides avec les valeurs **des autres
matchs** (`if pd.isna(base.get(colonne))`).

| mesure | valeur |
|---|---|
| horodatages distincts | 439 |
| horodatages partagés par **plusieurs matchs** | **342** |
| lignes écrasées | **726 sur 1165 — 62 %** |

Effet visible à l'écran, `mouvements_de_prix` appelé sur les deux versions :

| série | matchs porteurs d'une flèche |
|---|---|
| brute | **6** |
| fusionnée | **3** |

Et pour `3818325`, la version fusionnée annonce `back_odds_b: baisse` là où ses
propres relevés disent `hausse`. **Les flèches de mouvement de la liste sont
fausses aujourd'hui.** Ce ne sont pas des données manquantes : ce sont des
chimères composées de plusieurs matchs.

Le défaut et la lenteur ont la même cause, et la corriger sert les deux.

## 4. Pourquoi la fusion ne peut pas deviner

`live_series` ne porte **aucune colonne « match »**. Que deux `event_id`
désignent une seule rencontre est un fait de `live_now.event_ids`, jamais de la
table lue. La fusion ne peut donc pas le déduire — et le défaut d'aujourd'hui
est exactement là : elle le déduisait, en tenant un horodatage commun pour une
appartenance commune.

**L'appartenance devient un paramètre déclaré.**

- `fusionner_series(df, famille=None)`.
- `famille=None` — le défaut — groupe sur `(event_id, ts)` : **aucun
  repliement entre identifiants**. Le silence ne détruit plus rien.
- `famille=[ids...]` replie ces identifiants-là, et eux seuls, à `ts` égal.
- `charger_serie` passe `famille=surs`, ce qui est sa promesse depuis toujours :
  « la série d'**un** match ».

Il reste possible de déclarer une famille fausse — mais il faut désormais un
acte explicite pour cela, là où l'ancien comportement l'imposait par défaut.

## 5. Le cycle passe sous le seuil

La liste n'a jamais eu besoin de la fusion. Elle n'appelle `charger_serie` que
pour nourrir `mouvements_de_prix`, qui regroupe par `event_id` — et
[`liste_dense.py:576-580`] refusionne déjà les identifiants d'un match après
coup :

```python
for ident in str(m.get("event_ids") or m.get("event_id") or "").split(","):
    mvt.update(mouvements.get(ident.strip(), {}))
```

Nouveau lecteur `charger_mouvements(event_ids, lecteur=None)` : les six
colonnes utiles, aucune fusion.

```sql
SELECT event_id, ts, back_odds_a, lay_odds_a, back_odds_b, lay_odds_b
FROM live_series WHERE event_id IN (...) ORDER BY ts
```

Il partage `_identifiants_surs` et `_litteral_liste` avec les lecteurs
existants : la règle de sûreté SQL reste écrite **une seule fois**
([`live_data.py:748-752`]).

| | avant | après |
|---|---|---|
| lecture pour la liste | 341 ms | **16 ms** (mesuré) |
| cycle complet | ~350 ms | **~40 ms** |

Une fenêtre de détail ouverte ajoute son propre `charger_serie`, fusion
comprise — mais pour **un** match, sur sa seule série. Ce coût-là est celui que
la fusion doit payer, et il n'entre pas dans le cycle de la liste.

**La fenêtre temporelle n'est pas réduite.** Tentation écartée sur mesure :
`live_series` écrit **au changement**, pas à cadence fixe — écarts médians de
8 à 101 s selon le match, et des trous allant jusqu'à **1354 s**. Une fenêtre
de 600 s perdrait le relevé de référence d'avant la fenêtre de mouvement, donc
des flèches. La lenteur n'était pas dans le volume lu ; on ne coupe pas dans ce
qui n'est pas le problème.

## 6. Éteindre le grisement quand même

Le §5 met le cycle à ~40 ms, très en dessous des 500 ms : le grisement ne
devrait plus se déclencher. Ce n'est pas une raison de s'en remettre à lui. Le
budget de 500 ms est un plafond qu'on ne contrôle pas — base lente, soir à
quarante matchs, réseau. La ceinture tient seule ; le §5 est la bretelle.

Feuille de style dédiée, injectée **une fois au chargement de la page**, hors
du fragment — aujourd'hui elle est réémise à chaque cycle
([`pages/live.py:197`]) :

```css
[data-testid="stElementContainer"][data-stale="true"] {
  opacity: 1 !important; transition: none !important;
}
.stStatusWidget:has([data-testid="stStatusWidgetRunningIcon"]) { display: none; }
```

La seconde règle n'éteint **que** l'homme qui court. Le même widget porte
aussi « Connecting… » et l'avis de session perdue : les masquer échangerait une
gêne contre un silence dangereux.

La feuille est une **constante partagée**, importée par les deux pages du §8 —
ni `pages/match.py` ni `detail_match.py` n'injectent de CSS aujourd'hui, et
l'écrire deux fois garantirait qu'une correction n'atterrisse que d'un côté.
C'est la règle que ce dépôt tient déjà pour `detail_match`, partagé entre les
deux pages.

Ces deux sélecteurs sont des **internes de Streamlit**, relevés dans le bundle
1.52.2 et non de mémoire. Une montée de version peut les déplacer — c'est
pourquoi le §9 les fait garder par un test navigateur, seul endroit d'où l'on
puisse constater une opacité.

## 7. Ce qui remplace le grisement comme signal de vie

Supprimer le grisement supprime le seul signe que les données bougent. Sur une
page dont la raison d'être est de montrer que la collecte capte, ce n'est pas
neutre. Deux remplaçants, l'un global, l'autre local.

**Le battement.** Un bandeau sobre en tête de liste :
`● 14:32:07 · 6 matchs en cours`. La pastille joue une animation d'une seconde.
Streamlit recréant l'élément à chaque cycle, l'animation **rejoue à chaque
cycle** : c'est un battement, pas une boucle décorative qui tournerait aussi
sur une page morte. L'heure est celle du chargement réussi côté serveur — si le
cycle s'arrête, elle se fige, et ça se voit.

**Le surlignage.** Un instantané des valeurs volatiles — jeux, point, back, lay,
par joueur — vit dans `st.session_state`, une entrée par section
(`en-cours` / `termines`) pour que les deux listes ne se marchent pas dessus. À
chaque cycle on compare, on pose une classe `.neuf` sur les seules cellules qui
ont changé, et le CSS joue un surlignage de 0,6 s.

Au **premier** rendu il n'y a rien à comparer : aucun flash, faute de quoi toute
la liste s'allumerait à l'ouverture et le signal ne voudrait plus rien dire.

Le diff est calculé **côté serveur** : `st.markdown` n'exécute pas de
`<script>`, il n'y a pas d'autre voie. Le calcul est une comparaison de
dictionnaires — sans rapport avec les 289 ms du §2, qui étaient une boucle
`iterrows` sur un millier de lignes.

Ce surlignage ne remplace pas les flèches `hausse`/`baisse` : elles disent
« ce prix a bougé dans les deux dernières minutes », lui dit « ceci vient de
changer sous tes yeux ». Deux échelles de temps, deux marques.

## 8. Portée

- **`pages/live.py`** — §5, §6, §7 en entier.
- **`pages/match.py`** — le fragment de [`pages/match.py:541`] reçoit le §6.
  Pas le §7 : il affiche **un** match, pas une liste, et son détail porte déjà
  son propre graphique. Un battement n'y ajouterait rien qu'un point qui clignote.
- **`live_data.py`** — §4 et le lecteur du §5.
- **Hors périmètre** : `bets_en_cours.py` et `ws_odds_monitor.py`. Elles
  emploient `st_autorefresh`, qui relance la page **entière** — un autre
  mécanisme, un autre diagnostic, à traiter une fois celui-ci vérifié à l'usage.

La cadence par défaut reste **15 s**. À ~40 ms le cycle, 5 s devient
défendable, mais c'est un choix d'usage à faire en regardant la page, pas dans
une spec.

**Note ajoutée à la revue finale (2026-08-10).** Deux précisions que ce
paragraphe ne pouvait pas encore porter en le rédigeant :

1. Le §6 dit que la feuille est **une constante partagée** ; ce paragraphe dit
   que `pages/match.py` reçoit le §6 **mais pas** le §7. Les deux ne peuvent
   plus être vrais en même temps une fois que le CSS du §7 (le battement, le
   surlignage `.neuf`) vit **dans cette même constante** `CSS_FLUX` — ce
   qu'il fait, pour ne pas écrire deux feuilles. `pages/match.py` charge donc
   forcément des règles `.battement` et `.liste-dense .neuf` qu'il n'exploite
   jamais : sa page ne dessine ni bandeau de battement ni liste surlignée.
   C'est une contradiction du présent document, pas du code. Le CSS mort est
   accepté tel quel plutôt que de scinder `CSS_FLUX` en deux constantes : la
   duplication qu'une scission éviterait (quelques règles jamais
   appliquées) coûte moins qu'une deuxième feuille à tenir synchrone — exactement
   le risque que le §6 invoque pour justifier la constante unique.
2. **`pages/match.py` a deux moitiés**, et la revue finale a tranché que
   `CSS_FLUX` ne s'injecte que sur l'une : le fragment auto-rafraîchi du
   §8 (`if event_id:`), pas `niveau_1()` (l'archive — filtres, requêtes
   lentes, aucun fragment). Éteindre le grisement sur `niveau_1()` aurait fait
   passer une requête lente pour une page figée, et la même règle masque le
   widget qui porte aussi le bouton Stop — le seul moyen d'interrompre un
   cycle bloqué sur cette moitié-là de la page. Seul le rafraîchissement
   **automatique** devait se faire discret ; le clic dans l'archive garde son
   grisement et son Stop.

## 9. Vérification

Le défaut du §3 a survécu à 169 tests verts parce qu'aucun ne regardait un
rendu, et celui du §1 est **une opacité** : rien dans `AppTest` ne peut la voir.

| ce qu'on prouve | où |
|---|---|
| `fusionner_series` sans `famille` ne replie **jamais** deux `event_id` | test unitaire, données du §3 |
| avec `famille`, elle replie les identifiants d'un match — comportement du 2026-08-04 préservé | test unitaire |
| `charger_mouvements` rend les mêmes flèches que la série brute, pour les **six** matchs | test unitaire, `lecteur` injecté |
| le marquage `.neuf` ne s'allume pas au premier rendu | test unitaire |
| aucun conteneur ne descend sous l'opacité 1 pendant un cycle | [`tests/test_navigateur.py`] |
| l'icône « Running » est absente, le widget de déconnexion intact | [`tests/test_navigateur.py`] |

Le test de régression du §3 doit **échouer sur le code d'aujourd'hui** avant
qu'on le corrige. Un test qui n'a jamais été rouge ne prouve rien.

## 10. Ce que ce design ne fait pas

- **Pas de streaming client** (SSE, composant bidirectionnel, endpoint JSON).
  Envisagé, écarté : il faudrait un serveur HTTP à côté, son authentification,
  et un composant bidirectionnel pour que le clic ouvre encore le dialogue —
  alors que [`pages/live.py:191-195`] rappelle que tout ce qui recharge la page
  **déconnecte**, l'authentification ne vivant que dans `session_state`.
  Beaucoup de surface neuve pour ce qui est une règle CSS et un signal manquant.
- **Pas de cache sur `charger_matchs`.** 20 ms à chaud : un cache économiserait
  20 ms et introduirait une question de fraîcheur sur la page dont la fraîcheur
  est le sujet.
- **Pas de refonte de la structure DOM.** Les ~150 éléments par cycle ne sont
  pas le coût ; les 289 ms l'étaient.
