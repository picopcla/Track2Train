# ✅ ÉTAPE 1 : CALCUL ET SAUVEGARDE DES STATS PAR TYPE DE RUN

## 📊 Ce qui a été créé

### 1. Script de calcul : `calculate_running_stats.py`

**Fonctionnalités** :
- ✅ Calcule les moyennes des **15 dernières courses PAR TYPE** (5k, 10k, long_run)
- ✅ Pour chaque type, extrait :
  - FC moyenne (moyenne, min, max)
  - FC max (moyenne, min, max)
  - Allure (moyenne, min, max)
  - k_moy (moyenne, min, max, tendance)
  - Dérive cardio (moyenne, min, max)
  - Distance moyenne
- ✅ Sauvegarde dans `running_stats.json`
- ✅ Affichage formaté dans le terminal

**Usage** :
```bash
.venv/bin/python3 calculate_running_stats.py
```

---

### 2. Fichier de stats : `running_stats.json`

**Structure** :
```json
{
  "generated_at": "2025-11-09T08:56:51",
  "stats_by_type": {
    "normal_5k": {
      "nombre_courses": 15,
      "fc_moyenne": { "moyenne": 141.2, "min": 129.9, "max": 152.0 },
      "fc_max": { "moyenne": 156.4, "min": 143.0, "max": 167.0 },
      "allure": { "moyenne": 5.43, "min": 5.0, "max": 5.8 },
      "k_moy": { "moyenne": 6.01, "min": 4.68, "max": 7.35, "tendance": "hausse" },
      "deriv_cardio": { "moyenne": 1.182, "min": 0.992, "max": 1.335 }
    },
    "normal_10k": { ... },
    "long_run": { ... }
  }
}
```

**Résultats actuels** :

🏃 **5K** (15 courses)
- FC moyenne : 141 bpm (range: 130-152)
- FC max : 156 bpm (range: 143-167)
- Allure : 5:25/km (range: 5:00-5:47)
- k_moy : 6.01 (📈 en hausse)
- Dérive : 1.182 (🟡 acceptable)

🏃 **10K** (15 courses)
- FC moyenne : 143 bpm (range: 135-153)
- FC max : 160 bpm (range: 150-174)
- Allure : 5:31/km (range: 5:13-6:04)
- k_moy : 6.00 (📉 en baisse)
- Dérive : 1.155 (🟡 acceptable)

🏃 **LONG RUN** (15 courses)
- FC moyenne : 147 bpm (range: 139-153)
- FC max : 163 bpm (range: 153-178)
- Allure : 6:05/km (range: 5:32-7:57)
- k_moy : 5.32 (📉 en baisse)
- Dérive : 1.031 (🟢 excellent)

---

### 3. Intégration webhook : `INTEGRATION_WEBHOOK.py`

**Instructions pour intégrer dans `app.py`** :

#### A. Import (ligne ~17)
```python
from calculate_running_stats import calculate_stats_by_type, save_running_stats
```

#### B. Fonction de mise à jour (après les autres fonctions)
```python
def update_running_stats_after_webhook():
    """Met à jour les stats après chaque nouveau run"""
    try:
        activities = load_activities_from_drive()
        stats_by_type = calculate_stats_by_type(activities, n_last=15)
        save_running_stats(stats_by_type, 'running_stats.json')
        print("✅ Running stats mises à jour")
        return stats_by_type
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return None
```

#### C. Appel dans le webhook (ligne ~1500)
```python
@app.route('/webhook', methods=['POST'])
def webhook():
    # ... code existant ...
    save_activities_to_drive(activities)

    # 🆕 NOUVEAU
    update_running_stats_after_webhook()

    return jsonify({"status": "ok"})
```

#### D. Chargement dans index() (ligne ~1000)
```python
@app.route('/')
def index():
    # ... code existant ...

    # 🆕 Charger running stats
    running_stats = {}
    if os.path.exists('running_stats.json'):
        with open('running_stats.json', 'r') as f:
            running_stats = json.load(f)

    return render_template(
        'index.html',
        running_stats=running_stats,  # 🆕 Passer au template
        # ... autres variables ...
    )
```

