# 🎨 Intégration Frontend - Programme Hebdomadaire & Commentaires IA

**Date:** 2025-11-10
**Version:** 2.5.1
**Statut:** ⚠️ Backend prêt, Frontend à implémenter

---

## ⚠️ PROBLÈME ACTUEL

Les données suivantes sont **calculées côté backend** mais **PAS AFFICHÉES** dans le template HTML:

1. ❌ **Programme hebdomadaire** (`weekly_program`) - Sprint 3
2. ❌ **Commentaires IA par activité** (`ai_comment`) - Phase 3 Sprint 2B
3. ❌ **Analyse progression** (`progression_analysis`) - Sprint 5

### Données disponibles mais non affichées:

```python
# Dans app.py, route index() lignes 2220-2227:
weekly_program = generate_weekly_program(profile, activities)
progression_analysis = analyze_progression(activities, weeks=4)

# Passées au template ligne 2229:
return render_template(
    "index.html",
    weekly_program=weekly_program,          # ✅ Calculé, ❌ Non affiché
    progression_analysis=progression_analysis  # ✅ Calculé, ❌ Non affiché
)
```

---

## 🔧 SOLUTION 1: Afficher le Programme Hebdomadaire

### Où l'ajouter dans `templates/index.html`:

Après le carrousel des activités (vers ligne 400-500), ajouter:

```html
<!-- Programme Hebdomadaire -->
{% if weekly_program %}
<div class="weekly-program-section" style="margin-top: 2rem; padding: 1.5rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; color: white;">
    <h2 style="margin-top: 0;">📅 Programme de la Semaine</h2>

    <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 8px; margin: 1rem 0;">
        <p><strong>Objectif:</strong> {{ weekly_program.summary.total_distance }} km en {{ weekly_program.runs|length }} sorties</p>
        <p><strong>Volume total:</strong> {{ weekly_program.summary.total_time_min|int }} minutes</p>
    </div>

    {% for run in weekly_program.runs %}
    <div style="background: rgba(255,255,255,0.15); padding: 1rem; margin: 0.5rem 0; border-radius: 8px;">
        <h3 style="margin: 0 0 0.5rem 0;">
            {{ run.day_name }} - {{ run.session_type_display }}
        </h3>
        <p style="margin: 0.25rem 0;">
            <strong>Distance:</strong> {{ run.distance_km }} km •
            <strong>Durée:</strong> {{ run.duration_min|int }} min
        </p>
        <p style="margin: 0.25rem 0; font-size: 0.9em; opacity: 0.9;">
            {{ run.description }}
        </p>
    </div>
    {% endfor %}

    {% if weekly_program.ai_recommendations %}
    <div style="background: rgba(255,255,255,0.1); padding: 1rem; border-radius: 8px; margin-top: 1rem;">
        <h3 style="margin-top: 0;">💬 Recommandations IA</h3>
        <p style="white-space: pre-line;">{{ weekly_program.ai_recommendations }}</p>
    </div>
    {% endif %}
</div>
{% endif %}
```

---

## 🔧 SOLUTION 2: Afficher l'Analyse de Progression

Après le programme hebdomadaire, ajouter:

```html
<!-- Analyse Progression -->
{% if progression_analysis %}
<div class="progression-section" style="margin-top: 2rem; padding: 1.5rem; background: #f8f9fa; border-radius: 12px; border-left: 4px solid #28a745;">
    <h2 style="margin-top: 0; color: #28a745;">📈 Analyse de Progression</h2>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin: 1rem 0;">
        <div style="text-align: center; padding: 1rem; background: white; border-radius: 8px;">
            <div style="font-size: 2em; font-weight: bold; color: #667eea;">
                {{ progression_analysis.runs_completed }}
            </div>
            <div style="font-size: 0.9em; color: #666;">Sorties</div>
        </div>

        <div style="text-align: center; padding: 1rem; background: white; border-radius: 8px;">
            <div style="font-size: 2em; font-weight: bold; color: #28a745;">
                {{ progression_analysis.fitness_score|round(1) }}/10
            </div>
            <div style="font-size: 0.9em; color: #666;">Score Forme</div>
        </div>

        <div style="text-align: center; padding: 1rem; background: white; border-radius: 8px;">
            <div style="font-size: 2em; font-weight: bold; color: #764ba2;">
                {{ progression_analysis.total_distance|round(1) }} km
            </div>
            <div style="font-size: 0.9em; color: #666;">Distance Totale</div>
        </div>
    </div>

    {% if progression_analysis.trends %}
    <div style="margin-top: 1rem;">
        <h3>📊 Tendances:</h3>
        <ul>
        {% for trend in progression_analysis.trends %}
            <li>{{ trend }}</li>
        {% endfor %}
        </ul>
    </div>
    {% endif %}
</div>
{% endif %}
```

