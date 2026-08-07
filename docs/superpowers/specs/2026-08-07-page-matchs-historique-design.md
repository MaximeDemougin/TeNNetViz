# La page « Match » devient le parcours du passé et le bilan de collecte — design du 2026-08-07

## 1. Ce que la page doit servir

Deux besoins, un seul écran :

- **parcourir les matchs passés** avec des filtres ;
- **juger la santé de la collecte** — capte-t-on bien, et est-ce que ça
  s'améliore ?

Décision du propriétaire : la santé visée est celle de **la collecte**, pas
l'état instantané du système. La question est « ma matière vaut-elle quelque
chose ? », pas « un capteur est-il tombé ? ». Et la page « Match » actuelle
devient le **second niveau** de celle-ci, au lieu d'une page séparée.

## 2. Le fait qui justifie la page

**Les seuils de santé existent déjà dans le code, les trois sont franchis tous
les jours, et personne ne le voit.**

| indicateur | seuil (`Live/config.py`) | mesuré le 2026-08-06 |
|---|---|---|
| `match_rate` | `QA_MIN_MATCH_RATE = 0.90` | **65,3 %** |
| `pbp_coherence` | `QA_MIN_PBP_COHERENCE = 0.95` | **39,3 %** |
| `gap_ratio` | `QA_MAX_GAP_RATIO = 0.05` | **51,6 %** — dix fois le seuil |

`Live/qa_report.py` calcule ces trois valeurs chaque nuit et les écrit dans
`TeNNet_test.live_qa_daily` depuis le 2026-07-28. **Aucune n'est affichée nulle
part.** La page ne décore pas : elle rend visibles trois alarmes qui sonnent en
silence depuis dix jours.

Et la table porte une mesure que personne n'avait relevée — l'effet chiffré de
la correction d'authentification :

| jour | marchés | taux | cohérence `pbp` | **trou** | in-play |
|---|---|---|---|---|---|
| 08-01 | 54 | 88,9 % | 34,4 % | **97,4 %** | 97,5 h |
| 08-02 | 83 | 59,0 % | 36,9 % | **95,1 %** | 158,7 h |
| 08-03 | 88 | 68,2 % | 50,0 % | **97,2 %** | 190,7 h |
| 08-04 | 121 | 68,6 % | 62,1 % | **62,5 %** | 204,2 h |
| 08-05 | 55 | 72,7 % | 49,8 % | **50,3 %** | 86,9 h |
| 08-06 | 49 | 65,3 % | 39,3 % | **51,6 %** | 83,1 h |

Le trou passe de 97 % à 51 % entre le 3 et le 5 août — la fenêtre exacte de la
correction. Le gain est réel et mesuré ; le reste ne l'est pas.

## 3. La matière disponible, et ses limites

| table | volume | étendue | sert à |
|---|---|---|---|
| `live_matches` | 1 153 | 10 jours | parcourir, filtrer |
| `live_qa_daily` | 10 | 10 jours | le bilan |
| `live_points` | 176 208 | 10 jours | le point par point d'un match |
| `live_pbp_games` | 9 958 | 10 jours | le serveur faisant autorité |
| `live_inplay_markets` | 455 | 10 jours | les marchés vus sans match apparié |
| `live_series` | 45 178 | **2,6 jours** | les cotes — **limite dure** |

**La limite qui compte, et ce qu'elle n'est PAS** : `live_series` ne couvre que
~2,6 jours. Un match ancien aura son point par point mais **pas sa courbe de
cotes**. La page doit le DIRE quand c'est le cas, pas afficher un graphique
vide — une absence silencieuse se lit comme une panne.

**Ce n'est pas une perte de donnée, c'est une limite d'ACCES.** Les cotes de
ces matchs existent, dans les fichiers `ticks-*.ndjson.gz` sur le disque du
VPS (5 jours au 2026-08-07, aucune purge automatique, 62 Go libres pour
25-40 Mo/jour). Mais **cette page tourne sur Streamlit Community Cloud, qui
n'a pas ce disque** : elle ne peut lire que la base. D'ou la limite.