---

## 🎨 UTILISATION DANS LES GRAPHIQUES ApexCharts

### Objectif
Afficher des **lignes de référence** sur les graphiques pour comparer le run actuel aux moyennes :
- Ligne FC moyenne (par type de run)
- Ligne FC max moyenne
- Ligne allure moyenne
- Ligne k_moy moyenne
- Ligne dérive moyenne

---

### Code pour ajouter les lignes de référence

#### Dans `templates/index.html`, modifier les graphiques :

**1. Graphique FC** (ajouter annotation FC moyenne) :

```javascript
const optionsFC{{ loop.index0 }} = {
    // ... config existante ...
    annotations: {
        yaxis: [
            // 🆕 Ligne FC moyenne (selon type de run)
            {% if running_stats and running_stats.stats_by_type %}
                {% set current_type = act.type_sortie %}
                {% if current_type in running_stats.stats_by_type %}
                    {% set stats = running_stats.stats_by_type[current_type] %}
                    {
                        y: {{ stats.fc_moyenne.moyenne }},
                        borderColor: '#3b82f6',
                        strokeDashArray: 5,
                        borderWidth: 2,
                        label: {
                            text: 'FC moy {{ current_type }} ({{ stats.fc_moyenne.moyenne|int }} bpm)',
                            position: 'left',
                            style: {
                                color: '#fff',
                                background: '#3b82f6',
                                fontSize: '9px'
                            }
                        }
                    },
                    // 🆕 Ligne FC max moyenne
                    {
                        y: {{ stats.fc_max.moyenne }},
                        borderColor: '#dc2626',
                        strokeDashArray: 3,
                        borderWidth: 1,
                        label: {
                            text: 'FC max moy ({{ stats.fc_max.moyenne|int }} bpm)',
                            position: 'left',
                            style: {
                                color: '#fff',
                                background: '#dc2626',
                                fontSize: '9px'
                            }
                        }
                    }
                {% endif %}
            {% endif %}
        ]
    }
};
```

**2. Graphique Allure** (ajouter annotation allure moyenne) :

```javascript
const optionsAllure{{ loop.index0 }} = {
    // ... config existante ...
    annotations: {
        yaxis: [
            // 🆕 Ligne allure moyenne (selon type de run)
            {% if running_stats and running_stats.stats_by_type %}
                {% set current_type = act.type_sortie %}
                {% if current_type in running_stats.stats_by_type %}
                    {% set stats = running_stats.stats_by_type[current_type] %}
                    {
                        y: {{ stats.allure.moyenne }},
                        borderColor: '#16a34a',
                        strokeDashArray: 5,
                        borderWidth: 2,
                        label: {
                            text: 'Allure moy {{ current_type }}',
                            position: 'right',
                            style: {
                                color: '#fff',
                                background: '#16a34a',
                                fontSize: '9px'
                            }
                        }
                    }
                {% endif %}
            {% endif %}
        ]
    }
};
```

**3. Card k_moy** (afficher comparaison à la moyenne) :

```html
<div style="background: #f0f9ff; border-left: 4px solid #775DD0; padding: 0.8rem;">
    <div style="font-size: 0.75rem; color: #666;">Efficacité Cardio</div>
    <div style="font-size: 1.3rem; font-weight: bold; color: #775DD0;">
        {{ act.k_moy if act.k_moy != '-' else 'N/A' }}
    </div>

    {% if running_stats and running_stats.stats_by_type %}
        {% set current_type = act.type_sortie %}
        {% if current_type in running_stats.stats_by_type %}
            {% set stats = running_stats.stats_by_type[current_type] %}
            {% set diff = act.k_moy - stats.k_moy.moyenne if act.k_moy else 0 %}
            <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.2rem;">
                Moyenne {{ current_type }}: {{ stats.k_moy.moyenne }}
                {% if diff > 0.3 %}
                    <span style="color: #16a34a;">↗ +{{ "%.1f"|format(diff) }}</span>
                {% elif diff < -0.3 %}
                    <span style="color: #dc2626;">↘ {{ "%.1f"|format(diff) }}</span>
                {% else %}
                    <span style="color: #6b7280;">→ Similaire</span>
                {% endif %}
            </div>
        {% endif %}
    {% endif %}
</div>
```

