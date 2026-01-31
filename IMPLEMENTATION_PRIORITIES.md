# 🚀 PRIORITÉS D'IMPLÉMENTATION
## Dashboard Track2Train - Homme 52 ans

---

## ⚡ PHASE 1 : CRITIQUE (À FAIRE EN PREMIER)

### 1. Alerte Dérive Cardio (bandeau en haut de page)

**Fichier** : `templates/index.html`

**Code à ajouter** (après le header, avant le carrousel) :

```html
{% if act.deriv_cardio and act.deriv_cardio > 1.25 %}
<div style="background: #fee2e2; border-left: 4px solid #ef4444; padding: 1rem; border-radius: 8px; margin: 1rem 0;">
    <div style="display: flex; align-items: center; gap: 1rem;">
        <div style="font-size: 2rem;">🔴</div>
        <div>
            <h3 style="margin: 0; color: #991b1b; font-size: 1.1rem;">Alerte Dérive Cardio</h3>
            <p style="margin: 0.5rem 0 0 0; color: #7f1d1d;">
                Ta dernière sortie montre une <strong>dérive de {{ act.deriv_cardio }}</strong> avec une FC qui augmente fortement.
                🎯 <strong>Conseil :</strong> Pars plus progressivement à ta prochaine sortie (110 bpm) et reste en Zone 2 (FC < 120 bpm).
            </p>
        </div>
    </div>
</div>
{% endif %}
```

**Impact** : Alerte immédiate si l'utilisateur court trop fort

---

### 2. Score Dérive Cardio (grosse jauge colorée)

**Fichier** : `templates/index.html` (dans la section cards)

**Code à ajouter** :

```html
<div style="background: {% if act.deriv_cardio < 1.05 %}#dcfce7{% elif act.deriv_cardio < 1.15 %}#fef3c7{% elif act.deriv_cardio < 1.25 %}#fed7aa{% else %}#fee2e2{% endif %};
            border-left: 4px solid {% if act.deriv_cardio < 1.05 %}#16a34a{% elif act.deriv_cardio < 1.15 %}#ca8a04{% elif act.deriv_cardio < 1.25 %}#ea580c{% else %}#dc2626{% endif %};
            padding: 1rem; border-radius: 8px; text-align: center;">
    <div style="font-size: 0.75rem; color: #666; margin-bottom: 0.5rem;">Score Dérive Cardio</div>
    <div style="font-size: 3rem; font-weight: bold;">
        {% if act.deriv_cardio < 1.05 %}🟢{% elif act.deriv_cardio < 1.15 %}🟡{% elif act.deriv_cardio < 1.25 %}🟠{% else %}🔴{% endif %}
    </div>
    <div style="font-size: 1.8rem; font-weight: bold; margin: 0.5rem 0;">{{ act.deriv_cardio }}</div>
    <div style="font-size: 0.8rem; color: #666;">
        {% if act.deriv_cardio < 1.05 %}Excellent - Effort bien géré
        {% elif act.deriv_cardio < 1.15 %}Bon - Légère fatigue cardio
        {% elif act.deriv_cardio < 1.25 %}Attention - Effort trop intense
        {% else %}Alerte - Réduire intensité{% endif %}
    </div>
</div>
```

**Impact** : Feedback visuel immédiat sur la qualité de l'effort

---

### 3. Distribution temps par Zone FC (backend)

**Fichier** : `app.py`

**Fonction à ajouter** (après la fonction `enrich_single_activity`) :

```python
def calculate_zone_distribution(points, fc_max=168):
    """Calcule le % de temps passé dans chaque zone FC"""
    if not points:
        return None

    zones = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = 0

    for p in points:
        hr = p.get('hr')
        if hr is None:
            continue

        total += 1

        # Zones basées sur % de FC max
        if hr < fc_max * 0.60:  # < 101 bpm
            zones[1] += 1
        elif hr < fc_max * 0.70:  # 101-117 bpm
            zones[2] += 1
        elif hr < fc_max * 0.80:  # 117-134 bpm
            zones[3] += 1
        elif hr < fc_max * 0.90:  # 134-151 bpm
            zones[4] += 1
        else:  # >= 151 bpm
            zones[5] += 1

    if total == 0:
        return None

    return {
        'zone_1_pct': round((zones[1] / total) * 100, 1),
        'zone_2_pct': round((zones[2] / total) * 100, 1),
        'zone_3_pct': round((zones[3] / total) * 100, 1),
        'zone_4_pct': round((zones[4] / total) * 100, 1),
        'zone_5_pct': round((zones[5] / total) * 100, 1)
    }

# Appeler dans enrich_single_activity() :
# activity['zone_distribution'] = calculate_zone_distribution(activity.get('points', []))
```

**Affichage** : `templates/index.html`

