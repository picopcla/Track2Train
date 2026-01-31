# 🤖 Prompts IA Track2Train

Ce dossier contient tous les prompts utilisés par l'application pour générer les commentaires de coaching avec Claude Sonnet 4.

## 📁 Structure

```
prompts/
├── README.md                    # Ce fichier
├── segment_analysis.txt         # Prompt principal de coaching (utilisé par generate_segment_analysis)
└── (futurs prompts...)
```

## 📝 Comment Modifier les Prompts

### 1. Modifier le prompt principal (`segment_analysis.txt`)

**Variables disponibles** (remplacées automatiquement par le code):

**Profil:**
- `{main_goal}` - Objectif principal (semi_marathon, marathon, etc.)
- `{running_style}` - Style de course (moderate, intense, etc.)
- `{enjoys_sweating_text}` - "Oui" ou "Non"
- `{min_pace}` - Allure min confort (ex: "5:20")
- `{max_pace}` - Allure max confort (ex: "5:40")
- `{intensity_tolerance}` - Tolérance intensité (0-100)
- `{target_event_text}` - Texte événement cible ou vide

**Run:**
- `{date}` - Date du run
- `{distance_km}` - Distance en km (ex: "10.50 km")
- `{allure}` - Allure moyenne (ex: "5:30 /km")
- `{fc_moy}` - FC moyenne (ex: "145 bpm")
- `{fc_max_run}` - FC max du run
- `{deriv_cardio}` - Dérive cardiaque
- `{k_moy}` - Efficacité k

**Segments:**
- `{nb_segments}` - Nombre de segments
- `{segments_detail}` - Détail de tous les segments (généré automatiquement)

**Patterns:**
- `{patterns_list}` - Liste des patterns détectés
- `{patterns_interpretations}` - Interprétations détaillées

**Comparaisons (Phase 3 Sprint 1):**
- `{comparisons_section}` - Section complète des comparaisons vs historique

**Santé Cardiaque (Phase 3 Sprint 2B):**
- `{cardiac_section}` - Section complète analyse cardiaque

**Ressenti:**
- `{rating_stars}` - Note globale /5
- `{difficulty}` - Difficulté /5
- `{legs_feeling}` - Ressenti jambes
- `{cardio_feeling}` - Ressenti cardio
- `{enjoyment}` - Plaisir /5
- `{notes_text}` - Notes utilisateur (avec "\n- Remarque:" ou vide)

### 2. Exemples de Modifications

**Changer le ton du coach:**
```
TON: Coach perso direct, analytique mais bienveillant, emojis OK (max 3-4)
```
→ Modifier en:
```
TON: Coach motivant et énergique, style Hanson Brothers, emojis ++
```

**Ajuster la longueur des réponses:**
```
LONGUEUR: 4-6 phrases (200-350 mots)
```
→ Modifier en:
```
LONGUEUR: 2-3 phrases courtes (100-150 mots) - format ultra-concis
```

**Ajouter une règle spécifique:**
```
RÈGLES:
- Si EFFORT_BIEN_GÉRÉ: félicite et encourage à reproduire
...
```
→ Ajouter:
```
- Si distance > 15km: toujours mentionner l'hydratation et la nutrition
```

### 3. Tester vos Modifications

Après modification du fichier:
1. Sauvegarder `prompts/segment_analysis.txt`
2. Redémarrer Flask: `pkill -f app.py && .venv/bin/python app.py &`
3. Analyser un run pour voir le nouveau prompt en action

**Voir le prompt généré:**
Ajouter temporairement dans `app.py` ligne 1333:
```python
print("=" * 60)
print("PROMPT ENVOYÉ:")
print(prompt)
print("=" * 60)
```

## ⚠️ Précautions

1. **Ne pas supprimer les variables** - Gardez tous les `{variable_name}` intacts
2. **Longueur du prompt** - Plus long = plus cher en tokens
3. **Format** - Respecter la structure générale (sections séparées)
4. **Test** - Toujours tester après modification

## 💰 Impact Coût

Modification du prompt = impact sur coût par run:
- +10 lignes ≈ +150 tokens ≈ +$0.0005/run
- Prompt actuel: ~198 lignes ≈ 2970 tokens ≈ $0.015/run

## 📊 Versions

- **v2.5.0** - Prompt complet Phase 3 (comparaisons + cardiac)
- **v2.4.0** - Ajout programme hebdomadaire (backend only, pas de prompt)
- **v2.3.1** - Ajout section analyse cardiaque
- **v2.3.0** - Ajout section comparaisons historiques
- **v2.2.0** - Prompt segments + patterns
