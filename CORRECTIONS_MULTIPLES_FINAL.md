# ✅ CORRECTIONS MULTIPLES FINALES - templates/index.html ET app.py

## 📅 Date
2025-11-09

---

## 1. ✅ LABELS ANNOTATIONS - Backgrounds déjà supprimés

### Vérification effectuée
Tous les labels d'annotations ont déjà `background: 'transparent'` :
- ✅ Graphique FC : label "Max" (ligne rouge)
- ✅ Graphique Allure : label "Cible 5:20" (ligne rouge)
- ✅ Graphique Allure : label "Moy" (ligne verte)

**Résultat** : Aucune modification nécessaire, déjà correct.

---

## 2. ✅ POSITION LABELS ANNOTATIONS - Éviter superposition/coupure

### Problèmes identifiés
1. **Graphique FC** : Label "Max" coupé à gauche
2. **Graphique Allure** : 2 labels superposés

### Modifications appliquées

#### A. Graphique FC - Label "Max" (ligne ~676-686)

**Avant** :
```javascript
label: {
    text: 'Max (...)',
    position: 'left',  // ❌ Coupé à gauche
    ...
}
```

**Après** :
```javascript
label: {
    text: 'Max (...)',
    position: 'right',  // ✅ Déplacé vers la droite
    ...
}
```

#### B. Graphique Allure - Labels avec offset vertical (lignes ~791-802 et ~815-826)

**Label "Cible 5:20"** (rouge) :
```javascript
label: {
    text: 'Cible 5:20',
    position: 'right',
    offsetX: 0,
    offsetY: -10,  // ✅ AU-DESSUS de la ligne
    ...
}
```

**Label "Moy"** (vert) :
```javascript
label: {
    text: 'Moy (...)',
    position: 'right',
    offsetY: 10,  // ✅ EN-DESSOUS de la ligne
    ...
}
```

**Résultat** :
- Label FC max visible à droite
- Labels Allure espacés verticalement (évite superposition)

---

## 3. ✅ SPARKLINES - Ajout du run actuel

### Problème
Les sparklines affichaient les 20 derniers runs mais PAS le run actuel en cours de visualisation.

### Modification app.py (lignes ~1189-1243)

**Ancienne logique** :
```python
# Historique dérive cardiaque (20 derniers du même type)
drift_history = []
for prev_act in same_type_runs:
    deriv = prev_act.get("deriv_cardio")
    if isinstance(deriv, (int, float)):
        drift_history.append(deriv)
drift_history.reverse()
drift_history_last20 = json.dumps(drift_history)  # ❌ Sans le run actuel
```

**Nouvelle logique** :
```python
# Historique dérive cardiaque (20 derniers du même type)
drift_history = []
for prev_act in same_type_runs:
    deriv = prev_act.get("deriv_cardio")
    if isinstance(deriv, (int, float)):
        drift_history.append(deriv)
drift_history.reverse()  # Du plus ancien au plus récent

# Historique k_moy (20 derniers du même type)
k_history = []
for prev_act in same_type_runs:
    k = prev_act.get("k_moy")
    if isinstance(k, (int, float)):
        k_history.append(k)
k_history.reverse()

# Comparaisons (moyennes des 20 derniers - SANS la valeur actuelle)
k_moy_current = act.get("k_moy")
deriv_current = act.get("deriv_cardio")

# [... calculs comparaisons ...]

# ✅ Ajouter la valeur du run actuel à la fin (pour affichage sparkline)
if isinstance(k_moy_current, (int, float)):
    k_history.append(k_moy_current)
if isinstance(deriv_current, (int, float)):
    drift_history.append(deriv_current)

drift_history_last20 = json.dumps(drift_history) if len(drift_history) >= 2 else None
k_history_last20 = json.dumps(k_history) if len(k_history) >= 2 else None
```

**Points clés** :
- ✅ Comparaison calculée AVANT d'ajouter la valeur actuelle (sinon on compare à une moyenne qui l'inclut)
- ✅ Valeur actuelle ajoutée à la fin pour affichage sparkline
- ✅ Sparkline montre maintenant : 20 derniers runs + run actuel (21 points)

**Résultat** :
- Sparklines incluent le point du run en cours
- Dernière valeur de la sparkline = valeur actuelle affichée dans la card

---

## 4. ✅ LIGNES MOYENNES GRAPHIQUES - Correction des valeurs sources

### Problème
Les lignes de référence utilisaient les mauvaises valeurs :
- **FC max** : utilisait `fc_max.moyenne` au lieu de `fc_max.max`
- **Allure max** (en-tête) : utilisait `allure.max` (pire/lente) au lieu de `allure.min` (meilleure/rapide)

### Logique correcte confirmée dans calculate_running_stats.py