```html
{% if act.zone_distribution %}
<div style="background: #f9fafb; padding: 1rem; border-radius: 8px;">
    <div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">Temps par Zone FC</div>

    <div style="display: flex; height: 30px; border-radius: 6px; overflow: hidden;">
        <div style="background: #dcfce7; width: {{ act.zone_distribution.zone_1_pct }}%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; color: #166534;">
            {{ act.zone_distribution.zone_1_pct }}%
        </div>
        <div style="background: #86efac; width: {{ act.zone_distribution.zone_2_pct }}%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; color: #166534; font-weight: bold;">
            Z2: {{ act.zone_distribution.zone_2_pct }}% 🎯
        </div>
        <div style="background: #fef3c7; width: {{ act.zone_distribution.zone_3_pct }}%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; color: #854d0e;">
            {{ act.zone_distribution.zone_3_pct }}%
        </div>
        <div style="background: #fed7aa; width: {{ act.zone_distribution.zone_4_pct }}%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; color: #9a3412;">
            {{ act.zone_distribution.zone_4_pct }}%
        </div>
        <div style="background: #fecaca; width: {{ act.zone_distribution.zone_5_pct }}%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; color: #991b1b;">
            {{ act.zone_distribution.zone_5_pct }}%
        </div>
    </div>

    <div style="font-size: 0.7rem; color: #666; margin-top: 0.5rem; text-align: center;">
        🎯 Objectif : 60% en Zone 2 (FC 101-117 bpm)
    </div>
</div>
{% endif %}
```

**Impact** : L'utilisateur voit immédiatement qu'il passe trop de temps en zones 4-5

---

## ⚡ PHASE 2 : HAUTE PRIORITÉ

### 4. Variabilité FC intra-course

**Backend** (`app.py`) :

```python
def calculate_fc_variability(points):
    """Calcule la variabilité de FC pendant la course"""
    hrs = [p.get('hr') for p in points if p.get('hr') is not None]
    if len(hrs) < 10:
        return None

    fc_min = min(hrs)
    fc_max = max(hrs)

    variability = ((fc_max - fc_min) / fc_min) * 100
    return round(variability, 1)

# Appeler dans enrich_single_activity() :
# activity['fc_variability_pct'] = calculate_fc_variability(activity.get('points', []))
```

**Frontend** (`index.html`) :

```html
<div style="background: #f0f9ff; padding: 0.8rem; border-radius: 8px;">
    <div style="font-size: 0.75rem; color: #666;">Variabilité FC</div>
    <div style="font-size: 1.3rem; font-weight: bold; color: {% if act.fc_variability_pct < 15 %}#16a34a{% elif act.fc_variability_pct < 25 %}#ca8a04{% else %}#dc2626{% endif %};">
        {{ act.fc_variability_pct }}%
    </div>
    <div style="font-size: 0.7rem; color: #666;">
        {% if act.fc_variability_pct < 15 %}🟢 Effort constant
        {% elif act.fc_variability_pct < 25 %}🟡 Gestion moyenne
        {% else %}🔴 Départ trop brutal{% endif %}
    </div>
</div>
```

---

### 5. Zones colorées sur graphique FC (ApexCharts)

**Fichier** : `templates/index.html` (dans le graphique FC existant)

**Modifier le graphique FC pour ajouter les zones** :

```javascript
const optionsFC{{ loop.index0 }} = {
    // ... config existante ...
    annotations: {
        yaxis: [
            // Zone 1 (84-101 bpm)
            {
                y: 84,
                y2: 101,
                fillColor: '#dcfce7',
                opacity: 0.2,
                borderColor: 'transparent',
                label: {
                    text: 'Z1',
                    position: 'left',
                    style: { fontSize: '9px', color: '#16a34a' }
                }
            },
            // Zone 2 (101-117 bpm) - CIBLE
            {
                y: 101,
                y2: 117,
                fillColor: '#86efac',
                opacity: 0.3,
                borderColor: '#16a34a',
                borderWidth: 2,
                label: {
                    text: 'Zone 2 🎯',
                    position: 'left',
                    style: { fontSize: '10px', color: '#16a34a', fontWeight: 'bold' }
                }
            },
            // Zone 3 (117-134 bpm)
            {
                y: 117,
                y2: 134,
                fillColor: '#fef3c7',
                opacity: 0.2,
                borderColor: 'transparent'
            },
            // Zone 4 (134-151 bpm)
            {
                y: 134,
                y2: 151,
                fillColor: '#fed7aa',
                opacity: 0.2,
                borderColor: 'transparent'
            },
            // Zone 5 (151-168 bpm)
            {
                y: 151,
                y2: 168,
                fillColor: '#fecaca',
                opacity: 0.3,
                borderColor: 'transparent'
            },
            // Ligne limite Zone 2
            {
                y: 120,
                borderColor: '#16a34a',
                strokeDashArray: 5,
                borderWidth: 2,
                label: {
                    text: 'Limite Z2',
                    position: 'right',
                    style: { color: '#fff', background: '#16a34a', fontSize: '9px' }
                }
            }
        ]
    }
};
```

