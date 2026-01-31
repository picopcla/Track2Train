# Migration Claude → Google Gemini 1.5

## ✅ Modifications effectuées

### 1. Installation du SDK
- `google-generativeai==0.8.6` installé dans le venv
- Dépendances: `google-ai-generativelanguage`, `grpcio`, etc.

### 2. Modifications app.py

**Import**:
```python
import google.generativeai as genai
```

**Initialisation** (ligne 167-193):
```python
google_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
gemini_model = None
if google_api_key:
    genai.configure(api_key=google_api_key)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
```

**Fonction generate_ai_coaching()** (ligne 220-249):
- Remplacé `anthropic_client.messages.create()` par `gemini_model.generate_content()`
- Utilise `genai.types.GenerationConfig` pour max_tokens et temperature
- Accès réponse: `response.text` au lieu de `response.content[0].text`

**Fonction generate_coaching_comment()** (ligne 931-949):
- Même adaptation pour l'appel API
- Configuration: max_output_tokens=1500, temperature=0.3

### 3. Modifications templates/index.html

**Ligne 334**: `Powered by Anthropic` → `Powered by Google Gemini`

**Ligne 1857**: `Claude (Anthropic)` → `Google Gemini 1.5` dans le modal info

### 4. Configuration .env

Ajouté:
```
GOOGLE_GEMINI_API_KEY=YOUR_GEMINI_API_KEY_HERE
```

## 🔑 Obtenir une clé API Google Gemini

1. Aller sur https://aistudio.google.com/apikey
2. Se connecter avec votre compte Google
3. Cliquer sur "Create API Key"
4. Sélectionner le projet Google Cloud (ou en créer un)
5. Copier la clé générée
6. Remplacer `YOUR_GEMINI_API_KEY_HERE` dans `.env`

## 📊 Modèles disponibles

- **gemini-1.5-flash** (actuellement utilisé): Rapide, économique, parfait pour du coaching
- **gemini-1.5-pro**: Plus puissant mais plus lent/coûteux
- **gemini-2.0-flash-exp**: Version expérimentale 2.0

Pour changer de modèle, modifier ligne 173:
```python
gemini_model = genai.GenerativeModel('gemini-1.5-pro')  # ou gemini-2.0-flash-exp
```

## 🔄 Différences API Claude ↔ Gemini

| Aspect | Claude (Anthropic) | Gemini (Google) |
|--------|-------------------|-----------------|
| Import | `import anthropic` | `import google.generativeai as genai` |
| Init | `anthropic.Anthropic(api_key=...)` | `genai.configure(api_key=...)` puis `GenerativeModel()` |
| Appel | `client.messages.create(model, max_tokens, messages=[...])` | `model.generate_content(prompt, generation_config)` |
| Réponse | `response.content[0].text` | `response.text` |
| Format prompt | Messages avec roles | Texte direct |

## ✅ Fonctions migrées

- ✅ `generate_ai_coaching()` - Fonction générique principale
- ✅ `generate_coaching_comment()` - Commentaires coaching runs
- ⏳ `generate_k_evolution_comment()` - À migrer si utilisé
- ⏳ `generate_drift_evolution_comment()` - À migrer si utilisé
- ⏳ `generate_past_week_comment()` - À migrer si utilisé

## 🧪 Test après configuration

1. Ajouter la vraie clé API dans `.env`
2. Redémarrer le service: `sudo systemctl restart track2train-staging`
3. Vérifier les logs: `sudo journalctl -u track2train-staging -n 50`
4. Chercher: `✅ Google Gemini client initialisé`
5. Générer un commentaire IA sur un run
6. Vérifier que le HTML est bien formaté

## 💰 Coûts estimés

Gemini 1.5 Flash (modèle utilisé):
- **Gratuit** jusqu'à 15 requêtes/minute
- Très économique au-delà: ~$0.075 / 1M tokens input

Pour comparaison, Claude Haiku: ~$0.25 / 1M tokens input

## ⚠️ Note importante

Les prompts actuels sont optimisés pour Claude. Gemini peut interpréter différemment:
- Testez la génération HTML (devrait fonctionner)
- Ajustez les prompts si nécessaire dans `/prompts/coaching_run_v2.txt`
- Gemini est généralement bon pour suivre des instructions de format
