# 📊 IMPLÉMENTATION PALIERS FC - Version expérimentale

## 📅 Date
2025-11-09

---

## 🎯 OBJECTIF

Afficher des **lignes horizontales par segments** sur le graphique FC, montrant la FC moyenne de chaque portion de distance basée sur les stats des 15 derniers runs.

---

## 🏗️ ARCHITECTURE

### Concept
Au lieu d'une ligne horizontale complète, chaque segment a sa propre ligne **uniquement sur sa portion de distance** :

**Exemple 5K (2 segments)** :
- Segment 1 (0-3 km) : ligne violette à 133 bpm
- Segment 2 (3-6 km) : ligne violette à 150 bpm

**Exemple 10K (3 segments)** :
- Segment 1 (0-3.3 km) : ligne à 131 bpm
- Segment 2 (3.3-6.6 km) : ligne à 144 bpm
- Segment 3 (6.6-10 km) : ligne à 153 bpm

---

## 💻 IMPLÉMENTATION

### Fichier : `templates/index.html`

#### 1. Construction des séries (lignes 573-603)

```javascript
// Construire les séries FC (courbe principale + segments)
const fcSeries{{ loop.index0 }} = [{
    name: 'FC',
    data: fc{{ loop.index0 }}.map((val, idx) => ({
        x: labels{{ loop.index0 }}[idx],
        y: val
    }))
}];

// Ajouter les séries de segments FC
{% if running_stats and running_stats.stats_by_type %}
    {% set current_type = act.type_sortie %}
    {% if current_type in running_stats.stats_by_type %}
        {% set stats = running_stats.stats_by_type[current_type] %}
        {% if stats.fc_segments %}
            {% set num_segments = stats.fc_segments|length %}
            {% for fc_seg in stats.fc_segments %}
                {% set seg_index = loop.index0 %}
                {% set seg_start = (seg_index * 1.0 / num_segments) %}
                {% set seg_end = ((seg_index + 1) * 1.0 / num_segments) %}
fcSeries{{ loop.index0 }}.push({
    name: 'Segment {{ loop.index }}',
    data: [
        { x: maxDistance{{ loop.index0 }} * {{ seg_start }}, y: {{ fc_seg }} },
        { x: maxDistance{{ loop.index0 }} * {{ seg_end }}, y: {{ fc_seg }} }
    ]
});
            {% endfor %}
        {% endif %}
    {% endif %}
{% endif %}
```

**Logique** :
1. Créer un tableau `fcSeries` avec la courbe FC principale
2. Pour chaque segment dans `stats.fc_segments`, ajouter une série
3. Chaque série contient 2 points : début et fin du segment
4. Calcul des positions : `(index / num_segments) * maxDistance`

---

#### 2. Configuration des styles (lignes 628-632)

```javascript
stroke: {
    width: [2, 2, 2, ...],  // Dynamique selon nombre de segments
    curve: ['smooth', 'straight', 'straight', ...]  // FC smooth, segments straight
},
colors: ['#ef4444', '#9333ea', '#9333ea', ...],  // Rouge + violet
```

**Génération dynamique avec Jinja2** :
- Si `fc_segments` existe : tableaux avec valeurs pour chaque série
- Sinon : valeurs simples (compatibilité arrière)

---

## 📊 DONNÉES SOURCE

### running_stats.json
```json
{
  "normal_5k": {
    "fc_segments": [132.6, 149.5]
  },
  "normal_10k": {
    "fc_segments": [130.6, 144.1, 152.9]
  },
  "long_run": {
    "fc_segments": [134.8, 146.6, 151.4, 154.1]
  }
}
```

Calculées par `calculate_running_stats.py` sur les 15 derniers runs du même type.

---

## 🎨 RENDU VISUEL ATTENDU

### Graphique FC

```
FC (bpm)
  160 ┤     ╭─────╮
      │    ╭╯     ╰╮
  150 ┼════════════════════  ← Segment 2 (violet, 3-6km)
      │   ╭╯         ╰╮
  140 │  ╱             ╰╮
  130 ┼════════  ← Segment 1 (violet, 0-3km)
      │ ╱               ╰╮
  120 ┤╱                 ╰─
      └─────────────────────
       0   1   2   3   4   5   6  Distance (km)
```

**Légende** :
- Ligne rouge continue : FC réelle du run
- Lignes violettes horizontales : FC moyenne par segment (stats 15 derniers runs)

---

## ⚠️ POINTS D'ATTENTION

### 1. Compatibilité arrière
Le code vérifie l'existence de `fc_segments` avant de les ajouter. Si absent, affiche uniquement la courbe FC normale.

### 2. Performance
Pour un run avec 2 segments :
- 1 série FC : ~1000 points de données
- 2 séries segments : 2 points chacune
- Total : 3 séries, performance acceptable

### 3. Lisibilité
Les lignes violettes ne doivent pas masquer la courbe rouge. Couleur et épaisseur choisies pour contraste optimal.

---

## 🧪 VALIDATION

### Template Jinja2
```bash
✅ Template compilé sans erreur
✅ Syntaxe JavaScript valide
```

### Tests manuels requis
⚠️ **À tester par l'utilisateur** :
1. Charger la page web
2. Vérifier que le graphique FC s'affiche
3. Vérifier que les lignes violettes apparaissent en escalier
4. Vérifier que les segments correspondent aux bonnes portions de distance

---

## 🔄 ROLLBACK SI ÉCHEC

Si le graphique ne s'affiche pas ou plante :

```bash
# Revenir à la version 1.2 stable
git checkout templates/index.html
# Ou restaurer manuellement depuis VERSION_1.2_CHANGELOG.md
```

**Version de rollback** :
- Courbe FC rouge pleine
- Pas de segments
- Graphique stable et fonctionnel

---

## 📝 MODIFICATIONS EXACTES

### templates/index.html

**Lignes modifiées** :
- 573-606 : Construction séries avec segments
- 628-632 : Styles dynamiques

**Logique** :
- Si `stats.fc_segments` existe → séries multiples
- Sinon → série unique (version 1.2)

---

## ✅ STATUT

**IMPLÉMENTÉ** - En attente de validation utilisateur

Si validation réussie → Version 1.3
Si échec → Rollback à Version 1.2

---

**Date d'implémentation** : 2025-11-09
**À tester par** : Utilisateur
**Rollback disponible** : Oui (VERSION_1.2_CHANGELOG.md)