**Et cela ne contraint EN RIEN la modelisation**, qui se fait cote PoC, sur les
fichiers bruts. Ne pas lire ce paragraphe comme « les cotes anciennes sont
perdues » : elles ne le sont pas. Ce qui limite un modele aujourd'hui n'est pas
une retention mais l'AGE de la collecte -- 10 jours de matchs, 5 jours de
carnet -- contre les ~2 700 matchs que la puissance exige (§3.1 du document de
reprise du PoC). Au rythme mesure de ~115 matchs/jour, c'est trois a quatre
semaines d'accumulation, pas un obstacle de conception.

`live_matches` porte `ID_MATCH`, la clé de production : un match passé est donc
joignable au vrai résultat, et potentiellement aux paris. **Hors périmètre ici**,
mais c'est la raison de ne pas se contenter d'`event_id`.

## 4. Deux taux d'appariement, deux dénominateurs — ne pas les confondre

- **65,3 %** (`match_rate`, `live_qa_daily`) : sur les **marchés vus en jeu**,
  ceux qui sont appariés **et non ambigus**. Un appariement ambigu compte au
  dénominateur, jamais au numérateur (`Live/qa_report.py:275-288`).
- **36 %** (416/1 153, `live_matches.matched`) : sur **tous les matchs
  identifiés**, y compris ceux qu'OrbitX n'a jamais eus en direct.

Les deux sont justes et répondent à des questions différentes. La page affiche
le premier comme indicateur de santé, le second comme fait de la liste — et
étiquette chacun avec son dénominateur. Les mélanger produirait un chiffre qui
ne veut rien dire.

## 5. L'écran

**Niveau 1 — la flotte.**

Le bilan jour par jour : les trois indicateurs face à leur seuil, avec la
tendance. Un indicateur hors seuil se voit ; un indicateur qui s'améliore
aussi. Puis la liste des matchs, filtrable.

**Filtres** (tous tirés des données, jamais codés en dur) : jour, circuit
(`atp` 686 / `wta` 467), ligue (50 valeurs), apparié ou non.

**Niveau 2 — le match choisi.**

Le contenu de la page actuelle, réutilisé et non réécrit : point par point,
serveur, cotes quand elles existent encore. On y arrive en choisissant dans la
liste plutôt que par le sélecteur actuel.

## 6. Les pièges d'affichage, nommés

- **Les jours sans marché** (07-28 au 07-31 : `n_markets = 0`) doivent se lire
  « pas de mesure », **jamais « 0 % de santé »**. Un dénominateur nul n'est pas
  un échec — c'est l'absence de mesure, et le code du dépôt refuse déjà cette
  division ailleurs (`Live/qa_report.py:183`).
- **`n_inversions` vaut `None`** sur toutes les lignes : ne pas afficher une
  colonne vide comme si elle valait zéro.
- **Les cotes absentes** au-delà de 2,6 jours se disent, ne se masquent pas.
- **Une ligue à 1 match** n'est pas une statistique : la liste peut la montrer,
  le bilan ne doit pas en tirer un taux.

## 7. Hors périmètre

- **Aucune écriture en base.** La page lit ; elle n'écrit ni ne corrige rien.
- **Aucun calcul d'indicateur nouveau.** `qa_report` les calcule déjà ; les
  recalculer côté page créerait deux vérités qui divergeraient.
- **Aucune jointure aux paris ni au résultat de production.** `ID_MATCH` le
  permettrait, mais c'est un autre chantier — et le dépôt de la viz est public.
- **L'état instantané des sept capteurs** : c'est la page « En direct » qui le
  porte, pas celle-ci.

## 8. Ce que la page va poser comme questions, sans y répondre

Elle rendra visibles trois écarts que ce design ne cherche pas à expliquer, et
c'est bien ainsi — un tableau de bord qui masque ce qu'il ne sait pas expliquer
ne sert à rien.

- **`gap_ratio` à 51 %** : la moitié du temps de jeu n'est pas couverte, dix
  fois le seuil. Pourquoi, après la correction d'authentification ?
- **`pbp_coherence` à 39 %** alors que le dépôt a mesuré **86,6 %** comme
  plafond d'accord entre le serveur déduit et le `pbp` (§3.4 du document de
  reprise). L'écart est grand et n'est pas expliqué. Piste : les captures `pbp`
  ne portent qu'une médiane de 2 jeux (§13.14), donc le dénominateur commun est
  peut-être minuscule et le taux instable.
- **`match_rate` à 65 %** pour un seuil à 90 %.