**Structure des stats** (lignes ~89-114) :
```python
'fc_moyenne': {
    'moyenne': moyenne des FC moyennes,  # ← Pour ligne FC moyenne
    'min': min des FC moyennes,
    'max': max des FC moyennes
},
'fc_max': {
    'moyenne': moyenne des FC max,
    'min': min des FC max,
    'max': max des FC max  # ← Pour ligne FC max
},
'allure': {
    'moyenne': moyenne des allures moyennes,  # ← Pour ligne Allure moyenne
    'min': meilleure (plus rapide = min),     # ← Pour ligne Allure max (en-tête)
    'max': pire (plus lente = max)
}
```

### Modifications templates/index.html

#### A. Graphique FC - Ligne "Max" (ligne ~669-686)

**Avant** :
```javascript
{% if stats.fc_max and stats.fc_max.moyenne %}  // ❌ Utilisait moyenne
{
    y: {{ stats.fc_max.moyenne }},
    label: { text: 'Max ({{ stats.fc_max.moyenne|int }} bpm)' }
}
{% endif %}
```

**Après** :
```javascript
{% if stats.fc_max and stats.fc_max.max %}  // ✅ Utilise max
{
    y: {{ stats.fc_max.max }},
    label: { text: 'Max ({{ stats.fc_max.max|int }} bpm)' }
}
{% endif %}
```

#### B. En-tête FC max (ligne ~358-360)

**Avant** :
```html
{% if stats.fc_max and stats.fc_max.moyenne %}
    <span>(max: {{ stats.fc_max.moyenne|int }} bpm)</span>  <!-- ❌ -->
{% endif %}
```

**Après** :
```html
{% if stats.fc_max and stats.fc_max.max %}
    <span>(max: {{ stats.fc_max.max|int }} bpm)</span>  <!-- ✅ -->
{% endif %}
```

#### C. En-tête Allure max (ligne ~388-391)

**Avant** :
```html
{% if stats.allure and stats.allure.max %}  <!-- ❌ Max = plus lent -->
    {% set allure_max_stat = stats.allure.max %}
    <span>(max: {{ allure_max_stat|int }}:...)</span>
{% endif %}
```

**Après** :
```html
{% if stats.allure and stats.allure.min %}  <!-- ✅ Min = plus rapide -->
    {% set allure_max_stat = stats.allure.min %}
    <span>(max: {{ allure_max_stat|int }}:...)</span>
{% endif %}
```

**Résultat** :
- **Ligne FC max** : Affiche le max des FC max (valeur la plus élevée)
- **En-tête FC max** : Affiche la même valeur cohérente
- **En-tête Allure max** : Affiche la meilleure allure (min numérique = plus rapide)

---

## 📊 RÉSUMÉ DES CHANGEMENTS

### Fichiers modifiés
1. ✅ `templates/index.html` (3 corrections appliquées)
2. ✅ `app.py` (1 correction appliquée)

### Templates/index.html - Lignes modifiées
1. **Position label FC max** : ligne ~678 (left → right)
2. **Position label Allure "Cible"** : ligne ~795 (ajout offsetY: -10)
3. **Position label Allure "Moy"** : ligne ~818 (ajout offsetY: 10)
4. **Ligne FC max graphique** : ligne ~669-686 (fc_max.moyenne → fc_max.max)
5. **En-tête FC max** : ligne ~358-360 (fc_max.moyenne → fc_max.max)
6. **En-tête Allure max** : ligne ~388-391 (allure.max → allure.min)

### app.py - Lignes modifiées
7. **Sparklines avec run actuel** : lignes ~1189-1243 (ajout valeur actuelle après comparaisons)

### Tests effectués
```bash
✅ Template Jinja2 parsé sans erreur
✅ app.py compilé sans erreur
✅ Syntaxe JavaScript valide
✅ Logique calculate_running_stats.py vérifiée
```

---

## 🎯 RÉSULTATS ATTENDUS

### Graphique FC
```
Ligne rouge pointillée "Max (167 bpm)"
↑ Position : droite (non coupé)
↑ Valeur : max des FC max (167 = max absolu observé)
```

### Graphique Allure
```
Ligne rouge pointillée "Cible 5:20"
↑ Position : au-dessus de la ligne

Ligne verte pointillée "Moy (5:25)"
↓ Position : en-dessous de la ligne
```

### En-têtes
```
FC max : 166 bpm (max: 167 bpm)
           ↑ Cohérent avec ligne graphique

Allure max : 4:58 /km (max: 5:00)
                         ↑ Meilleure allure (min numérique)
```

### Sparklines
```
Efficacité Cardio: [...5.8, 6.1, 6.3, 7.35]
                                      ↑ Valeur actuelle (dernier point)

Dérive Cardio: [...1.15, 1.20, 1.18, 1.335]
                                      ↑ Valeur actuelle (dernier point)
```

---

## ✅ VALIDATION FINALE

**Toutes les 4 corrections ont été appliquées avec succès.**

### Checklist
- ✅ Labels annotations sans backgrounds (déjà fait)
- ✅ Positions labels corrigées (évite coupure/superposition)
- ✅ Sparklines incluent le run actuel
- ✅ Valeurs correctes pour lignes FC max et Allure max

---

**Prochaine étape : Test visuel sur le dashboard** 🎉
