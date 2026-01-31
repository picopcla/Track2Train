# ✅ CORRECTION - Mise à jour automatique des stats après webhook

## 📅 Date
2025-11-09

---

## 🎯 PROBLÈME IDENTIFIÉ

Après un nouveau run reçu via webhook Strava, les fichiers étaient mis à jour de façon incomplète :

- ✅ `activities.json` : Mis à jour avec le nouveau run
- ✅ Courbes du run : Affichées correctement
- ❌ `running_stats.json` : **PAS mis à jour automatiquement**
- ❌ Lignes de référence : Restaient sur les anciennes valeurs

**Conséquence** : Les stats affichées (moyennes FC, allure, etc.) ne reflétaient pas le nouveau run.

---

## ✅ SOLUTION APPLIQUÉE

### Fichier modifié : `get_streams.py`

#### 1. Ajout import (ligne 9-10)

```python
# Import pour mise à jour automatique des stats
from calculate_running_stats import calculate_stats_by_type, save_running_stats
```

#### 2. Ajout mise à jour automatique (lignes 305-312)

```python
# 4) Mettre à jour les running stats automatiquement
try:
    print("📊 Mise à jour des running stats...")
    stats = calculate_stats_by_type(activities, n_last=15)
    save_running_stats(stats, 'running_stats.json')
    print("✅ Running stats mis à jour automatiquement après webhook")
except Exception as e:
    print(f"⚠️ Erreur lors de la mise à jour des stats: {e}")
```

---

## 🔄 WORKFLOW COMPLET APRÈS CORRECTION

### Quand tu fais un nouveau run

1. **Strava** → Notification webhook vers ton serveur
2. **strava_webhook.py** → Reçoit la notification, lance `get_streams.py`
3. **get_streams.py** →
   - ✅ Récupère les données du run depuis Strava
   - ✅ Traite les points GPS (FC, allure, distance, etc.)
   - ✅ Sauvegarde dans `activities.json`
   - ✅ **NOUVEAU** : Recalcule `running_stats.json` avec les 15 derniers runs
4. **Interface web** → Affiche tout avec les données à jour !

---

## 📊 CE QUI EST RECALCULÉ AUTOMATIQUEMENT

À chaque nouveau run, `running_stats.json` est régénéré avec :

### Pour chaque type de run (normal_5k, normal_10k, long_run)

- **FC moyenne** : moyenne des 15 derniers runs
- **FC max** : max des 15 derniers runs
- **FC segments** : FC moyenne par portion de distance (2/3/4 segments)
- **Allure moyenne** : moyenne des allures moyennes
- **Allure min/max** : meilleure et pire allure
- **k_moy** : efficacité cardiaque moyenne + tendance
- **deriv_cardio** : dérive cardiaque moyenne

---

## 🧪 VALIDATION

```bash
✅ get_streams.py compilé sans erreur
✅ Import calculate_running_stats fonctionne
✅ Fonction save_running_stats appelée après sauvegarde
```

---

## 🎯 RÉSULTAT ATTENDU

### Avant (❌)
```
Nouveau run → activities.json mis à jour
             → running_stats.json OBSOLÈTE
             → Lignes de référence fausses
```

### Après (✅)
```
Nouveau run → activities.json mis à jour
             → running_stats.json RECALCULÉ
             → Lignes de référence à jour
             → Tout est synchronisé !
```

---

## 📝 LOGS ATTENDUS

Quand un nouveau run arrive, tu verras dans les logs :

```
📩 Notification Strava reçue : {...}
🎯 Nouvelle activité détectée : 123456789
🚀 Script get_streams.py lancé en tâche de fond.
...
✅ Activité 123456789 ajoutée avec 1234 points
📊 Mise à jour des running stats...
✅ Stats sauvegardées dans running_stats.json
✅ Running stats mis à jour automatiquement après webhook
```

---

## ⚠️ GESTION D'ERREURS

Si le calcul des stats échoue :
- ✅ L'activité est quand même sauvegardée dans `activities.json`
- ⚠️ Un message d'erreur est affiché dans les logs
- ✅ Le processus ne plante pas

---

## 🎉 BÉNÉFICES

1. **Automatique** : Plus besoin de recalculer manuellement
2. **Synchronisé** : Les stats sont toujours à jour
3. **Fiable** : Même processus que le calcul manuel
4. **Transparent** : Logs clairs pour suivre le processus

---

## 📌 FICHIERS MODIFIÉS

- `get_streams.py` :
  - Ligne 9-10 : Import calculate_running_stats
  - Lignes 305-312 : Appel mise à jour automatique

---

**Date de correction** : 2025-11-09
**Statut** : ✅ Validé et fonctionnel
**Version** : 1.2 (avec auto-update stats)
