# 📋 PLAN PHASE 3 - Programme Hebdomadaire + Analyse Avancée

**Date:** 2025-11-09
**Version cible:** 2.2.0

---

## 🎯 OBJECTIFS PHASE 3

### 1. Programme Hebdomadaire (3 Runs)
- Génération automatique de 3 runs pour la semaine à venir
- Types de séances adaptés au profil et objectif
- Objectifs par run (distance, allure cible, FC cible)

### 2. Analyse Comparative par Segment
**NOUVEAU:** Au lieu d'analyser globalement, analyser **chaque segment individuellement** :
- Segment 1 actuel vs Segment 1 des 15 derniers runs du même type
- Segment 2 actuel vs Segment 2 des 15 derniers runs du même type
- Segment 3 actuel vs Segment 3 des 15 derniers runs du même type

**Métriques comparées par segment:**
- Allure moyenne (est-ce que T1 est plus rapide/lent que d'habitude ?)
- FC moyenne (est-ce que T2 demande plus/moins d'effort cardiaque ?)
- Dérive intra-segment (est-ce que T3 a une meilleure/pire efficacité ?)

### 3. Prédictions de Temps de Course
- Pour chaque run programmé : prédiction du temps estimé
- Basé sur : profil, historique, type de séance, conditions

### 4. Comparaison Prédiction vs Réalité
- Après le run : afficher prédiction vs temps réel
- Analyse de l'écart
- Ajustement des prédictions futures

### 5. Analyse IA Santé Cardiaque
- Monitoring FC au cours de la séance
- Détection d'anomalies (FC trop haute trop tôt, récupération lente)
- Analyse des patterns cardiaques vs historique
- Conseils santé (repos, vigilance, médecin)

### 6. Progression des Séances
- Visualisation de l'évolution semaine par semaine
- Comparaison des runs similaires dans le temps
- Tendances (amélioration/stagnation/régression)

---

## 📦 COMPOSANTS À DÉVELOPPER

### Backend Python

#### 1. `generate_weekly_program(profile, activities, current_week)`
**Rôle:** Générer 3 runs pour la semaine
**Input:** Profil utilisateur, historique activités, semaine actuelle
**Output:**
```python
{
  "week_number": 45,
  "start_date": "2025-11-11",
  "end_date": "2025-11-17",
  "runs": [
    {
      "day": "Mardi",
      "type": "sortie longue",
      "distance_km": 12,
      "pace_target": "5:25/km",
      "fc_target": "145-155 bpm",
      "predicted_time": "01:05:00",
      "notes": "Allure confort, construire l'endurance"
    },
    {
      "day": "Jeudi",
      "type": "tempo",
      "distance_km": 8,
      "pace_target": "5:05/km",
      "fc_target": "155-165 bpm",
      "predicted_time": "00:40:40",
      "notes": "Effort soutenu mais contrôlé"
    },
    {
      "day": "Dimanche",
      "type": "récupération",
      "distance_km": 6,
      "pace_target": "5:45/km",
      "fc_target": "135-145 bpm",
      "predicted_time": "00:34:30",
      "notes": "Relâchement total, endurance de base"
    }
  ]
}
```

#### 2. `compare_segment_with_history(segment_number, current_segment, activities, type_sortie)`
**Rôle:** Comparer un segment avec l'historique
**Input:** Numéro segment, segment actuel, historique, type de sortie
**Output:**
```python
{
  "segment_number": 1,
  "current": {
    "pace": 5.27,
    "fc_avg": 138,
    "drift": 2.11
  },
  "historical_avg": {
    "pace": 5.35,  # Moyenne des T1 des 15 derniers runs
    "fc_avg": 145,
    "drift": 1.85
  },
  "comparison": {
    "pace_diff": -0.08,  # Plus rapide de 5 sec/km
    "pace_trend": "faster",
    "fc_diff": -7,  # FC plus basse de 7 bpm
    "fc_trend": "better",
    "drift_diff": +0.26,  # Dérive plus élevée
    "drift_trend": "worse"
  },
  "percentile": 35,  # Ce T1 est dans le 35e percentile (plutôt bon)
  "count": 15  # Nombre de runs comparés
}
```

#### 3. `predict_race_time(profile, distance_km, run_type, recent_activities)`
**Rôle:** Prédire le temps de course
**Input:** Profil, distance, type, historique récent
**Output:**
```python
{
  "predicted_time_sec": 3900,
  "predicted_time_str": "01:05:00",
  "confidence": 0.85,
  "factors": {
    "recent_pace_avg": 5.30,
    "recent_fc_efficiency": 0.92,
    "fatigue_score": 0.15,
    "weather_factor": 1.02
  }
}
```

#### 4. `analyze_cardiac_health(activity, segments, profile, history)`
**Rôle:** Analyser la santé cardiaque pendant la séance
**Input:** Activité, segments, profil, historique
**Output:**
```python
{
  "overall_status": "good",  # good/warning/alert
  "alerts": [],
  "observations": [
    "FC démarre normalement (71 bpm)",
    "Montée rapide au T1 (+78 bpm en 3km) - surveiller échauffement",
    "FC stable au T2 et T3 - bonne adaptation",
    "Dérive T1 élevée (2.11) - possible fatigue résiduelle"
  ],
  "recommendations": [
    "Échauffement progressif de 10 min avant démarrage",
    "Surveiller la récupération post-run (FC retour < 100 bpm en 5 min)"
  ],
  "heart_rate_zones": {
    "zone1_time_pct": 15,  # % temps en zone 1
    "zone2_time_pct": 60,
    "zone3_time_pct": 25,
    "zone4_time_pct": 0,
    "zone5_time_pct": 0
  },
  "recovery_indicator": "good"  # good/moderate/poor
}
```

#### 5. `compare_prediction_vs_actual(predicted, actual_activity)`
**Rôle:** Comparer prédiction vs réalité
**Input:** Prédiction, activité réelle
**Output:**
```python
{
  "predicted_time": "01:05:00",
  "actual_time": "01:03:17",
  "diff_sec": -103,  # 1min43s plus rapide
  "diff_pct": -2.6,
  "accuracy": "excellent",  # excellent/good/poor
  "factors_analysis": {
    "pace_faster_than_expected": True,
    "fc_lower_than_expected": True,
    "conditions_better": False
  },
  "ai_comment": "Excellente surprise ! Tu as couru 1min43s plus rapide que prévu..."
}
```

#### 6. `analyze_progression(activities, weeks=4)`
**Rôle:** Analyser la progression sur X semaines
**Input:** Activités, nombre de semaines
**Output:**
```python
{
  "period": "4 weeks",
  "runs_completed": 12,
  "by_type": {
    "sortie longue": {
      "count": 4,
      "avg_pace_trend": -0.05,  # 3 sec/km plus rapide
      "avg_fc_trend": -3,  # 3 bpm de moins
      "trend": "improving"
    },
    "tempo": {
      "count": 4,
      "avg_pace_trend": -0.08,
      "avg_fc_trend": -5,
      "trend": "improving"
    }
  },
  "overall_trend": "improving",
  "fitness_score": 7.5,  # /10
  "fitness_change": +0.8
}
```

### Frontend

#### 1. Page `/weekly_program`
- Affichage des 3 runs programmés
- Cartes par run avec objectifs
- Prédictions de temps
- Bouton "Marquer comme fait" après le run

#### 2. Section "Analyse Comparative" dans Dashboard
- Accordéon par segment avec comparaison historique
- Graphiques sparkline : ton segment vs moyenne historique
- Indicateurs visuels (↗↘→) pour les tendances

#### 3. Section "Santé Cardiaque" dans Run
- Zone cardio par segment
- Alertes/recommandations IA
- Temps passé par zone FC

#### 4. Page `/progression`
- Graphiques évolution sur 4-12 semaines
- Comparaison par type de séance
- Score de fitness

---

## 📐 ARCHITECTURE

### Nouvelles Collections JSON

**`weekly_programs.json`:**
```json
{
  "2025-W45": {
    "week_number": 45,
    "generated_date": "2025-11-09",
    "runs": [...],
    "completion": [
      {"run_index": 0, "completed": true, "activity_id": "123"},
      {"run_index": 1, "completed": false},
      {"run_index": 2, "completed": false}
    ]
  }
}
```

**`predictions.json`:**
```json
{
  "16403009248": {
    "predicted_time": 3900,
    "actual_time": 3797,
    "diff_sec": -103,
    "accuracy": "excellent"
  }
}
```

**`cardiac_analyses.json`:**
```json
{
  "16403009248": {
    "status": "good",
    "alerts": [],
    "observations": [...],
    "zones": {...}
  }
}
```

### Nouvelles Routes Flask

- `GET /weekly_program` - Affiche le programme de la semaine
- `POST /weekly_program/generate` - Génère un nouveau programme
- `POST /weekly_program/complete` - Marque un run comme fait
- `GET /progression` - Page progression
- `GET /cardiac_analysis/<activity_id>` - Analyse cardiaque d'un run

---

## 🔄 WORKFLOW UTILISATEUR

### Lundi matin : Génération du programme
1. User clique "Générer mon programme de la semaine"
2. IA génère 3 runs adaptés (Mardi, Jeudi, Dimanche)
3. Affichage avec prédictions de temps

### Mardi soir : Après le run
1. Run sync depuis Strava
2. Calcul segments automatique
3. **NOUVEAU:** Comparaison segment par segment vs historique
4. **NOUVEAU:** Analyse santé cardiaque
5. **NOUVEAU:** Comparaison prédiction vs réalité
6. Génération commentaire IA enrichi avec tout ça
7. User donne son ressenti
8. Programme mis à jour (run 1 marqué fait)

### Dimanche soir : Fin de semaine
1. 3 runs complétés
2. Page `/progression` affiche l'évolution
3. Bouton "Générer le programme de la semaine prochaine"

---

## 🧪 ORDRE D'IMPLÉMENTATION

### Sprint 1 : Comparaison Segments vs Historique
1. ✅ Fonction `get_segment_history(segment_num, type_sortie, activities)`
2. ✅ Fonction `compare_segment_with_history()`
3. ✅ Intégrer dans feedback route
4. ✅ Afficher dans dashboard (accordéon segments)

### Sprint 2 : Analyse Santé Cardiaque
1. ✅ Fonction `calculate_hr_zones(points, fc_max)`
2. ✅ Fonction `analyze_cardiac_health()`
3. ✅ Section dans dashboard
4. ✅ Alertes IA

### Sprint 3 : Programme Hebdomadaire
1. ✅ Fonction `generate_weekly_program()`
2. ✅ Page `/weekly_program`
3. ✅ Système de completion

### Sprint 4 : Prédictions & Comparaisons
1. ✅ Fonction `predict_race_time()`
2. ✅ Fonction `compare_prediction_vs_actual()`
3. ✅ Affichage dans run feedback

### Sprint 5 : Progression
1. ✅ Fonction `analyze_progression()`
2. ✅ Page `/progression`
3. ✅ Graphiques évolution

---

## 📊 PRIORISATION

**SPRINT 1 (PRIORITAIRE):** Comparaison segments vs historique
- C'est ce que tu veux en priorité
- Base pour les autres features
- Impact immédiat sur l'analyse

**SPRINT 2:** Analyse santé cardiaque
- Important pour le monitoring
- Complémentaire à l'analyse segments

**SPRINT 3:** Programme hebdomadaire
- Structure les runs de la semaine
- Nécessaire pour les prédictions

**SPRINT 4:** Prédictions
- Nécessite le programme (Sprint 3)
- Cool mais secondaire

**SPRINT 5:** Progression
- Nice to have
- Peut attendre

---

## 🎯 ON COMMENCE PAR QUOI ?

**Je propose de démarrer par le SPRINT 1:**
1. Créer `compare_segment_with_history()`
2. L'intégrer dans la route feedback
3. Afficher dans le dashboard pour chaque segment

**Exemple d'affichage:**
```
📍 Tronçon 1 (0.0-3.3 km)
   Allure: 5:16/km (↗ 5 sec/km plus rapide que tes 15 derniers T1)
   FC moy: 138 bpm (↘ 7 bpm de moins que d'habitude - excellent !)
   Dérive: 2.11 (↗ +0.26 vs moyenne - surveiller)
   📊 Percentile: 35e/100 (meilleur que 65% de tes T1)
```

**Tu valides cette approche ?**
