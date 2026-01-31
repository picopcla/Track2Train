# Track2Train v2.6.0 - Release Notes

**Date:** 2025-11-11
**Version précédente:** 2.5.1

---

## 🎯 Nouvelles Fonctionnalités Majeures

### 1. 📝 Interface Web de Gestion du Ressenti

**Nouvelle interface complète pour ajouter/modifier le ressenti de chaque séance**

#### Routes ajoutées :
- `GET /feedback/<activity_date>` - Formulaire de saisie du ressenti
- `POST /feedback/<activity_date>` - Sauvegarde du ressenti

#### Fonctionnalités :
- **Formulaire élégant** avec design moderne (gradient violet)
- **5 catégories de ressenti** :
  - ⭐ Note globale (1-5)
  - 💪 Difficulté ressentie (1-5)
  - 🦵 Ressenti jambes (Fraîches/Normales/Lourdes/Très lourdes)
  - ❤️ Ressenti cardio (Facile/Modéré/Difficile/Très difficile)
  - 😊 Plaisir pris (1-5)
- **Zone de notes personnelles** libre
- **Préremplissage automatique** des valeurs existantes
- **Sauvegarde persistante** dans `outputs/run_feedbacks.json`
- **Redirection automatique** vers la page d'accueil après sauvegarde

#### Intégration dans le carrousel :
- Bouton **"✏️ Modifier le ressenti"** si un ressenti existe
- Bouton **"📝 Ajouter un ressenti"** si aucun ressenti
- Style cohérent avec gradient orange/doré
- Positionné entre l'affichage du ressenti et le bouton IA

#### Fichiers créés/modifiés :
- `app.py:2577-2672` - Nouvelles routes feedback
- `app.py:661-669` - Fonction `load_feedbacks()`
- `templates/run_feedback.html` - Template du formulaire (282 lignes)
- `templates/index.html:425-431` - Bouton d'accès au formulaire

---

### 2. 🏃 Amélioration du Programme Hebdomadaire

**Programme de la semaine enrichi avec allures et FC cibles**

#### Modifications affichage :
- ✅ **Allures cibles** ajoutées : Ex. "5:40/km"
- ✅ **FC cibles** ajoutées : Ex. "130-140 bpm"
- ✅ **Jours supprimés** : Remplacés par "Run 1", "Run 2", "Run 3"
- ✅ **Liberté d'exécution** : Les runs peuvent être faits dans n'importe quel ordre

#### Structure données :
```python
{
    'runs': [
        {
            'day': 'Mardi',  # Pas affiché
            'type_display': 'Sortie Longue',
            'distance_km': 12,
            'pace_target': '5:40/km',
            'fc_target': '130-140 bpm',
            'predicted_time': '01:08:00',
            'notes': 'Allure confort...'
        },
        # Run 2, Run 3...
    ]
}
```

#### Fichiers modifiés :
- `templates/index.html:438-455` - Section programme hebdomadaire
- `templates/index.html:441` - "Run {{ loop.index }}" au lieu du jour
- `templates/index.html:448-449` - Ajout allure et FC cibles

---

### 3. 📊 Affichage du Ressenti dans le Carrousel

**Chaque activité affiche maintenant son ressenti si disponible**

#### Affichage :
- Encadré jaune/or avec bordure
- **4 métriques principales** en grille 2x2 :
  - Difficulté : X/5
  - Note globale : X/5 ⭐
  - Jambes : [état]
  - Cardio : [état]
- **Notes personnelles** affichées en italique sous les métriques
- Uniquement visible si un ressenti existe

#### Intégration données :
- Chargement des feedbacks : `app.py:2018`
- Fusion avec activités : `app.py:2185-2187`
- Ajout au dict carrousel : `app.py:2223`
- Affichage template : `templates/index.html:407-423`

---

## 🔧 Améliorations Techniques

### Gestion des Feedbacks

**Nouvelle fonction de chargement des feedbacks** :
```python
def load_feedbacks():
    """Charge les feedbacks depuis outputs/run_feedbacks.json"""
    feedbacks = read_output_json('run_feedbacks.json') or {}
    return feedbacks
```

**Stockage** : `/opt/app/Track2Train-staging/outputs/run_feedbacks.json`

