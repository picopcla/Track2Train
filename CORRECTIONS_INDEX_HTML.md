# ✅ CORRECTIONS MULTIPLES - templates/index.html

## 📅 Date
2025-11-09

---

## 1. ✅ SPARKLINES EFFICACITÉ/DÉRIVE - Lignes de référence ajoutées

### Modification
Ajout de lignes horizontales représentant la moyenne du type de run sur les mini-graphiques (sparklines).

### Implémentation

**Sparkline Dérive Cardio** (ligne ~966) :
```javascript
annotations: {
    yaxis: [
        {% if running_stats and running_stats.stats_by_type %}
            {% set current_type = act.type_sortie %}
            {% if current_type in running_stats.stats_by_type %}
                {% set stats = running_stats.stats_by_type[current_type] %}
                {% if stats.deriv_cardio and stats.deriv_cardio.moyenne %}
        {
            y: {{ stats.deriv_cardio.moyenne }},
            borderColor: '#999',
            strokeDashArray: 3,
            borderWidth: 1
        }
                {% endif %}
            {% endif %}
        {% endif %}
    ]
}
```

**Sparkline Efficacité Cardio** (ligne ~1031) :
```javascript
annotations: {
    yaxis: [
        {% if running_stats and running_stats.stats_by_type %}
            {% set current_type = act.type_sortie %}
            {% if current_type in running_stats.stats_by_type %}
                {% set stats = running_stats.stats_by_type[current_type] %}
                {% if stats.k_moy and stats.k_moy.moyenne %}
        {
            y: {{ stats.k_moy.moyenne }},
            borderColor: '#999',
            strokeDashArray: 3,
            borderWidth: 1
        }
                {% endif %}
            {% endif %}
        {% endif %}
    ]
}
```

