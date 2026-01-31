# 🚀 CHANGELOG VERSION 2.0.0

**Date** : 2025-11-09
**Déployé sur** : Staging

---

## 🎯 NOUVEAUTÉS MAJEURES

### 🤖 Système de Coaching IA avec Claude Sonnet 4

#### 1. Profil Utilisateur Étendu
- ✅ Section **Objectifs** : objectif principal, date cible, événement, style de course, tolérance intensité
- ✅ Section **Préférences** : allures confort (min/max), plaisir de transpirer
- ✅ Section **Contraintes santé** : surveillance cardiaque, genoux, chevilles

**Fichiers** :
- `profile.json` (structure enrichie)
- `templates/profile.html` (formulaire complet avec radio, sliders, checkboxes)

#### 2. Feedback Post-Run Interactif
- ✅ Formulaire de ressenti complet :
  - ⭐ Note globale (5 étoiles cliquables)
  - 😓 Difficulté (5 boutons avec emojis)
  - 🦵 État des jambes (4 options)
  - ❤️ Ressenti cardio (4 options)
  - 😊 Plaisir (slider 1-5)
  - 📝 Notes libres (textarea 200 caractères)
- ✅ Sauvegarde dans `outputs/run_feedbacks.json`

**Fichiers** :
- `templates/run_feedback.html`
- Route `/run_feedback/<activity_id>` (GET + POST)

#### 3. Génération Commentaires IA
- ✅ Intégration Claude Sonnet 4 (Anthropic)
- ✅ Prompt personnalisé avec :
  - Profil complet de l'utilisateur
  - Données objectives du run (distance, allure, FC, dérive)
  - Ressenti subjectif de l'utilisateur
- ✅ Commentaires 50-100 mots : validation + point positif + conseil actionnable
- ✅ Ton coach personnel bienveillant

**Fonctions** :
- `generate_ai_coaching()` - Fonction générique API Anthropic
- `generate_run_comment()` - Génération commentaire post-run
- `load_run_feedbacks()`, `save_run_feedback()`, `get_feedback_for_activity()`

#### 4. Affichage Dashboard
- ✅ Bloc **"💬 Analyse du coach"** dans chaque slide du carrousel
- ✅ Affichage du commentaire IA si feedback existe
- ✅ Bouton "📝 Donner mon ressenti" si pas de feedback
- ✅ Bouton "✏️ Modifier mon ressenti" pour éditer

**CSS** : Bloc coach avec bordure orange, fond gris clair, responsive

---

## 📊 DIFFÉRENCES v1.3.1 → v2.0.0

### Nouveaux fichiers
- `profile.json` - Profil utilisateur enrichi
- `outputs/run_feedbacks.json` - Feedbacks + commentaires IA
- `templates/run_feedback.html` - Page feedback post-run
- `.env` - Clé API Anthropic
- `CHANGELOG_V2.0.md` - Ce fichier

### Fichiers modifiés
- `app.py` :
  - Import Anthropic SDK
  - Fonction `generate_ai_coaching()`
  - Fonctions helpers feedbacks
  - Fonction `generate_run_comment()`
  - Route `/run_feedback/<activity_id>` (GET + POST)
  - Route `/profile` (POST enrichi)
  - Route `/` (chargement et matching feedbacks)
- `templates/profile.html` :
  - Section "🎯 Mes Objectifs" complète
  - Radio buttons, sliders, checkboxes
- `templates/index.html` :
  - Bloc "💬 Analyse du coach" dans carrousel
  - CSS pour affichage commentaires IA

### Dépendances ajoutées
- `anthropic==0.72.0` (SDK Claude)

---

## 💰 COÛTS

**Claude Sonnet 4** :
- Coût par commentaire : ~$0.0007 (200 tokens)
- **15 runs/mois** : ~$0.01/mois (1 centime)

---

## 🧪 TESTS VALIDÉS

✅ Test création feedback complet (`test_feedback.py`)
✅ Test génération IA avec Claude Sonnet 4
✅ Test sauvegarde dans `run_feedbacks.json`
✅ Test chargement et matching `activity_id` ↔ feedback
✅ Test affichage dans dashboard HTML
✅ Test boutons "Donner/Modifier ressenti"

**Exemple testé** : Run du 2025-11-09, 10.04 km, allure 5:17/km, dérive 2.37
- ✅ Commentaire généré : "Excellent run Emmanuel ! 💪 Tu as maintenu..."
- ✅ Affiché dans dashboard avec bouton "Modifier"

---

## 🔄 ROLLBACK (si nécessaire)

En cas de problème, retour à la v1.3.1 :

```bash
# Restaurer backup v1.3.1
cp -r /opt/app/Track2Train-v1.3.1-backup/* /opt/app/Track2Train-staging/

# Ou désactiver juste l'IA
rm .env  # Retire la clé Anthropic
# L'app fonctionnera sans coaching IA
```

---

## 📋 PROCHAINES ÉTAPES - PHASE 2

### Analyse par Tronçons + Patterns
- Calcul métriques par segments (2/3/4 tronçons selon distance)
- Détection patterns : départ trop rapide, baisse fin course, dérive excessive
- Commentaire IA enrichi avec analyse tronçons
- Affichage segments dans accordéon dashboard

### Objectifs par Tronçons
- Génération objectifs précis pour prochain run
- Conseils par segment : allure cible, FC cible
- Page dédiée `/next_run_objectives`

### Plan d'Entraînement Complet
- Génération plan 12-20 semaines
- Personnalisé selon profil + historique
- Prédictions temps de course
- Page `/training_plan`

---

**Version** : 2.0.0
**Date de release** : 2025-11-09
**Statut** : ✅ Staging validé
**Production** : À déployer