**4. Card dérive cardio** (afficher comparaison) :

```html
<div style="background: #fff7ed; border-left: 4px solid #FF9800; padding: 0.8rem;">
    <div style="font-size: 0.75rem; color: #666;">Dérive Cardio</div>
    <div style="font-size: 1.3rem; font-weight: bold; color: #FF9800;">
        {{ act.deriv_cardio if act.deriv_cardio else 'N/A' }}
    </div>

    {% if running_stats and running_stats.stats_by_type %}
        {% set current_type = act.type_sortie %}
        {% if current_type in running_stats.stats_by_type %}
            {% set stats = running_stats.stats_by_type[current_type] %}
            {% set diff_pct = ((act.deriv_cardio - stats.deriv_cardio.moyenne) / stats.deriv_cardio.moyenne * 100) if act.deriv_cardio else 0 %}
            <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.2rem;">
                Moyenne {{ current_type }}: {{ "%.2f"|format(stats.deriv_cardio.moyenne) }}
                {% if diff_pct > 10 %}
                    <span style="color: #dc2626;">🔴 +{{ "%.0f"|format(diff_pct) }}%</span>
                {% elif diff_pct > 5 %}
                    <span style="color: #f59e0b;">🟠 +{{ "%.0f"|format(diff_pct) }}%</span>
                {% elif diff_pct < -5 %}
                    <span style="color: #16a34a;">🟢 {{ "%.0f"|format(diff_pct) }}%</span>
                {% else %}
                    <span style="color: #6b7280;">→ Normal</span>
                {% endif %}
            </div>
        {% endif %}
    {% endif %}
</div>
```

---

## 📋 CHECKLIST D'INTÉGRATION

### Backend (app.py)
- [ ] Importer `calculate_running_stats`
- [ ] Créer fonction `update_running_stats_after_webhook()`
- [ ] Appeler dans route `/webhook`
- [ ] Charger `running_stats.json` dans route `index()`
- [ ] Passer `running_stats` au template

### Frontend (templates/index.html)
- [ ] Ajouter lignes de référence sur graphique FC
- [ ] Ajouter ligne de référence sur graphique Allure
- [ ] Afficher comparaison dans card k_moy
- [ ] Afficher comparaison dans card dérive cardio

### Test
- [ ] Exécuter `calculate_running_stats.py` manuellement
- [ ] Vérifier `running_stats.json` généré
- [ ] Recharger la page index
- [ ] Vérifier que les lignes de référence s'affichent
- [ ] Simuler un webhook et vérifier la mise à jour

---

## 🎯 RÉSULTAT ATTENDU

Après intégration, chaque graphique affichera :
1. **Les données du run actuel** (courbe existante)
2. **Les lignes de référence** (moyennes des 15 derniers runs du MÊME TYPE)
3. **Comparaisons visuelles** dans les cards (↗ au-dessus / ↘ en-dessous / → similaire)

**Exemple visuel** :
```
Graphique FC :
- Courbe rouge : FC du run actuel
- Ligne bleue pointillée : FC moyenne des 15 derniers 5K (141 bpm)
- Ligne rouge pointillée : FC max moyenne des 15 derniers 5K (156 bpm)

Card k_moy :
k_moy : 7.3
Moyenne normal_5k: 6.0
↗ +1.3 (🟢 AU-DESSUS DE LA MOYENNE)
```

---

## ✅ VALIDATION ÉTAPE 1

**Est-ce que cette approche te convient ?**

Si oui, je passe à l'**ÉTAPE 2** :
- Génération de l'analyse IA (points forts/faibles)
- Création du prompt
- Sauvegarde dans `analyses/`
- Bouton d'accès depuis `index.html`

Si non, dis-moi ce qu'il faut ajuster ! 👍
