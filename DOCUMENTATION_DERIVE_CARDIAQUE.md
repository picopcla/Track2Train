# DOCUMENTATION - DÉRIVE CARDIAQUE

**Date de mise en œuvre**: 20 décembre 2025
**Version**: 2.0 (Calcul temporel)

---

## 📖 DÉFINITION

La **dérive cardiaque** (cardiac drift) mesure l'augmentation progressive de la fréquence cardiaque pour une même intensité d'effort au cours d'une séance de running.

**Principe physiologique**:
- Au début d'un run stable, le corps atteint un équilibre entre FC et allure
- Au fil du temps, la FC augmente progressivement (fatigue, déshydratation, température)
- Une dérive faible indique une bonne stabilité cardio-mécanique

**Unité**: Pourcentage (%)
**Interprétation**: Plus BAS = meilleur (moins de dégradation)

---

## 🔢 MÉTHODE DE CALCUL (Version 2.0)

### 1. PRÉTRAITEMENT

#### Exclusion systématique:
- **Les 5 premières minutes** (300 secondes)
  - Raison: Phase de montée cardiaque (warm-up)
  - Fallback: 300 mètres si durée < 5 min

#### Données filtrées:
- Pauses et arrêts exclus automatiquement
- Points avec FC ou vitesse invalides exclus

### 2. DIVISION TEMPORELLE

**CAS STANDARD** (par défaut - implémenté):
```
Portion analysée divisée en 2 moitiés TEMPORELLES égales

Première moitié: temps < mid_time
  → Calcul FC₁ (moyenne FC)
  → Calcul V₁ (moyenne vitesse)

Seconde moitié: temps ≥ mid_time
  → Calcul FC₂ (moyenne FC)
  → Calcul V₂ (moyenne vitesse)
```

**Validité**:
- Valable quelle que soit la distance (10 km, 15 km, 25 km)
- Durée minimale recommandée: ≥25-30 min après nettoyage

### 3. CALCUL DU RATIO CARDIO-MÉCANIQUE

```
R₁ = FC₁ / V₁   (première moitié)
R₂ = FC₂ / V₂   (seconde moitié)
```

Où:
- FC = Fréquence cardiaque moyenne (bpm)
- V = Vitesse moyenne (m/s)

### 4. CALCUL DE LA DÉRIVE

```
Dérive (%) = ((R₂ - R₁) / R₁) × 100
```

**Arrondi**: 0,1% (1 décimale)

---

## 💻 IMPLÉMENTATION

### Code (app.py lignes 1370-1397):

```python
# Division temporelle en 2 moitiés (CAS STANDARD)
deriv_cardio = "-"
if len(times_analysis) >= 10:
    duration_analysis = times_analysis[-1] - times_analysis[0]

    # Division en 2 moitiés temporelles
    mid_time = times_analysis[0] + duration_analysis / 2
    mask_first_half = times_analysis < mid_time
    mask_second_half = times_analysis >= mid_time

    # Première moitié: FC₁, V₁
    fc1 = np.mean(fcs_analysis[mask_first_half])
    v1 = np.mean(vels_analysis[mask_first_half])

    # Seconde moitié: FC₂, V₂
    fc2 = np.mean(fcs_analysis[mask_second_half])
    v2 = np.mean(vels_analysis[mask_second_half])

    # Calcul des ratios R = FC / V
    if v1 > 0 and v2 > 0:
        R1 = fc1 / v1
        R2 = fc2 / v2

        # Dérive (%) = ((R₂ - R₁) / R₁) × 100
        if R1 > 0:
            deriv_cardio_pct = ((R2 - R1) / R1) * 100
            deriv_cardio = round(deriv_cardio_pct, 1)
```

### Fichiers modifiés:
- `app.py` (lignes 1295-1397): Nouvelle méthode de calcul
- `activities.json`: Toutes les dérives recalculées
- `running_stats.json`: Nouvelles moyennes par type
- `profile.json`: Nouveaux objectifs (drift_target)

---

## 📊 RÉSULTATS (151 activités recalculées)

### Moyennes par type de run:

| Type de run    | Moyenne | Min     | Max    | Nombre |
|----------------|---------|---------|--------|--------|
| tempo_recup    | 6.7%    | -18.2%  | 14.6%  | 41     |
| tempo_rapide   | 9.0%    | -0.1%   | 17.7%  | 19     |
| endurance      | 6.7%    | -3.2%   | 17.5%  | 35     |
| long_run       | 13.8%   | 5.9%    | 21.1%  | 15     |

