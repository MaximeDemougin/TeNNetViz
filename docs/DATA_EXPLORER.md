# 🔍 Page d'Exploration de Données - PyGWalker

## Description

La nouvelle page **"Exploration de données"** utilise PyGWalker pour permettre une analyse interactive et visuelle des paris. Cette interface de type "glisser-déposer" permet de créer facilement des graphiques, tableaux croisés dynamiques et analyses personnalisées sans écrire de code.

## Fonctionnalités

### 📊 Visualisations interactives
- **Graphiques multiples** : Barres, lignes, aires, scatter plots, etc.
- **Tableaux croisés dynamiques** : Agrégations et pivots personnalisés
- **Filtres dynamiques** : Filtrage facile des données
- **Encodage couleur** : Ajout de dimensions supplémentaires avec la couleur

### 🎯 Sources de données
Trois options de sélection :
1. **Paris terminés** : Analyse des paris déjà conclus avec gains/pertes
2. **Paris en cours** : Visualisation des paris actifs
3. **Les deux** : Vue combinée avec distinction par statut

### 📈 Métriques disponibles
- Nombre total de paris
- Colonnes disponibles
- Gains totaux (pour paris terminés)

### 🎨 Options de personnalisation
- **Mode sombre/clair** : Adaptation à vos préférences visuelles
- **Barre d'outils** : Affichage ou masquage des outils

## Colonnes disponibles

| Colonne | Description |
|---------|-------------|
| Match | Nom du match (Joueur 1 - Joueur 2) |
| Date | Date et heure du match |
| Compétition | Type de compétition (ATP, WTA, Doubles) |
| Level | Niveau du tournoi (Grand Chelem, Masters, etc.) |
| Round | Tour du tournoi |
| Surface | Surface de jeu (Dur, Gazon, Terre battue) |
| Mise | Montant misé |
| Cote | Cote réelle du pari |
| Prédiction | Cote prédite par le modèle |
| Gains net | Gains ou pertes du pari |
| Marge attendue | Marge théorique du pari |
| Cumulative Gains | Gains cumulés |

## Exemples d'utilisation

### 🎾 Analyse par surface
1. Glissez "Surface" vers l'axe X
2. Glissez "Gains net" vers l'axe Y
3. Sélectionnez un graphique en barres
4. Visualisez vos performances par surface

### 🏆 Performance par niveau de tournoi
1. Glissez "Level" vers l'axe X
2. Glissez "Mise" et "Gains net" vers l'axe Y
3. Comparez vos investissements et retours

### 📅 Évolution temporelle
1. Glissez "Date" vers l'axe X
2. Glissez "Cumulative Gains" vers l'axe Y
3. Visualisez l'évolution de votre bankroll

### 🔍 Tableau croisé dynamique
1. Passez en mode "Tableau"
2. Glissez "Compétition" en lignes
3. Glissez "Surface" en colonnes
4. Glissez "Gains net" en valeurs (somme)

## Installation

La dépendance PyGWalker a été ajoutée automatiquement :

```bash
pip install pygwalker>=0.4.9,<0.5.0
```

## Accès

La page est accessible depuis le menu principal sous la section **"Analyse"** avec l'icône 📊.

## Configuration technique

- **Cache des données** : TTL de 300 secondes pour optimiser les performances
- **Mode de calcul** : `use_kernel_calc=True` pour de meilleures performances
- **Sauvegarde des configurations** : `spec_io_mode="rw"` pour sauvegarder vos visualisations

## Notes

- La page nécessite une connexion utilisateur active
- Les données sont chargées dynamiquement en fonction de la sélection
- L'interface s'adapte au thème sombre pour une meilleure expérience
