# Track2Train v2.8.0 - "Coach Hebdomadaire"

**Date:** 2025-12-21
**Milestone:** v2.8.0_20251221_200056

## Nouveautés principales

### 🏃 Système de coaching hebdomadaire
- Ajout checkbox "📅 Dernier run de la semaine" dans le formulaire de ressenti
- Analyse complète de tous les runs de la semaine quand la checkbox est cochée
- Génération automatique du bilan hebdomadaire par l'IA

### 📊 Bilan de semaine complet (mode coach)
Quand "Dernier run de la semaine" est coché, l'IA génère :
- **📈 Bilan Semaine** : analyse volume, qualité, variété, cohérence
- Statistiques : distance totale, dénivelé total, k moyen, dérive moyenne
- Détail de chaque run de la semaine
- Verdict global de la semaine

### 🗓️ Programme personnalisé semaine suivante
L'IA génère un programme 4 runs adapté aux résultats de la semaine :
- Run 1 (Lun/Mar) : Récupération 5-6km
- Run 2 (Mer/Jeu) : Tempo 5-6km
- Run 3 (Ven) : Tempo soutenu 10-11km
- Run 4 (Dim) : Long run 12-15km
- Chaque run avec allure cible, objectif et focus personnalisés

### 🎯 Améliorations analyse IA

#### Marge de progression renforcée
- Instructions pour 2-3 phrases détaillées avec chiffres précis
- Mode training : k à réduire, dérive à améliorer, zones FC à rééquilibrer
- Mode race : allure à améliorer, gestion effort, optimisation zones FC

#### Suppressions
- ❌ Section "Ressenti vs Réalité" (n'apportait pas de valeur)
- ❌ Ancien bloc "Bilan Semaine" statique (fond gris/bleu)
- ❌ Ancien bloc "Programme de la Semaine" statique (fond violet)

## Modifications techniques

### Fichiers modifiés

#### `/opt/app/Track2Train-staging/app.py`
- **Lignes 2407-2460** : Analyse complète des runs de la semaine
  - Calcul statistiques hebdomadaires (distance, dénivelé, k moyen, dérive moyenne)
  - Génération résumé détaillé de tous les runs
- **Ligne 2408** : Récupération `is_last_run_of_week` depuis feedback
- **Ligne 2498** : Augmentation max_tokens à 5000 (vs 3500)
- **Lignes 4179, 4209** : Sauvegarde checkbox dans feedback

#### `/opt/app/Track2Train-staging/templates/run_feedback.html`
- **Lignes 208-215** : Ajout checkbox "Dernier run de la semaine"
- **Lignes 184-211** : Styles CSS pour checkbox

#### `/opt/app/Track2Train-staging/prompts/session_analysis.txt`
- **Lignes 111-123** : Suppression section "Ressenti vs Réalité"
- **Lignes 122, 130** : Marge progression détaillée avec instructions chiffrées
- **Lignes 134-181** : Nouvelle section bilan semaine + programme (conditionnelle)
  - Utilise variable `{week_summary}` pour données de la semaine
  - Génère bilan complet et programme 4 runs personnalisés

#### `/opt/app/Track2Train-staging/templates/index.html`
- **Lignes 599-661** : Suppression ancien bloc "Bilan Semaine" statique
- **Lignes 600-697** : Suppression ancien bloc "Programme de la Semaine" statique

#### `/etc/systemd/system/track2train-staging.service`
- **Ligne 12** : Timeout augmenté de 120s → 180s (3 minutes)
  - Nécessaire pour génération bilan + programme complet

## Rollback

Pour revenir à la version 2.7.0 :

```bash
cd /opt/app/Track2Train-staging
BACKUP="/opt/app/Track2Train-staging/milestones/v2.8.0_20251221_200056"

# Restaurer les fichiers
cp "$BACKUP/app.py" .
cp -r "$BACKUP/templates/"* templates/
cp -r "$BACKUP/prompts/"* prompts/
echo "2.7.0" > VERSION
sudo cp "$BACKUP/track2train-staging.service" /etc/systemd/system/

# Redémarrer
sudo systemctl daemon-reload
sudo systemctl restart track2train-staging
```

## Notes techniques

### Performance
- Génération IA normale : ~30-60 secondes
- Génération avec bilan semaine : ~60-120 secondes
- Timeout configuré à 180 secondes pour sécurité

### Tokens Claude
- Analyse normale : ~3500 tokens
- Analyse avec bilan semaine : ~5000 tokens
- Coût légèrement augmenté pour les analyses de fin de semaine

### Logique de détection
- La checkbox doit être cochée manuellement par l'utilisateur
- Recommandation : cocher sur le long run du dimanche
- Variable `is_last_run_of_week` stockée dans `run_feedbacks.json`

## Impact utilisateur

### Workflow recommandé
1. **Runs normaux** : Remplir ressenti, générer IA → analyse classique
2. **Dimanche (dernier run)** :
   - Cocher "📅 Dernier run de la semaine"
   - Générer IA → bilan complet + programme suivant
   - Patienter 1-2 minutes pour génération enrichie

### Bénéfices
- Vision complète de la semaine écoulée
- Programme adapté aux résultats réels
- Coaching personnalisé semaine par semaine
- Progressivité intelligente basée sur les données

## Tests effectués
- ✅ Checkbox fonctionnelle dans formulaire ressenti
- ✅ Sauvegarde is_last_run_of_week dans JSON
- ✅ Calcul statistiques hebdomadaires
- ✅ Génération bilan + programme par IA
- ✅ Timeout 180s suffisant
- ✅ Anciens blocs statiques supprimés
- ✅ Pas de régression sur analyse normale

## Auteur
Claude Code (Anthropic) - Session 2025-12-21