### Observations:

1. **Long runs**: Dérive la plus élevée (13.8%)
   - Physiologiquement cohérent (fatigue cumulative sur longue distance)
   - Objectif P40: 14.1%

2. **Tempo rapide**: Dérive modérée à élevée (9.0%)
   - Effort intense, fatigue rapide
   - Objectif P40: 9.2%

3. **Endurance et récupération**: Dérive basse (6.7%)
   - Allure confortable, meilleure stabilité
   - Objectifs P40: 8.4% et 6.6%

4. **Valeurs négatives**: Rares mais possibles
   - Indiquent une amélioration de l'efficacité en cours de run
   - Peuvent résulter d'un échauffement insuffisant ou conditions variables

---

## 🎯 OBJECTIFS (profile.json)

### Méthode de calcul:
- **Percentile 40 (P40)**: 40% de vos meilleures performances
- Ambitieux mais atteignable
- Plancher physiologique: 3.0% minimum

### Objectifs actuels:

```json
"personalized_targets": {
  "tempo_recup": {
    "drift_target": 6.6
  },
  "tempo_rapide": {
    "drift_target": 9.2
  },
  "endurance": {
    "drift_target": 8.4
  },
  "long_run": {
    "drift_target": 14.1
  }
}
```

### Interprétation:
- ✅ **Dérive < objectif**: Performance excellente
- 🎯 **Dérive ≈ objectif**: Performance visée
- 📈 **Dérive > objectif**: Marge de progression

---

## 🔄 CAS ROBUSTE (Option future)

Pour séances longues ou bruitées:

```
Division: 20% début / 20% fin (ignorer partie centrale)

Première portion: 20% du temps au début
Dernière portion: 20% du temps à la fin
```

**Avantages**:
- Meilleure stabilité statistique
- Évite les variations de la partie centrale
- Plus conforme à la définition physiologique

**Non implémenté actuellement** - CAS STANDARD suffit pour la majorité des runs.

---

## ⚠️ INTERDICTIONS

1. ❌ **Ne PAS découper par distance**
   - Exemple: Ne pas utiliser "premiers 5 km" vs "derniers 5 km"
   - Raison: Durée variable selon allure

2. ❌ **Ne PAS utiliser plus de 2 segments**
   - La dérive compare 2 états: début vs fin
   - Plus de segments dilue la mesure

3. ❌ **Ne PAS utiliser FC instantanée**
   - Toujours utiliser des moyennes temporelles
   - Évite le bruit et les variations ponctuelles

---

## 📝 SCRIPTS DE RECALCUL

### recalculate_cardiac_drift.py
Recalcule toutes les dérives dans activities.json avec la nouvelle méthode.

**Usage**:
```bash
.venv/bin/python3 recalculate_cardiac_drift.py
```

### update_drift_targets.py
Recalcule les objectifs (drift_target) dans profile.json basé sur P40.

**Usage**:
```bash
.venv/bin/python3 update_drift_targets.py
```

---

## 📚 RÉFÉRENCES PHYSIOLOGIQUES

**Cardiac drift**:
- Augmentation normale de 3-10% sur runs modérés
- Augmentation de 10-20% sur long runs ou conditions difficiles
- Valeurs > 20% indiquent fatigue importante ou déshydratation

**Facteurs influençant la dérive**:
- Température et humidité (↑ chaleur = ↑ dérive)
- Hydratation (↓ hydratation = ↑ dérive)
- Niveau d'entraînement (↑ entraîné = ↓ dérive)
- Durée de l'effort (↑ durée = ↑ dérive)

---

## 🔧 MAINTENANCE

### Recalcul périodique recommandé:
- Tous les 3 mois pour mettre à jour les objectifs
- Après changement significatif de forme (pic ou baisse)
- Après changement de conditions d'entraînement (altitude, climat)

### Validation:
1. Vérifier que les dérives sont cohérentes avec le ressenti
2. Comparer avec historique pour détecter anomalies
3. Ajuster objectifs si performances évoluent significativement

---

**Dernière mise à jour**: 20 décembre 2025
**Auteur**: Track2Train v2.0
**Contact**: support@track2train.com