**Impact** : L'utilisateur voit instantanément quand il sort de la Zone 2

---

### 6. Évolution dérive cardio (graphique ligne)

**Frontend** (`index.html`) - Ajouter un nouveau graphique :

```html
<div class="sub-header">
    <h2>📉 Évolution Dérive Cardio (20 dernières courses)</h2>
</div>

<div id="chartDerivTrend"></div>

<script>
const derivTrendData = [
    {% for act in activities_for_carousel %}
    { x: '{{ act.date[:10] }}', y: {{ act.deriv_cardio if act.deriv_cardio else 'null' }} }{% if not loop.last %},{% endif %}
    {% endfor %}
].filter(d => d.y !== null);

const optionsDerivTrend = {
    series: [{ name: 'Dérive Cardio', data: derivTrendData }],
    chart: { type: 'line', height: 200 },
    stroke: { width: 3, curve: 'smooth', colors: ['#f97316'] },
    annotations: {
        yaxis: [
            { y: 1.05, borderColor: '#16a34a', strokeDashArray: 5, label: { text: 'Excellent < 1.05', style: { background: '#16a34a' } } },
            { y: 1.15, borderColor: '#ca8a04', strokeDashArray: 5, label: { text: 'Bon < 1.15', style: { background: '#ca8a04' } } },
            { y: 1.25, borderColor: '#dc2626', strokeDashArray: 5, label: { text: 'Alerte > 1.25', style: { background: '#dc2626' } } }
        ]
    },
    yaxis: {
        title: { text: 'Dérive Cardio' },
        min: 0.9,
        max: 1.5
    },
    xaxis: {
        type: 'datetime',
        title: { text: 'Date' }
    }
};

const chartDerivTrend = new ApexCharts(document.querySelector('#chartDerivTrend'), optionsDerivTrend);
chartDerivTrend.render();
</script>
```

**Impact** : Visualiser la tendance sur le long terme

---

## 📊 PHASE 3 : MOYENNE PRIORITÉ

### 7. Allure en Zone 2 (progression aérobie)

**Backend** :

```python
def calculate_allure_in_zone2(points, fc_max=168):
    """Calcule l'allure moyenne quand on est en Zone 2"""
    z2_min = fc_max * 0.60  # 101 bpm
    z2_max = fc_max * 0.70  # 117 bpm

    allures_z2 = []
    for p in points:
        hr = p.get('hr')
        vel = p.get('vel')
        if hr and vel and z2_min <= hr <= z2_max and vel > 0:
            allure = 16.6667 / vel
            allures_z2.append(allure)

    if not allures_z2:
        return None

    return round(np.mean(allures_z2), 2)
```

---

### 8. Prédictions 10K et Semi

**Backend** :

```python
def predict_10k_readiness(k_moy, deriv_cardio, zone_2_pct):
    """Prédit si l'utilisateur est prêt pour un 10K en Zone 2-3"""
    ready = k_moy > 6.5 and deriv_cardio < 1.15 and zone_2_pct > 40

    if ready:
        # Estimer temps basé sur allure en Z2-Z3
        estimated_time = "55-60 min"
        status = "✅ PRÊT"
        advice = "Tu peux tenter un 10K en Zone 2-3 (FC < 130 bpm)"
    else:
        estimated_time = "Non prêt"
        status = "⏳ PAS ENCORE"
        advice = "Continue à construire ta base aérobie en Zone 2"

    return {
        'ready': ready,
        'time': estimated_time,
        'status': status,
        'advice': advice
    }
```

---

## 📝 RÉSUMÉ DES PRIORITÉS

**PRIORITÉ 1 (URGENT - Santé)** :
1. ✅ Alerte dérive cardio > 1.25
2. ✅ Score dérive avec jauge colorée
3. ✅ Distribution temps par zone FC

**PRIORITÉ 2 (Important - Feedback)** :
4. ✅ Variabilité FC intra-course
5. ✅ Zones colorées sur graphique FC
6. ✅ Graphique évolution dérive

**PRIORITÉ 3 (Utile - Progression)** :
7. Allure en Zone 2
8. Prédictions 10K/Semi
9. FC repos (si disponible)

---

## 🎯 TEMPS D'IMPLÉMENTATION ESTIMÉ

- **Phase 1** : 2-3 heures (critique pour la santé)
- **Phase 2** : 3-4 heures (amélioration feedback)
- **Phase 3** : 2-3 heures (progression long terme)

**Total** : 7-10 heures de développement

---

## 💡 CONSEIL FINAL

**Commence par la Phase 1** - c'est le plus important pour la santé de l'utilisateur de 52 ans.

L'alerte dérive cardio va immédiatement l'aider à comprendre qu'il court trop fort et à adapter son entraînement.