---

## 🔧 SOLUTION 3: Bouton Commentaires IA par Activité

### Dans chaque slide du carrousel (chercher la balise `<div class="carousel-slide">`):

Après les informations de l'activité, ajouter:

```html
<!-- Bouton Génération Commentaire IA -->
<div style="margin-top: 1rem;">
    <button
        class="btn-generate-ai"
        data-activity-date="{{ activity.date }}"
        data-slide-index="{{ loop.index0 }}"
        onclick="generateAIComment(this)"
        style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 10px 20px; border-radius: 8px; cursor: pointer; font-size: 14px; width: 100%; transition: all 0.3s;">
        🤖 Générer Commentaire IA
    </button>
    <div id="ai-comment-{{ loop.index0 }}" class="ai-comment-container" style="margin-top: 1rem; padding: 1rem; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea; display: none;">
    </div>
</div>
```

### JavaScript à ajouter avant `</body>`:

```html
<script>
async function generateAIComment(button) {
    const activityDate = button.dataset.activityDate;
    const slideIndex = button.dataset.slideIndex;
    const commentDiv = document.getElementById(`ai-comment-${slideIndex}`);

    // Désactiver le bouton et afficher le chargement
    button.disabled = true;
    button.innerHTML = '⏳ Génération en cours... (5-10 sec)';

    try {
        const response = await fetch(`/generate_ai_comment/${activityDate}`);
        const data = await response.json();

        if (data.success) {
            // Afficher le commentaire
            commentDiv.style.display = 'block';
            commentDiv.innerHTML = `
                <div>
                    <strong style="color: #667eea;">💬 Coach IA:</strong>
                    <p style="margin: 0.5rem 0; line-height: 1.6; white-space: pre-line;">${data.comment}</p>
                    <small style="color: #666;">
                        📊 ${data.segments_count} segments • ${data.patterns_count} patterns détectés
                    </small>
                </div>
            `;
            // Cacher le bouton après génération
            button.style.display = 'none';
        } else {
            // Afficher l'erreur
            commentDiv.style.display = 'block';
            commentDiv.innerHTML = `
                <p style="color: #dc3545; font-weight: bold;">⚠️ ${data.error}</p>
            `;
            button.disabled = false;
            button.innerHTML = '🔄 Réessayer';
        }
    } catch (error) {
        // Erreur réseau
        commentDiv.style.display = 'block';
        commentDiv.innerHTML = `
            <p style="color: #dc3545; font-weight: bold;">❌ Erreur réseau. Vérifiez votre connexion.</p>
        `;
        button.disabled = false;
        button.innerHTML = '🔄 Réessayer';
        console.error('Erreur:', error);
    }
}
</script>
```

---

## 📝 Styles CSS additionnels

Ajouter dans la section `<style>`:

```css
.btn-generate-ai:hover:not(:disabled) {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-generate-ai:disabled {
    opacity: 0.6;
    cursor: not-allowed;
}

.weekly-program-section h3 {
    font-size: 1.1em;
}

.progression-section ul {
    list-style: none;
    padding-left: 0;
}

.progression-section li:before {
    content: "✓ ";
    color: #28a745;
    font-weight: bold;
    margin-right: 0.5rem;
}
```

---

## 🧪 Test

Après avoir ajouté ces modifications au template:

1. **Redémarrer Flask**:
   ```bash
   pkill -f "python.*app.py"
   .venv/bin/python app.py &
   ```

2. **Vérifier la page**:
   - Le programme hebdomadaire devrait s'afficher sous le carrousel
   - L'analyse de progression devrait s'afficher après
   - Chaque activité du carrousel devrait avoir un bouton "Générer Commentaire IA"

3. **Tester le bouton IA**:
   - Cliquer sur "Générer Commentaire IA" sur une activité
   - Attendre 5-10 secondes
   - Le commentaire devrait s'afficher

---

## 📊 État Actuel

✅ **Backend:** Toutes les fonctions implémentées et testées
✅ **API REST:** `/generate_ai_comment/<date>` fonctionnelle
❌ **Frontend:** Template HTML à modifier pour afficher les données

**Fichier à modifier:** `/opt/app/Track2Train-staging/templates/index.html`

---

**🎯 Une fois ces modifications faites, TOUTES les fonctionnalités Phase 3 seront visibles!**
