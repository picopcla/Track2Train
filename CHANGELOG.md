# 📋 Changelog Track2Train

## [2.16.0] - 2026-02-01

### 🎯 Unification Stats & Objectifs + Correction IA

#### Nouveau
**Dashboard Unifié (Stats):**
- Fusion des pages `/objectifs` et `/stats` en une seule vue cohérente.
- **Pilotage Direct:** Cartes d'objectifs (K et Drift) intégrées en haut de la page stats.
- **Suggestions Dynamiques:** Affichage des suggestions P30 (K) et P40 (Drift) basées sur l'historique récent.
- **Action Immédiate:** Boutons pour sauvegarder les cibles ou lancer un recalcul automatique par l'IA sans changer de page.

**Amélioration Coaching IA:**
- **Prompt Contextuel:** L'IA reçoit désormais *explicitement* les objectifs généraux du profil (K/Drift) pour chaque analyse.
- **Correction:** Fallback automatique sur les objectifs du profil si aucun run n'est planifié spécifiquement (évite les analyses "aveugles").
- **Cohérence:** Les feedbacks IA, les graphiques et le bilan hebdo utilisent tous la même source de vérité pour les cibles.

#### Supprimé
- **Page Legacy:** Suppression complète de l'ancienne page `objectifs.html` et de sa route `/objectifs`.
- **Navigation:** Retrait du bouton "Objectifs" de l'index (désormais redondant).

#### Impact
- Expérience utilisateur simplifiée (tout au même endroit).
- Cohérence totale entre les chiffres affichés et l'analyse du coach.
- Codebase plus propre (moins de duplication).

---


## [2.13.0] - 2026-01-14

### 🎯 Système de Score Hebdomadaire & Objectifs Évolutifs

#### Nouveau
**Système de notation /10:**
- `calculate_weekly_score()` - Calcule note hebdomadaire basée sur 5 facteurs
  - Volume (20%), Adhésion (20%), Respect types (20%), Qualité technique (30%), Régularité (10%)
- Note globale, détails par critère, points forts, axes d'amélioration
- Historique sauvegardé dans `outputs/weekly_scores.json` (12 dernières semaines)

**Objectifs enrichis dans le plan hebdomadaire:**
- Parsing automatique objectif global ("Semi marathon wn 1h45")
- Calcul allure cible, meilleure performance récente, gap en secondes
- Focus semaine intégré dans le programme
- Structure `summary.objective` avec toutes les métriques

**Recalibrage automatique des objectifs:**
- `check_and_recalibrate_objectives()` - Ajuste k_target et drift_target automatiquement
- Déclencheur 1: Objectifs atteints (2+ types) → Resserrer -5%
- Déclencheur 2: Stagnation (4 sem < 7/10) → Relâcher +3%
- Notification dans le bilan si recalibrage effectué

#### Modifié
- `analyze_past_week()` - Inclut maintenant score, strengths, improvements
- `generate_past_week_comment()` - Prompt enrichi avec note et analyse détaillée
- `generate_weekly_program()` - Enrichi avec objectifs et focus semaine
- `prompts/past_week_analysis.txt` - Nouveau format avec score et conseils coaching
- Route index - Sauvegarde score + déclenche recalibrage après génération bilan

#### Fichiers créés
- `outputs/weekly_scores.json` - Historique des notes hebdomadaires
- `/tmp/html_enrichment_snippets.md` - Documentation snippets HTML

#### Données disponibles (JSON)
```json
// past_week_analysis.json
{
  "score": 7.5,
  "score_details": {"volume": 8.9, "adherence": 7.5, ...},
  "strengths": ["Volume excellent", ...],
  "improvements": ["Qualité technique à améliorer", ...],
  "recalibration": {...}  // Si recalibrage effectué
}

// weekly_plan.json
{
  "summary": {
    "objective": {
      "target_time": "1:45:00",
      "target_pace": "4:58",
      "current_best_pace": "5:08",
      "pace_gap_seconds": 10
    },
    "focus": "Maintenir qualité et volume"
  }
}
```

#### Impact
- Note hebdomadaire permet suivi progression dans le temps
- Objectifs deviennent évolutifs (s'adaptent aux performances)
- Commentaires IA plus riches avec analyse détaillée
- Recalibrage auto évite stagnation et ajuste challenge

**Code:** +280 lignes (3 nouvelles fonctions)
**Tests:** ✅ Syntax OK, Service redémarré, Dashboard 200 OK

---

## [2.12.0] - 2026-01-14

### 🧹 Nettoyage Majeur - Code Mort & Fichiers Obsolètes

#### Supprimé
**Fichiers Python:**
- `sync_strava.py` (111 lignes) - Fichier cassé avec fonctions non définies

**Fonctions mortes:**
- `calculate_running_stats.py`: `format_allure()`, `display_stats()` (41 lignes)
- `data_access_local.py`: `restore_activities_from_drive()` (12 lignes)

**Imports inutiles:**
- `app.py`: `backup_activities_to_drive` (jamais appelé)
- `get_streams.py`: `import io` (jamais utilisé)

**Fichiers config obsolètes:**
- `.version_info` - Jamais référencé
- `Procfile` - Déploiement cloud (systemd utilisé)
- `prompts/README.md` - Documentation obsolète

**Scripts dev:**
- `start_and_test.sh` - Obsolète avec systemd
- `setup_webhook.sh` - Webhook déjà configuré

**PWA non implémentée:**
- `static/service-worker.js`
- `static/manifest.json`

**Templates & prompts:**
- 9 fichiers obsolètes (program_guide.html, drift_evolution.txt, etc.)

**Données:**
- `outputs/profile.json` (doublon)
- `client_secrets.json` (OAuth obsolète)

#### Corrigé
- Bug: `detect_session_type` → `classify_run_type` (3 occurrences)
- Bug: `datetime.datetime.now()` → `datetime.now()` (7 occurrences après nettoyage imports)
- 13 bare `except:` remplacés par exceptions spécifiques
- 8+ imports datetime redondants supprimés

#### Optimisé
- Cache profil (60s TTL) - Réduit appels load_profile()
- Classification conditionnelle - Évite reclassifications inutiles
- Route `generate_ai_comment` optimisée - Trouve activité avant enrichissement

#### Résumé
- **19 fichiers supprimés**
- **166 lignes de code mort supprimées**
- **2 bugs corrigés**
- **3 optimisations de performance**
- **0 régression** (tous tests passent)

**Fichiers avant:** 47 | **Fichiers après:** 28 | **Gain:** 19 fichiers
**Lignes avant:** 4930 | **Lignes après:** 4728 | **Gain:** 202 lignes

---

## [2.11.0] - 2025-XX-XX
*(Version précédente)*
