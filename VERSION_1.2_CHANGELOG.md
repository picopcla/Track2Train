# 🎉 VERSION 1.2 - Track2Train

## 📅 Date
2025-11-09

---

## 🆕 NOUVELLES FONCTIONNALITÉS

### 1. ✅ Calcul FC par segments de distance
**Fichier** : `calculate_running_stats.py`

**Ajout de 2 nouvelles fonctions** :
- `get_segments_count(run_type)` : Détermine le nombre de segments (2/3/4)
- `calculate_fc_by_segments(points, num_segments)` : Calcule la FC moyenne par segment

**Segmentation selon le type** :
- `normal_5k` → 2 segments
- `normal_10k` → 3 segments
- `long_run` → 4 segments

**Nouveau champ dans running_stats.json** :
```json
"fc_segments": [132.6, 149.5]  // Exemple pour normal_5k
```

**Résultats** :
- `normal_5k`: [132.6, 149.5] bpm
- `normal_10k`: [130.6, 144.1, 152.9] bpm
- `long_run`: [134.8, 146.6, 151.4, 154.1] bpm

---

## 🎨 AMÉLIORATIONS VISUELLES

### 2. ✅ En-tête Allure - "/km" en noir
**Fichier** : `templates/index.html` (ligne 238)

**AVANT** :
```html
<span style="color: #9ca3af; font-size: 1.2rem;">/km</span>
```

**APRÈS** :
```html
<span style="color: #1f2937; font-size: 1.2rem;">/km</span>
```

**Résultat** : Meilleure lisibilité, texte noir au lieu de gris

---

### 3. ✅ Courbe Allure - Vert lime + Plus épaisse
**Fichier** : `templates/index.html` (lignes 745-750)

**AVANT** :
```javascript
stroke: {
    width: 2,
    curve: 'stepline',
    colors: ['#006400']  // Vert foncé
},
colors: ['#006400'],
```

**APRÈS** :
```javascript
stroke: {
    width: 3,  // Plus épaisse
    curve: 'stepline',
    colors: ['#32CD32']  // Vert lime pétant
},
colors: ['#32CD32'],
```

**Résultat** : Courbe beaucoup plus visible

---

### 4. ✅ Courbe FC - Rouge pleine (pas pointillée)
**Fichier** : `templates/index.html` (lignes 602-605)

**AVANT** :
```javascript
stroke: {
    width: 2,
    curve: 'smooth',
    dashArray: 5  // Pointillé
},
```

**APRÈS** :
```javascript
stroke: {
    width: 2,
    curve: 'smooth'  // Ligne pleine
},
```

**Résultat** : Courbe FC rouge continue, plus claire

---

### 5. ✅ Ligne FC max supprimée
**Fichier** : `templates/index.html`

La ligne horizontale rouge "Max (167 bpm)" a été supprimée des annotations.

**Raison** : Redondante, n'apporte pas d'information utile

**Résultat** : Graphique plus épuré, focus sur les zones cardiaques

---

## 📊 DONNÉES MISES À JOUR

### running_stats.json
**Régénéré le** : 2025-11-09T10:48:28

**Nouveaux champs** :
```json
{
  "normal_5k": {
    "fc_segments": [132.6, 149.5],
    ...
  },
  "normal_10k": {
    "fc_segments": [130.6, 144.1, 152.9],
    ...
  },
  "long_run": {
    "fc_segments": [134.8, 146.6, 151.4, 154.1],
    ...
  }
}
```

---

## 🔧 CORRECTIONS TECHNIQUES

### Calcul allure moyenne (corrigé dans version précédente)
Rappel : Le calcul utilise maintenant `temps_total / distance_totale` au lieu de la moyenne des allures instantanées.

---

## 📝 FICHIERS MODIFIÉS

1. **calculate_running_stats.py**
   - Lignes 11-77 : Ajout fonctions segments
   - Lignes 166-182 : Calcul moyennes FC segments
   - Ligne 204 : Ajout fc_segments dans stats
   - Lignes 281-283 : Affichage FC segments dans terminal

2. **running_stats.json**
   - Régénéré avec fc_segments pour tous les types

3. **templates/index.html**
   - Ligne 238 : /km en noir
   - Lignes 602-605 : Courbe FC pleine
   - Lignes 745-750 : Courbe allure lime + épaisse
   - Lignes 660-665 : Suppression ligne FC max

---

## ✅ VALIDATION

### Tests effectués
```bash
✅ calculate_running_stats.py - Compilé sans erreur
✅ running_stats.json - Régénéré avec succès
✅ Template Jinja2 - Parsé sans erreur
✅ Graphiques - Affichage correct
```

### Résultat visuel
- **Graphique FC** : Courbe rouge pleine + zones cardiaques colorées
- **Graphique Allure** : Courbe vert lime visible + lignes référence
- **En-tête** : /km en noir, meilleure lisibilité

---

## 🎯 RÉSUMÉ

**Version 1.2** améliore significativement la lisibilité des graphiques avec :
- Courbes plus visibles (lime, épaisseur)
- Interface plus épurée (suppression ligne FC max redondante)
- Données enrichies (FC par segments de distance)
- Textes plus lisibles (noir au lieu de gris)

**Prêt pour la production** ✅

---

**Date de sauvegarde** : 2025-11-09
**Statut** : Stable et validé