**Résultat** :
- Ligne grise fine pointillée (#999) sur chaque sparkline
- Représente la moyenne des 15 derniers runs du même type
- Permet de visualiser rapidement si la valeur actuelle est au-dessus ou en-dessous de la moyenne

---

## 2. ✅ ALLURE GRANDE (4:56) - Mise en forme améliorée

### Modification
- Le chiffre "4:56" est maintenant en **font-weight: bold**
- Le "/km" agrandi de 0.65rem à **1.2rem**
- Alignement vertical du "/km" avec le bas du chiffre (baseline)

### Code modifié (ligne ~236) :
```html
<div style="display: flex; align-items: baseline; gap: 0.3rem;">
    <span style="font-size: 2.5rem; font-weight: bold; color: #1f2937; line-height: 1;">{{ act.allure }}</span>
    <span style="color: #9ca3af; font-size: 1.2rem;">/km</span>
</div>
```

**Avant** :
```
4:56
/km  (très petit, mal aligné)
```

**Après** :
```
4:56 /km  (proportionné et aligné)
```

---

## 3. ✅ GRAPHIQUES - Cadres colorés supprimés, textes colorés conservés

### Modifications

#### A. Graphique FC - Ligne "Moyenne" supprimée
**Supprimé** : Ligne horizontale pointillée "FC moy" avec label bleu
**Conservé** : Ligne horizontale pointillée "FC max" avec label rouge (sans background)

**Avant** (ligne ~612-629) :
```javascript
{
    y: {{ stats.fc_moyenne.moyenne }},
    borderColor: '#3b82f6',
    label: {
        style: {
            color: '#fff',
            background: '#3b82f6'  // ❌ Cadre coloré
        }
    }
}
```

**Après** (supprimée complètement)

#### B. Graphique FC - Label "Max" sans background
**Modifié** (ligne ~619) :
```javascript
{
    y: {{ stats.fc_max.moyenne }},
    borderColor: '#dc2626',
    label: {
        text: 'Max ({{ stats.fc_max.moyenne|int }} bpm)',
        style: {
            color: '#dc2626',      // ✅ Texte rouge
            fontWeight: 'bold',
            fontSize: '10px'
            // ✅ Pas de background
        }
    }
}
```

#### C. Graphique Allure - Labels sans backgrounds
**Ligne cible "5:20"** (ligne ~733) :
```javascript
label: {
    text: 'Cible 5:20',
    style: {
        color: '#dc2626',      // ✅ Texte rouge
        fontWeight: 'bold',
        fontSize: '10px'
        // ✅ Pas de background rouge
    }
}
```

**Ligne moyenne** (ligne ~755) :
```javascript
label: {
    text: 'Moy (5:25)',  // Format mm:ss
    style: {
        color: '#16a34a',      // ✅ Texte vert
        fontWeight: 'bold',
        fontSize: '10px'
        // ✅ Pas de background vert
    }
}
```

**Résultat** :
- ❌ Supprimé : Cadres avec fond coloré (background)
- ✅ Conservé : Textes en gras colorés (rouge/vert)
- ✅ Conservé : Lignes horizontales pointillées

---

## 4. ✅ EN-TÊTE GRAPHIQUE FC - Moyennes du type de run ajoutées

### Modification
Ajout des valeurs moyennes entre parenthèses à côté des valeurs actuelles.

### Code modifié (ligne ~341) :
```html
<div style="display: flex; gap: 2rem; margin: 0.5rem 0 0.3rem 0; font-size: 0.9rem; color: #666;">
    <span>FC moyenne : <strong style="color: #1f2937;">{{ act.fc_moy }} bpm</strong>
        {% if running_stats and running_stats.stats_by_type %}
            {% set current_type = act.type_sortie %}
            {% if current_type in running_stats.stats_by_type %}
                {% set stats = running_stats.stats_by_type[current_type] %}
                {% if stats.fc_moyenne and stats.fc_moyenne.moyenne %}
                    <span style="color: #9ca3af; font-size: 0.85rem;">(moy: {{ stats.fc_moyenne.moyenne|int }} bpm)</span>
                {% endif %}
            {% endif %}
        {% endif %}
    </span>
    <span>FC max : <strong style="color: #1f2937;">{{ act.fc_max }} bpm</strong>
        {% if running_stats and running_stats.stats_by_type %}
            {% set current_type = act.type_sortie %}
            {% if current_type in running_stats.stats_by_type %}
                {% set stats = running_stats.stats_by_type[current_type] %}
                {% if stats.fc_max and stats.fc_max.moyenne %}
                    <span style="color: #9ca3af; font-size: 0.85rem;">(max: {{ stats.fc_max.moyenne|int }} bpm)</span>
                {% endif %}
            {% endif %}
        {% endif %}
    </span>
</div>
```

**Avant** :
```
FC moyenne : 145 bpm    FC max : 167 bpm
```

**Après** :
```
FC moyenne : 145 bpm (moy: 141 bpm)    FC max : 167 bpm (max: 156 bpm)
```

---

## 5. ✅ EN-TÊTE GRAPHIQUE ALLURE - Ligne similaire créée

### Modification
Création d'une nouvelle ligne au-dessus du graphique Allure avec le même style que l'en-tête FC.

### Code ajouté (ligne ~366) :
```html
<!-- Allure Moyenne et Max (style épuré) -->
<div style="display: flex; gap: 2rem; margin: 1rem 0 0.3rem 0; font-size: 0.9rem; color: #666;">
    <span>Allure moyenne : <strong style="color: #1f2937;">{{ act.allure }}</strong>
        {% if running_stats and running_stats.stats_by_type %}
            {% set current_type = act.type_sortie %}
            {% if current_type in running_stats.stats_by_type %}
                {% set stats = running_stats.stats_by_type[current_type] %}
                {% if stats.allure and stats.allure.moyenne %}
                    {% set allure_moy = stats.allure.moyenne %}
                    <span style="color: #9ca3af; font-size: 0.85rem;">(moy: {{ allure_moy|int }}:{{ "%02d"|format(((allure_moy - allure_moy|int) * 60)|int) }})</span>
                {% endif %}
            {% endif %}
        {% endif %}
    </span>
    <span>Allure max : <strong style="color: #1f2937;" id="allureMax{{ loop.index0 }}">-</strong>
        {% if running_stats and running_stats.stats_by_type %}
            {% set current_type = act.type_sortie %}
            {% if current_type in running_stats.stats_by_type %}
                {% set stats = running_stats.stats_by_type[current_type] %}
                {% if stats.allure and stats.allure.max %}
                    {% set allure_max_stat = stats.allure.max %}
                    <span style="color: #9ca3af; font-size: 0.85rem;">(max: {{ allure_max_stat|int }}:{{ "%02d"|format(((allure_max_stat - allure_max_stat|int) * 60)|int) }})</span>
                {% endif %}
            {% endif %}
        {% endif %}
    </span>
</div>
```

### JavaScript pour calculer allure max actuelle (ligne ~556) :
```javascript
// Afficher l'allure max formatée
const allureMaxMin{{ loop.index0 }} = Math.floor(allureMax{{ loop.index0 }});
const allureMaxSec{{ loop.index0 }} = Math.round((allureMax{{ loop.index0 }} - allureMaxMin{{ loop.index0 }}) * 60);
const allureMaxElement{{ loop.index0 }} = document.getElementById('allureMax{{ loop.index0 }}');
if (allureMaxElement{{ loop.index0 }}) {
    allureMaxElement{{ loop.index0 }}.textContent = allureMaxMin{{ loop.index0 }} + ':' + (allureMaxSec{{ loop.index0 }} < 10 ? '0' : '') + allureMaxSec{{ loop.index0 }} + ' /km';
}
```

**Résultat** :
```
Allure moyenne : 5:23 /km (moy: 5:25)    Allure max : 4:58 /km (max: 5:48)
```

---

## 📊 RÉSUMÉ DES CHANGEMENTS

### Fichiers modifiés
- ✅ `templates/index.html` (5 corrections appliquées)

### Tests effectués
```bash
✅ Template Jinja2 parsé sans erreur
✅ Syntaxe JavaScript valide
✅ Toutes les variables requises sont disponibles
```

### Améliorations visuelles
1. **Sparklines** : Lignes de référence pour contexte visuel immédiat
2. **Allure grande** : Meilleure lisibilité avec /km proportionné
3. **Labels graphiques** : Textes colorés sans cadres (design épuré)
4. **En-têtes** : Comparaisons instantanées avec moyennes du type de run
5. **Cohérence** : Style uniforme entre graphiques FC et Allure

---

## ✅ VALIDATION

**Toutes les corrections demandées ont été appliquées avec succès.**

Prochaine étape : Tester visuellement sur le dashboard.