**Format** :
```json
{
  "16403009248": {
    "activity_id": "16403009248",
    "date": "2025-11-09T11:28:42Z",
    "rating_stars": 4,
    "difficulty": 4,
    "legs_feeling": "normal",
    "cardio_feeling": "moderate",
    "enjoyment": 4,
    "notes": "Bon run, léger vent de face",
    "timestamp": "2025-11-11T08:44:26.297253"
  }
}
```

---

## 📝 Fichiers Modifiés/Créés

### Fichiers créés :
1. `templates/run_feedback.html` (282 lignes) - Formulaire de saisie du ressenti
2. `RELEASE_NOTES_2.6.0.md` - Ce fichier

### Fichiers modifiés :

#### `app.py`
- Lignes 661-669 : Fonction `load_feedbacks()`
- Lignes 2018 : Chargement des feedbacks au démarrage
- Lignes 2185-2187 : Fusion feedbacks avec activités
- Lignes 2223 : Ajout feedback au dict carrousel
- Lignes 2577-2672 : Routes `/feedback/<activity_date>` (GET et POST)

#### `templates/index.html`
- Lignes 407-423 : Section affichage ressenti dans carrousel
- Lignes 425-431 : Bouton "Modifier/Ajouter ressenti"
- Lignes 441 : "Run {{ loop.index }}" au lieu du jour
- Lignes 448-449 : Affichage allure et FC cibles

#### `VERSION`
- `2.5.1` → `2.6.0`

---

## ✅ Tests Effectués

### Test 1 : Affichage du formulaire
```bash
curl http://127.0.0.1:5002/feedback/2025-11-09T11:28:42Z
# ✅ Formulaire chargé avec données existantes pré-remplies
```

### Test 2 : Sauvegarde du ressenti
```bash
curl -X POST http://127.0.0.1:5002/feedback/2025-11-09T11:28:42Z \
  -d "rating_stars=4" \
  -d "difficulty=4" \
  -d "legs_feeling=normal" \
  -d "cardio_feeling=moderate" \
  -d "enjoyment=4" \
  -d "notes=Test modification"
# ✅ Sauvegarde réussie, redirection vers /
```

### Test 3 : Affichage sur la page principale
```bash
curl http://127.0.0.1:5002/ | grep "Difficulté"
# ✅ Affichage : "Difficulté: 4/5"
```

### Test 4 : Programme hebdomadaire
```bash
curl http://127.0.0.1:5002/ | grep "Run 1"
# ✅ Affichage : "Run 1 - Sortie Longue"
# ✅ Affichage : "Allure cible: 5:40/km"
# ✅ Affichage : "FC cible: 130-140 bpm"
```

---

## 🎯 Workflow Utilisateur

### Ajout/Modification du ressenti :

1. **Ouvrir le carrousel** sur une activité
2. **Cliquer** sur "✏️ Modifier le ressenti" ou "📝 Ajouter un ressenti"
3. **Remplir** le formulaire :
   - Sélectionner notes (1-5) pour globale, difficulté, plaisir
   - Choisir état jambes (menu déroulant)
   - Choisir ressenti cardio (menu déroulant)
   - Ajouter notes texte (optionnel)
4. **Sauvegarder** (bouton "💾 Sauvegarder")
5. **Retour automatique** à la page d'accueil avec ressenti mis à jour

---

## 📊 Impact Performance

- **Chargement des feedbacks** : +10ms au démarrage de la page
- **Affichage carrousel** : Aucun impact (données déjà chargées)
- **Formulaire feedback** : Page indépendante, pas d'impact sur index

---

## 🔮 Améliorations Futures

1. **Génération IA enrichie** : Utiliser le ressenti pour affiner les commentaires IA
2. **Statistiques ressentis** : Dashboard avec évolution du ressenti sur 4-8 semaines
3. **Alertes fatigue** : Détection automatique si ressenti dégradé sur plusieurs runs
4. **Export PDF** : Exporter l'historique des ressentis
5. **Import depuis Strava** : Récupération automatique des notes Strava

---

## 🐛 Bugs Connus

Aucun bug connu dans cette version.

---

## 📚 Documentation Associée

- `INTEGRATION_FRONTEND.md` - Guide d'intégration frontend
- `AI_ON_DEMAND.md` - Documentation API commentaires IA
- `EXTERNAL_PROMPTS_COMPLETE.md` - Système de prompts externes

---

**🎉 Version 2.6.0 - Gestion complète du ressenti et programme enrichi !**
