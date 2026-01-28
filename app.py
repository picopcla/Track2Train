import os
import json
import time
from datetime import datetime, timedelta, date
from pathlib import Path
import numpy as np
from dateutil import parser
from flask import Flask, render_template, request, redirect, jsonify
from google import genai
from dotenv import load_dotenv


# === Chargement des variables d'environnement ===
# Charge le .env du projet (fonctionne sur Windows, Linux, Mac)
load_dotenv()

# Vérification de la clé Gemini (seule variable obligatoire)
if not os.getenv("GOOGLE_GEMINI_API_KEY"):
    print("⚠️ GOOGLE_GEMINI_API_KEY non définie - le coaching IA sera désactivé")
# === Fin chargement ENV ===


# --- Helpers Drive (après bootstrap ENV !) ---

from data_access_local import (
    load_activities_local as load_activities_from_drive,
    load_profile_local as load_profile_from_drive,
    save_profile_local,
    save_activities_local as save_activities_to_drive,
    read_output_json_local as read_output_json,
    write_output_json_local as write_output_json,
)

# Import des fonctions de calcul des statistiques par type de run
from calculate_running_stats import calculate_stats_by_type, save_running_stats

# Pour compatibilité (si jamais utilisé ailleurs)
class DriveUnavailableError(RuntimeError):
    pass

# Helpers pour compatibilité
def read_weekly_plan(week_number=None):
    """Lit le programme hebdomadaire. Si week_number fourni, lit depuis l'historique."""
    if week_number:
        # Essayer de lire l'historique pour cette semaine
        historical = read_output_json(f'weekly_plan_w{week_number}.json')
        if historical:
            return historical
    # Sinon lire le plan actuel
    return read_output_json('weekly_plan.json')

def write_weekly_plan(data):
    """Sauvegarde le programme actuel ET dans l'historique avec le numéro de semaine."""
    write_output_json('weekly_plan.json', data)
    # Sauvegarder aussi dans l'historique si week_number présent
    if data and data.get('week_number'):
        week_num = data['week_number']
        write_output_json(f'weekly_plan_w{week_num}.json', data)
        print(f"📅 Programme semaine {week_num} sauvegardé dans l'historique")


def read_weekly_objectives(week_number=None):
    """Lit les objectifs hebdomadaires. Si week_number fourni, lit depuis l'historique."""
    if week_number:
        return read_output_json(f'weekly_objectives_w{week_number}.json')
    return read_output_json('weekly_objectives.json')


def write_weekly_objectives(week_number, objectives):
    """
    Sauvegarde les objectifs d'une semaine.

    Args:
        week_number: Numéro de la semaine ISO
        objectives: Dict avec les objectifs {
            'week_number': int,
            'total_distance_km': float,
            'total_runs': int,
            'k_target': float,
            'drift_target': float,
            'focus': str,
            'generated_at': str (ISO datetime)
        }
    """
    objectives['week_number'] = week_number
    objectives['generated_at'] = datetime.now().isoformat()

    # Sauvegarder le fichier courant
    write_output_json('weekly_objectives.json', objectives)
    # Sauvegarder dans l'historique
    write_output_json(f'weekly_objectives_w{week_number}.json', objectives)
    print(f"🎯 Objectifs semaine {week_number} sauvegardés")
    return objectives


def compare_weekly_objectives(current_week, previous_week=None):
    """
    Compare les objectifs de la semaine courante avec la précédente.

    Returns:
        Dict avec la comparaison ou None si pas de données précédentes
    """
    if previous_week is None:
        previous_week = current_week - 1
        if previous_week < 1:
            previous_week = 52

    prev_objectives = read_weekly_objectives(previous_week)
    if not prev_objectives:
        return None

    return {
        'previous_week': previous_week,
        'previous_distance': prev_objectives.get('total_distance_km', 0),
        'previous_runs': prev_objectives.get('total_runs', 0),
        'previous_k_target': prev_objectives.get('k_target', 0),
        'previous_drift_target': prev_objectives.get('drift_target', 0),
        'previous_focus': prev_objectives.get('focus', '')
    }


def parse_weekly_objectives_from_html(html_content, week_number):
    """
    Parse les objectifs hebdomadaires depuis le HTML généré par l'IA.

    Args:
        html_content: Le HTML généré contenant les objectifs
        week_number: Numéro de la semaine

    Returns:
        Dict avec les objectifs ou None si non trouvés
    """
    import re

    objectives = {
        'week_number': week_number,
        'total_distance_km': 0,
        'total_runs': 0,
        'k_target': 0,
        'drift_target': 0,
        'focus': ''
    }

    try:
        # Chercher la section OBJECTIFS SEMAINE
        # Les patterns doivent gérer le tag </strong> entre le label et la valeur
        # Ex: <strong>Volume:</strong> 35 km sur 4 séances

        # Pattern: Volume: XX km sur X séances (avec </strong> optionnel)
        volume_match = re.search(r'Volume:?\s*(?:</strong>)?\s*(\d+(?:[.,]\d+)?)\s*km\s+sur\s+(\d+)\s+séances?', html_content, re.IGNORECASE)
        if volume_match:
            objectives['total_distance_km'] = float(volume_match.group(1).replace(',', '.'))
            objectives['total_runs'] = int(volume_match.group(2))
            print(f"   📊 Volume extrait: {objectives['total_distance_km']} km, {objectives['total_runs']} séances")

        # Pattern: k moyen cible: < X.XX (avec </strong> optionnel)
        k_match = re.search(r'k\s+(?:moyen\s+)?cible:?\s*(?:</strong>)?\s*<?[\s]*(\d+(?:[.,]\d+)?)', html_content, re.IGNORECASE)
        if k_match:
            objectives['k_target'] = float(k_match.group(1).replace(',', '.'))
            print(f"   📊 k cible extrait: {objectives['k_target']}")

        # Pattern: Drift moyen cible: < X% (avec </strong> optionnel)
        drift_match = re.search(r'[Dd]rift\s+(?:moyen\s+)?cible:?\s*(?:</strong>)?\s*<?[\s]*(\d+(?:[.,]\d+)?)\s*%?', html_content, re.IGNORECASE)
        if drift_match:
            objectives['drift_target'] = float(drift_match.group(1).replace(',', '.'))
            print(f"   📊 Drift cible extrait: {objectives['drift_target']}%")

        # Pattern: Focus: [texte jusqu'à </div>] (avec </strong> optionnel)
        focus_match = re.search(r'Focus:?\s*(?:</strong>)?\s*([^<]+)', html_content, re.IGNORECASE)
        if focus_match:
            objectives['focus'] = focus_match.group(1).strip()[:200]  # Limiter à 200 chars
            print(f"   📊 Focus extrait: {objectives['focus'][:50]}...")

        # Vérifier qu'on a au moins quelques données
        if objectives['total_distance_km'] > 0 or objectives['k_target'] > 0:
            return objectives

        print("   ⚠️ Pas d'objectifs trouvés dans le HTML")
        return None

    except Exception as e:
        print(f"   ❌ Erreur parsing objectifs: {e}")
        return None


# =============================================================================
# 🔍 ANALYSE CONTEXTUELLE POUR COACHING IA
# =============================================================================

MOTS_ALERTES = [
    "fatigue", "fatigué", "fatiguée", "lourd", "lourdes", "dur", "dure", "difficile",
    "douleur", "douleurs", "mal", "épuisé", "épuisée", "vidé", "vidée", "crampe",
    "crampes", "courbature", "courbatures", "tendu", "raide", "forcé", "poussé",
    "galère", "galèré", "souffert", "pénible", "laborieux"
]

MOTS_POSITIFS = [
    "bien", "facile", "fluide", "forme", "top", "nickel", "carton", "super",
    "excellent", "parfait", "génial", "plaisir", "agréable", "léger", "légère",
    "aisé", "confortable", "régal", "tranquille", "relax", "easy", "cool"
]


def analyser_notes_seances(notes_list: list) -> dict:
    """
    Analyse les notes de séances pour détecter les signaux de fatigue ou de forme.

    Args:
        notes_list: Liste des notes textuelles des séances

    Returns:
        dict avec alertes détectées, positifs détectés, et tendance globale
    """
    alertes_trouvees = []
    positifs_trouves = []

    for note in notes_list:
        if not note:
            continue
        note_lower = note.lower()

        for mot in MOTS_ALERTES:
            if mot in note_lower and mot not in alertes_trouvees:
                alertes_trouvees.append(mot)

        for mot in MOTS_POSITIFS:
            if mot in note_lower and mot not in positifs_trouves:
                positifs_trouves.append(mot)

    # Déterminer la tendance
    score = len(positifs_trouves) - len(alertes_trouvees)
    if score >= 2:
        tendance = "positive"
    elif score <= -2:
        tendance = "negative"
    else:
        tendance = "neutre"

    return {
        "alertes": alertes_trouvees,
        "positifs": positifs_trouves,
        "tendance": tendance,
        "score": score
    }


def calculer_tendances_3_semaines(current_week: int) -> dict:
    """
    Calcule les tendances k et drift sur les 3 dernières semaines.

    Args:
        current_week: Numéro de la semaine courante

    Returns:
        dict avec tendances k et drift (stable/amélioration/dégradation)
    """
    k_values = []
    drift_values = []

    # Charger les 3 dernières semaines d'objectifs (qui contiennent les réalisés)
    for i in range(3):
        week_num = current_week - i
        if week_num < 1:
            week_num += 52

        objectives = read_weekly_objectives(week_num)
        if objectives:
            if objectives.get('k_realise'):
                k_values.append(objectives['k_realise'])
            elif objectives.get('k_target'):
                k_values.append(objectives['k_target'])

            if objectives.get('drift_realise'):
                drift_values.append(objectives['drift_realise'])
            elif objectives.get('drift_target'):
                drift_values.append(objectives['drift_target'])

    def calc_tendance(values):
        if len(values) < 2:
            return "insuffisant"
        # Pour k et drift, une baisse = amélioration
        diff = values[0] - values[-1]  # récent - ancien
        if diff < -0.03:  # Amélioration significative (k/drift a baissé)
            return "amélioration"
        elif diff > 0.03:  # Dégradation (k/drift a augmenté)
            return "dégradation"
        else:
            return "stable"

    return {
        "k_tendance": calc_tendance(k_values),
        "k_valeurs": k_values,
        "drift_tendance": calc_tendance(drift_values),
        "drift_valeurs": drift_values
    }


def generer_dossier_analyse(week_runs: list, weekly_plan: dict, week_objectives: dict,
                            current_week: int, feedbacks: dict) -> dict:
    """
    Génère un dossier d'analyse structuré pour l'IA.

    Args:
        week_runs: Liste des runs réalisés cette semaine
        weekly_plan: Programme prévu pour la semaine
        week_objectives: Objectifs de la semaine
        current_week: Numéro de la semaine
        feedbacks: Dictionnaire des feedbacks utilisateur

    Returns:
        dict structuré avec toutes les données d'analyse
    """
    # Volume
    total_realise = sum(r.get('distance_km', 0) for r in week_runs)
    total_programme = weekly_plan.get('summary', {}).get('total_distance', 0) if weekly_plan else 0
    runs_programmes = len(weekly_plan.get('runs', [])) if weekly_plan else 0

    # Qualité moyenne
    k_values = [r.get('k_moy', 0) for r in week_runs if r.get('k_moy')]
    drift_values = [r.get('deriv_cardio', 0) for r in week_runs if r.get('deriv_cardio')]
    k_moyen = sum(k_values) / len(k_values) if k_values else 0
    drift_moyen = sum(drift_values) / len(drift_values) if drift_values else 0

    # Collecter les notes de séances
    notes_seances = []
    for run in week_runs:
        activity_id = str(run.get('activity_id', ''))
        if activity_id in feedbacks:
            note = feedbacks[activity_id].get('notes', '')
            if note:
                notes_seances.append(note)

    # Analyser les notes
    analyse_notes = analyser_notes_seances(notes_seances)

    # Tendances sur 3 semaines
    tendances = calculer_tendances_3_semaines(current_week)

    # Objectifs de la semaine (fallback sur le programme si pas d'objectifs définis)
    obj_distance = week_objectives.get('total_distance_km', 0) if week_objectives else 0
    obj_k = week_objectives.get('k_target', 0) if week_objectives else 0
    obj_drift = week_objectives.get('drift_target', 0) if week_objectives else 0

    # Si pas d'objectifs, utiliser le programme comme référence
    if obj_distance == 0 and total_programme > 0:
        obj_distance = total_programme
        print(f"   ⚠️ Pas d'objectifs définis, utilisation du programme comme référence: {obj_distance} km")

    # Construire le dossier
    dossier = {
        "semaine": current_week,
        "volume": {
            "programme_km": round(total_programme, 1),
            "realise_km": round(total_realise, 1),
            "taux_completion": round(total_realise / total_programme * 100, 1) if total_programme > 0 else 0,
            "objectif_km": round(obj_distance, 1) if obj_distance > 0 else round(total_programme, 1),
            "taux_vs_objectif": round(total_realise / obj_distance * 100, 1) if obj_distance > 0 else (round(total_realise / total_programme * 100, 1) if total_programme > 0 else 0)
        },
        "efficacite": {
            "k_moyen_realise": round(k_moyen, 3),
            "k_objectif": round(obj_k, 3) if obj_k else None,
            "k_tendance_3sem": tendances["k_tendance"],
            "k_historique": tendances["k_valeurs"],
            "drift_moyen_realise": round(drift_moyen, 1),
            "drift_objectif": round(obj_drift, 1) if obj_drift else None,
            "drift_tendance_3sem": tendances["drift_tendance"],
            "drift_historique": tendances["drift_valeurs"]
        },
        "qualite_seances": {
            "programmees": runs_programmes,
            "completees": len(week_runs),
            "taux_completion": round(len(week_runs) / runs_programmes * 100, 1) if runs_programmes > 0 else 0
        },
        "signaux_textuels": {
            "notes_seances": notes_seances,
            "alertes_detectees": analyse_notes["alertes"],
            "positifs_detectes": analyse_notes["positifs"],
            "tendance_ressenti": analyse_notes["tendance"],
            "score_ressenti": analyse_notes["score"]
        }
    }

    return dossier


def update_running_stats_after_webhook():
    """
    Met à jour les statistiques de running après un nouveau run
    À appeler après avoir traité un nouveau run (webhook ou index)
    """
    try:
        # Charger les activités
        activities = load_activities_from_drive()

        # Calculer les stats par type (15 dernières courses)
        stats_by_type = calculate_stats_by_type(activities, n_last=15)

        # Sauvegarder dans running_stats.json
        save_running_stats(stats_by_type, 'running_stats.json')

        print("✅ Running stats mises à jour après traitement")
        return stats_by_type

    except Exception as e:
        print(f"❌ Erreur mise à jour running stats: {e}")
        return None




# -------------------
# Fonction pour loguer les étapes avec durée
# -------------------
def log_step(message, start_time):
    elapsed = time.time() - start_time
    print(f"⏱️ {message} — {elapsed:.2f} sec depuis début")


# --- Constantes globales ---
WEATHER_CODE_MAP = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌧️", 55: "🌧️", 61: "🌧️", 63: "🌧️", 65: "🌧️",
    71: "❄️", 73: "❄️", 75: "❄️", 77: "❄️", 80: "🌧️", 81: "🌧️", 82: "🌧️",
    95: "⛈️", 96: "⛈️", 99: "⛈️"
}

app = Flask(__name__)


# --- Init Google Gemini 2.5 ---
google_api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
gemini_client = None
if google_api_key:
    try:
        gemini_client = genai.Client(api_key=google_api_key)
        print("✅ Google Gemini client initialisé (gemini-2.0-flash)")
    except Exception as e:
        print(f"⚠️ Erreur init Gemini: {e}")
else:
    print("⚠️ GOOGLE_GEMINI_API_KEY non définie")
    print("⚠️ Veuillez ajouter GOOGLE_GEMINI_API_KEY dans .env")


# --- Fonction helper: Charger prompts depuis fichiers ---
def load_prompt(prompt_name):
    """
    Charge un fichier prompt depuis prompts/{prompt_name}.txt

    Args:
        prompt_name: Nom du fichier prompt (sans .txt)

    Returns:
        str: Contenu du prompt template
    """
    prompt_file = Path(__file__).parent / "prompts" / f"{prompt_name}.txt"
    try:
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️ Fichier prompt introuvable: {prompt_file}")
        return ""
    except Exception as e:
        print(f"❌ Erreur lecture prompt {prompt_name}: {e}")
        return ""


# --- Fonction IA: Génération avec Google Gemini 2.5 ---
def generate_ai_coaching(prompt_content, max_tokens=500, temperature=0.3):
    """
    Fonction générique universelle pour générer du contenu avec Google Gemini 2.5

    Args:
        prompt_content: Le prompt à envoyer à Gemini
        max_tokens: Nombre maximum de tokens (défaut: 500)
        temperature: Température de génération (défaut: 0.3)

    Returns:
        str: La réponse de Gemini ou un message par défaut si erreur
    """
    if not gemini_client:
        return "⚠️ Coaching IA temporairement indisponible (clé API non configurée)."

    try:
        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt_content,
            config={
                'max_output_tokens': max_tokens,
                'temperature': temperature
            }
        )

        return response.text
    except Exception as e:
        print(f"❌ Erreur generate_ai_coaching: {e}")
        return f"⚠️ Erreur lors de la génération du coaching IA. Veuillez réessayer plus tard."


def load_ai_comments():
    """Charge les commentaires IA principaux sauvegardés depuis outputs/ai_comments.json"""
    try:
        comments = read_output_json('ai_comments.json') or {}
        return comments
    except Exception as e:
        print(f"⚠️ Erreur chargement ai_comments: {e}")
        return {}


def save_ai_comment(activity_date, comment, segments_count, patterns_count):
    """Sauvegarde un commentaire IA principal dans outputs/ai_comments.json"""
    try:
        comments = load_ai_comments()
        comments[activity_date] = {
            'comment': comment,
            'segments_count': segments_count,
            'patterns_count': patterns_count,
            'generated_at': datetime.now().isoformat()
        }
        write_output_json('ai_comments.json', comments)
        print(f"💾 Commentaire IA sauvegardé pour {activity_date}")
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde ai_comment: {e}")


def load_zones_comments():
    """Charge les commentaires IA zones FC depuis outputs/zones_fc_comments.json"""
    try:
        comments = read_output_json('zones_fc_comments.json')
        return comments if comments is not None else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def save_zones_comment(activity_date, zones_comment):
    """Sauvegarde un commentaire IA zones FC dans outputs/zones_fc_comments.json"""
    try:
        comments = load_zones_comments()
        comments[activity_date] = {
            'comment': zones_comment,
            'generated_at': datetime.now().isoformat()
        }
        write_output_json('zones_fc_comments.json', comments)
        print(f"💾 Commentaire zones FC sauvegardé pour {activity_date}")
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde zones_comment: {e}")

def generate_past_week_comment(past_week_analysis):
    """
    Génère un commentaire IA sur la semaine écoulée (réalisé vs programmé).

    Args:
        past_week_analysis: Dict résultat de analyze_past_week()

    Returns:
        str: Commentaire IA motivant (30-50 mots) ou None si données insuffisantes
    """
    if not gemini_client or not past_week_analysis:
        return None

    # Charger le prompt template
    try:
        with open('prompts/past_week_analysis.txt', 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    except Exception as e:
        print(f"❌ Erreur lecture prompt past_week_analysis.txt: {e}")
        return None

    # Formatter les runs programmés
    programmed_runs_text = ""
    for i, run in enumerate(past_week_analysis.get('run_details', []), 1):
        prog = run['programmed']
        programmed_runs_text += f"{i}. {prog['day']} ({prog['day_date']}): {prog['type_display']} - {prog['distance_km']} km à {prog['pace_target']}\n"

    # Formatter les détails par run (avec zones cardiaques)
    run_details_text = ""
    for i, run in enumerate(past_week_analysis.get('run_details', []), 1):
        prog = run['programmed']
        realized = run['realized']
        status = run['status']

        if status == 'completed':
            real_distance = realized.get('distance_km', 0)
            real_pace = realized.get('allure', '-')
            fc_moy = realized.get('fc_moy', '-')

            # Ajouter les zones cardiaques si disponibles
            zones_text = ""
            zone_percentages = realized.get('zone_percentages', {})
            if zone_percentages:
                zones_values = []
                for z in ['1', '2', '3', '4', '5']:
                    pct = zone_percentages.get(z, 0)
                    zones_values.append(f"Z{z}:{pct:.0f}%")
                zones_text = f" | Zones: {', '.join(zones_values)}"

            run_details_text += f"✅ {prog['day']}: {prog['type_display']} RÉALISÉ - {real_distance} km à {real_pace} (FC moy: {fc_moy} bpm){zones_text}\n"
        else:
            run_details_text += f"❌ {prog['day']}: {prog['type_display']} NON RÉALISÉ ({prog['distance_km']} km prévu)\n"

    # Récupérer les données de score (NOUVEAU)
    score = past_week_analysis.get('score', 0)
    score_details = past_week_analysis.get('score_details', {})
    strengths = past_week_analysis.get('strengths', [])
    improvements = past_week_analysis.get('improvements', [])

    # Formatter les listes
    strengths_list = "\n".join(f"  • {s}" for s in strengths) if strengths else "  • (aucun point fort détecté)"
    improvements_list = "\n".join(f"  • {s}" for s in improvements) if improvements else "  • (rien à améliorer)"

    # Remplir le prompt
    prompt = prompt_template.format(
        week_number=past_week_analysis.get('week_number', '?'),
        start_date=past_week_analysis.get('start_date', '?'),
        end_date=past_week_analysis.get('end_date', '?'),
        runs_completed=past_week_analysis.get('runs_completed', 0),
        total_programmed=past_week_analysis.get('total_programmed', 0),
        adherence_rate=past_week_analysis.get('adherence_rate', 0),
        total_distance_programmed=past_week_analysis.get('total_distance_programmed', 0),
        total_distance_realized=round(past_week_analysis.get('total_distance_realized', 0), 1),
        programmed_runs=programmed_runs_text.strip(),
        run_details=run_details_text.strip(),
        # NOUVEAU: Note et analyse
        weekly_score=score,
        score_volume=score_details.get('volume', 0),
        score_adherence=score_details.get('adherence', 0),
        score_quality=score_details.get('quality', 0),
        score_type_respect=score_details.get('type_respect', 0),
        score_regularity=score_details.get('regularity', 0),
        strengths_list=strengths_list,
        improvements_list=improvements_list
    )

    # Générer le commentaire avec Claude
    try:
        comment = generate_ai_coaching(prompt, max_tokens=150)
        if comment:
            # S'assurer que c'est 30-50 mots
            words = comment.split()
            if len(words) > 50:
                comment = ' '.join(words[:50])
            return comment
        return None
    except Exception as e:
        print(f"❌ Erreur generate_past_week_comment: {e}")
        return None


# --- Helper date robuste ---
def _date_key(a):
    d = a.get("date") or ""
    try:
        return parser.isoparse(d)  # gère "Z" et offsets
    except Exception:
        return datetime.min


# -------------------
# Détection du type de séance (règles simples par distance)
# -------------------
## ═══════════════════════════════════════════════════════════════════
## CLASSIFICATION DES RUNS - SYSTÈME SIMPLIFIÉ
## ═══════════════════════════════════════════════════════════════════

def classify_run_type(activity):
    """
    Classification UNIQUE et SIMPLE des runs basée sur distance + allure.

    TYPOLOGIE:
    1. tempo_recup  : < 7 km ET allure > 5:20/km  → Zones 1-2 (récupération)
    2. tempo_rapide : < 7 km ET allure ≤ 5:20/km  → Zones 2-3 (tempo court)
    3. endurance    : 7-11 km                     → Zones 2-3 (allure semi)
    4. long_run     : > 11 km                     → Zones 2-3 (sortie longue)

    OBJECTIFS:
    - tempo_recup   : k ~4.9,  dérive ~6-7%,   FC 125-135
    - tempo_rapide  : k ~5.6,  dérive ~8-9%,   FC 135-145
    - endurance     : k ~5.2,  dérive ~10-12%, FC 135-145
    - long_run      : k ~5.2,  dérive ~14-16%, FC 130-140
    """
    # Récupérer la distance
    dist_km = activity.get('distance_km', 0)

    # Si pas de distance_km, essayer depuis points
    if not dist_km or dist_km == 0:
        pts = activity.get("points", [])
        if pts and len(pts) > 0:
            dist_km = pts[-1].get("distance", 0) / 1000.0

    # Si toujours pas de distance, retourner inconnu
    if not dist_km or dist_km == 0:
        return "inconnue"

    # Calcul allure moyenne en min/km
    duree_sec = activity.get('duree_sec', 0)
    if not duree_sec or duree_sec == 0:
        pts = activity.get("points", [])
        if pts and len(pts) > 0:
            duree_sec = pts[-1].get("time", 0)

    if duree_sec > 0 and dist_km > 0:
        pace_min_per_km = (duree_sec / 60.0) / dist_km
    else:
        pace_min_per_km = 999  # Pas de données → considéré comme lent

    # Classification par distance
    if dist_km > 11:
        return "long_run"

    if dist_km >= 7:
        return "endurance"

    # < 7 km : distinction selon allure (seuil 5:20/km = 5.333 min/km)
    if pace_min_per_km <= 5.333:
        return "tempo_rapide"
    else:
        return "tempo_recup"


def calculate_type_averages(activities, target_run_type, limit=10):
    """
    Calcule les moyennes des 10 derniers runs d'un type donné.

    Args:
        activities: Liste des activités (triées du plus récent au plus ancien)
        target_run_type: Type recherché ('tempo_recup', 'tempo_rapide', 'endurance', 'long_run')
        limit: Nombre de runs à moyenner (par défaut 10)

    Returns:
        dict: {
            'count': nombre de runs trouvés,
            'allure_moy': allure moyenne en min/km,
            'k_moy': k moyen,
            'drift_moy': drift moyen en %,
            'cadence_moy': cadence moyenne en SPM,
            'fc_moy': FC moyenne en bpm,
            'zones_fc': {1: X%, 2: Y%, ...} distribution zones FC moyennes
        }
    """
    matching_runs = []

    for act in activities:
        # Classifier le run
        run_type = classify_run_type(act)

        # Si correspond au type recherché
        if run_type == target_run_type:
            matching_runs.append(act)

            # Arrêter après avoir trouvé assez de runs
            if len(matching_runs) >= limit:
                break

    # Si aucun run trouvé
    if not matching_runs:
        return {
            'count': 0,
            'allure_moy': None,
            'k_moy': None,
            'drift_moy': None,
            'cadence_moy': None,
            'fc_moy': None,
            'zones_fc': {}
        }

    # Calculer les moyennes
    allures = []
    ks = []
    drifts = []
    cadences = []
    fcs = []
    zones_totals = {1: [], 2: [], 3: [], 4: [], 5: []}

    for act in matching_runs:
        # Allure - convertir depuis format "5:15" vers min/km décimal
        allure_str = act.get('allure')
        if allure_str and allure_str != "-":
            try:
                # Format "5:15" -> 5.25 min/km
                parts = allure_str.split(':')
                if len(parts) == 2:
                    mins = int(parts[0])
                    secs = int(parts[1])
                    pace = mins + (secs / 60.0)
                    allures.append(pace)
            except (ValueError, IndexError):
                pass

        # k
        k = act.get('k_moy')
        if k and k != "-" and k > 0:
            ks.append(k)

        # Drift - utiliser deriv_cardio
        drift = act.get('deriv_cardio')
        if drift is not None and drift != "-":
            drifts.append(drift)

        # Cadence - essayer cadence_spm puis cad_mean_spm
        cad = act.get('cadence_spm') or act.get('cad_mean_spm')
        if cad and cad != "-" and cad > 0:
            cadences.append(cad)

        # FC moyenne
        fc = act.get('fc_moy')
        if fc and fc != "-" and fc > 0:
            fcs.append(fc)

        # Zones FC
        cardiac = act.get('cardiac_analysis', {})
        if cardiac and 'hr_zones' in cardiac:
            zone_pcts = cardiac['hr_zones'].get('zone_percentages', {})
            for z in range(1, 6):
                pct = zone_pcts.get(z, 0)
                if pct > 0:
                    zones_totals[z].append(pct)

    # Calcul moyennes
    allure_moy = sum(allures) / len(allures) if allures else None
    k_moy = sum(ks) / len(ks) if ks else None
    drift_moy = sum(drifts) / len(drifts) if drifts else None
    cadence_moy = sum(cadences) / len(cadences) if cadences else None
    fc_moy = sum(fcs) / len(fcs) if fcs else None

    # Moyennes zones FC
    zones_fc = {}
    for z in range(1, 6):
        if zones_totals[z]:
            zones_fc[z] = sum(zones_totals[z]) / len(zones_totals[z])
        else:
            zones_fc[z] = 0

    return {
        'count': len(matching_runs),
        'allure_moy': allure_moy,
        'k_moy': k_moy,
        'drift_moy': drift_moy,
        'cadence_moy': cadence_moy,
        'fc_moy': fc_moy,
        'zones_fc': zones_fc
    }


def generate_remaining_runs_html(weekly_plan, current_planned_run, activities, current_run_date_iso):
    """
    Génère le HTML des runs restants du programme de la semaine.
    Identifie les runs déjà faits par TYPE (pas par ordre).
    Retourne une chaîne vide si aucun run restant.
    """
    if not weekly_plan or 'runs' not in weekly_plan:
        return ""

    # Extraire la date du run actuel
    current_date = None
    if current_run_date_iso:
        try:
            current_date = datetime.strptime(current_run_date_iso[:10], '%Y-%m-%d')
        except ValueError:
            pass

    if not current_date:
        return ""

    # Récupérer les runs de la semaine en cours depuis activities
    current_week = current_date.isocalendar()[1]
    current_year = current_date.isocalendar()[0]

    # Mapping des types pour la correspondance
    type_mapping = {
        'recuperation': ['recuperation', 'tempo_recup', 'recovery'],
        'tempo_recup': ['recuperation', 'tempo_recup', 'recovery'],
        'endurance': ['endurance', 'tempo_leger'],
        'tempo_leger': ['endurance', 'tempo_leger'],
        'tempo_rapide': ['tempo_rapide', 'tempo', 'threshold'],
        'long_run': ['long_run', 'sortie_longue'],
        'fractionne': ['fractionne', 'interval', 'vma']
    }

    # Collecter les types de runs effectués cette semaine (y compris le run actuel)
    completed_types = []
    if activities:
        for act in activities:
            act_date_str = act.get('date', '')
            if act_date_str:
                try:
                    act_date = datetime.strptime(act_date_str[:10], '%Y-%m-%d')
                    if act_date.isocalendar()[1] == current_week and act_date.isocalendar()[0] == current_year:
                        run_type = (act.get('session_category') or act.get('type_sortie', '') or '').lower()
                        if run_type:
                            completed_types.append(run_type)
                except ValueError:
                    pass

    print(f"📊 Runs effectués cette semaine (types): {completed_types}")

    # Identifier les runs du programme qui n'ont PAS encore été faits
    remaining_runs = []
    used_completed = []  # Pour éviter de matcher plusieurs fois le même run effectué

    for run in weekly_plan['runs']:
        planned_type = run.get('type', '').lower()
        possible_matches = type_mapping.get(planned_type, [planned_type])

        # Vérifier si ce type a été effectué
        is_completed = False
        for i, completed_type in enumerate(completed_types):
            if i not in used_completed:
                if completed_type in possible_matches or planned_type in completed_type or completed_type in planned_type:
                    is_completed = True
                    used_completed.append(i)
                    print(f"✅ Run programme '{planned_type}' matché avec run effectué '{completed_type}'")
                    break

        if not is_completed:
            remaining_runs.append(run)
            print(f"⏳ Run programme '{planned_type}' → RESTANT")

    if not remaining_runs:
        print("📋 Aucun run restant cette semaine")
        return ""

    # Générer le HTML
    html = """
<div style="background: #eff6ff; border: 2px solid #3b82f6; padding: 14px 16px; border-radius: 10px; margin-top: 16px;">
<div style="font-weight: 700; font-size: 15px; color: #1d4ed8; margin-bottom: 12px;">📋 RUNS RESTANTS CETTE SEMAINE</div>
"""

    for run in remaining_runs:
        html += f"""
<div style="background: white; padding: 10px 12px; border-radius: 8px; margin-bottom: 8px; border-left: 4px solid #3b82f6;">
<div style="font-weight: 600; color: #1d4ed8; font-size: 14px;">🏃 {run.get('type_display', run.get('type', 'N/D'))}</div>
<div style="font-size: 12px; color: #374151; margin-top: 4px;">
{run.get('distance_km', 'N/D')} km • Allure {run.get('pace_target', 'N/D')} • k cible {run.get('k_target', 'N/D')} • Drift max {run.get('drift_target', 'N/D')}%
</div>
</div>
"""

    html += "</div>"
    return html


def generate_coaching_comment(activity, feedback, profile, activities, cardiac_analysis=None):
    """
    🆕 Génère un commentaire de coaching IA avec HTML structuré et contexte moyennes 10 derniers.
    Utilise UNIQUEMENT les métriques déjà calculées dans activity.
    """
    # Charger le prompt template v3 (simplifié sans gros exemple HTML)
    prompt_template = load_prompt("coaching_run_v3")
    if not prompt_template:
        return "⚠️ Template de prompt coaching introuvable."

    # Classifier le run actuel
    run_type = classify_run_type(activity)

    # Charger the weekly plan pour récupérer les objectifs planifiés
    # Extraire la date au format YYYY-MM-DD depuis le champ 'date' (ISO format)
    run_date_iso = activity.get('date', '')
    run_date_str = None
    planned_run = None
    weekly_plan = None  # Initialiser pour utilisation ultérieure

    if run_date_iso:
        try:
            # Parse ISO format (ex: "2026-01-02T11:19:03Z") et extraire YYYY-MM-DD
            run_date = datetime.strptime(run_date_iso[:10], '%Y-%m-%d')
            run_date_str = run_date_iso[:10]  # "2026-01-02"
            week_num = run_date.isocalendar()[1]
            print(f"📅 Chargement weekly plan pour semaine {week_num} (date: {run_date_str})")
            weekly_plan = read_weekly_plan(week_num)

            if weekly_plan and 'runs' in weekly_plan:
                print(f"✅ Weekly plan trouvé avec {len(weekly_plan.get('runs', []))} runs")

                # 1. D'abord essayer de matcher par date exacte
                for planned in weekly_plan['runs']:
                    if planned.get('day_date') == run_date_str:
                        planned_run = planned
                        print(f"🎯 Objectifs planifiés trouvés par DATE pour {run_date_str}: {planned.get('type_display')}")
                        break

                # 2. Si pas de match par date, matcher par TYPE de run
                if not planned_run:
                    # Mapping des types pour la correspondance
                    type_mapping = {
                        'recuperation': ['recuperation', 'tempo_recup', 'recovery'],
                        'tempo_recup': ['recuperation', 'tempo_recup', 'recovery'],
                        'endurance': ['endurance', 'tempo_leger'],
                        'tempo_leger': ['endurance', 'tempo_leger'],
                        'tempo_rapide': ['tempo_rapide', 'tempo', 'threshold'],
                        'long_run': ['long_run', 'sortie_longue'],
                        'fractionne': ['fractionne', 'interval', 'vma']
                    }

                    run_type_lower = run_type.lower() if run_type else ''
                    possible_types = type_mapping.get(run_type_lower, [run_type_lower])

                    for planned in weekly_plan['runs']:
                        planned_type = planned.get('type', '').lower()
                        if planned_type in possible_types or run_type_lower in planned_type:
                            planned_run = planned
                            print(f"🎯 Objectifs planifiés trouvés par TYPE ({run_type} → {planned_type}): {planned.get('type_display')}")
                            break

                # 3. Si toujours pas de match, prendre le premier run non encore passé
                if not planned_run and weekly_plan['runs']:
                    planned_run = weekly_plan['runs'][0]
                    print(f"🎯 Objectifs planifiés par défaut (1er run): {planned_run.get('type_display')}")

                if not planned_run:
                    print(f"⚠️ Aucun run planifié trouvé dans le programme")
            else:
                print(f"⚠️ Weekly plan semaine {week_num} vide ou invalide")
        except Exception as e:
            print(f"❌ Erreur chargement weekly plan: {e}")

    # Calculer moyennes par type (10 derniers de chaque type)
    type_averages = {}
    for rt in ['tempo_recup', 'tempo_rapide', 'endurance', 'long_run']:
        avg = calculate_type_averages(activities, rt, limit=10)
        type_averages[rt] = avg

    # Formater les moyennes pour le prompt
    def format_avg(avg_dict):
        if avg_dict['count'] == 0:
            return "Aucune donnée disponible"

        allure_str = f"{int(avg_dict['allure_moy'])}:{int((avg_dict['allure_moy'] % 1) * 60):02d}/km" if avg_dict['allure_moy'] else "N/D"
        k_str = f"{avg_dict['k_moy']:.2f}" if avg_dict['k_moy'] else "N/D"
        drift_str = f"{avg_dict['drift_moy']:.1f}%" if avg_dict['drift_moy'] is not None else "N/D"
        cadence_str = f"{avg_dict['cadence_moy']:.0f} SPM" if avg_dict['cadence_moy'] else "N/D"
        fc_str = f"{avg_dict['fc_moy']:.0f} bpm" if avg_dict['fc_moy'] else "N/D"
        zones_str = ", ".join([f"Z{z}: {avg_dict['zones_fc'].get(z, 0):.1f}%" for z in range(1, 6)])

        return f"Allure: {allure_str}, k: {k_str}, Drift: {drift_str}, Cadence: {cadence_str}, FC: {fc_str}, Zones: {zones_str}, Count: {avg_dict['count']}"

    moyennes_text = f"""
Moyennes 10 derniers RÉCUPÉRATION: {format_avg(type_averages['tempo_recup'])}
Moyennes 10 derniers TEMPO: {format_avg(type_averages['tempo_rapide'])}
Moyennes 10 derniers ENDURANCE: {format_avg(type_averages['endurance'])}
Moyennes 10 derniers LONG RUN: {format_avg(type_averages['long_run'])}
"""

    # Données du run actuel - UNIQUEMENT ce qui existe déjà
    allure_actuel = activity.get('allure', 'N/D')
    k_actuel = f"{activity.get('k_moy', 0):.2f}" if activity.get('k_moy') and activity.get('k_moy') != "-" else "N/D"
    drift_actuel = f"{activity.get('deriv_cardio', 0):.1f}%" if activity.get('deriv_cardio') is not None and activity.get('deriv_cardio') != "-" else "N/D"
    cadence_actuel = f"{activity.get('cadence_spm') or activity.get('cad_mean_spm', 0):.0f} SPM" if (activity.get('cadence_spm') or activity.get('cad_mean_spm')) and (activity.get('cadence_spm') or activity.get('cad_mean_spm')) != "-" else "N/D"
    fc_actuel = f"{activity.get('fc_moy', 0):.0f} bpm" if activity.get('fc_moy') and activity.get('fc_moy') != "-" else "N/D"
    distance_actuel = f"{activity.get('distance_km', 0):.2f} km"

    # Zones FC actuelles
    zones_actuel_str = "N/D"
    if cardiac_analysis and 'hr_zones' in cardiac_analysis:
        zone_pcts = cardiac_analysis['hr_zones'].get('zone_percentages', {})
        zones_actuel_str = ", ".join([f"Z{z}: {zone_pcts.get(z, 0):.1f}%" for z in range(1, 6)])

    # Ressenti
    mode_run = feedback.get('mode_run', 'training')
    is_last_run_of_week = feedback.get('is_last_run_of_week', False)
    rating = feedback.get('rating_stars', 3)
    difficulty = feedback.get('difficulty', 3)
    legs = feedback.get('legs_feeling', 'normal')
    cardio = feedback.get('cardio_feeling', 'moderate')
    notes = feedback.get('notes', '').strip()

    # Si dernier run de la semaine, générer le bilan hebdomadaire
    week_summary = ""
    current_week = 0
    next_week = 1

    print(f"🔍 is_last_run_of_week = {is_last_run_of_week}, activities count = {len(activities) if activities else 0}")
    if is_last_run_of_week and activities and run_date_iso:
        print(f"✅ Génération du bilan de semaine activée")
        try:
            current_date = datetime.strptime(run_date_iso[:19], '%Y-%m-%dT%H:%M:%S')
            current_week = current_date.isocalendar()[1]
            current_year = current_date.isocalendar()[0]

            # Récupérer tous les runs de la semaine
            week_runs = []
            for act in activities:
                act_date_str = act.get('date', '')
                if act_date_str:
                    try:
                        act_date = datetime.strptime(act_date_str[:19], '%Y-%m-%dT%H:%M:%S')
                        act_week = act_date.isocalendar()[1]
                        act_year = act_date.isocalendar()[0]
                        if act_week == current_week and act_year == current_year:
                            week_runs.append(act)
                    except ValueError:
                        pass

            # Trier par date
            week_runs.sort(key=lambda x: x.get('date', ''))

            # Générer le dossier d'analyse structuré pour l'IA
            if week_runs:
                # Charger les données nécessaires
                weekly_plan_current = read_weekly_plan(current_week)
                week_objectives = read_weekly_objectives(current_week)
                all_feedbacks = load_feedbacks()

                # Générer le dossier d'analyse complet
                import json
                dossier = generer_dossier_analyse(
                    week_runs=week_runs,
                    weekly_plan=weekly_plan_current,
                    week_objectives=week_objectives,
                    current_week=current_week,
                    feedbacks=all_feedbacks
                )

                print(f"📊 Dossier analyse généré: volume {dossier['volume']['taux_completion']}%, "
                      f"k={dossier['efficacite']['k_moyen_realise']}, "
                      f"tendance ressenti: {dossier['signaux_textuels']['tendance_ressenti']}")

                # Sauvegarder le k et drift réalisés pour le suivi des tendances
                if week_objectives:
                    week_objectives['k_realise'] = dossier['efficacite']['k_moyen_realise']
                    week_objectives['drift_realise'] = dossier['efficacite']['drift_moyen_realise']
                    write_weekly_objectives(current_week, week_objectives)

                # Formatter le dossier en texte structuré pour l'IA
                week_summary = f"""

=== DOSSIER D'ANALYSE SEMAINE {current_week} ===

📊 VOLUME:
  Programme: {dossier['volume']['programme_km']} km
  Réalisé: {dossier['volume']['realise_km']} km
  Taux complétion programme: {dossier['volume']['taux_completion']}%
  Objectif: {dossier['volume']['objectif_km']} km
  Taux vs objectif: {dossier['volume']['taux_vs_objectif']}%

⚡ EFFICACITÉ:
  k moyen réalisé: {dossier['efficacite']['k_moyen_realise']}
  k objectif: {dossier['efficacite']['k_objectif'] or 'non défini'}
  k tendance 3 semaines: {dossier['efficacite']['k_tendance_3sem']}
  Drift moyen réalisé: {dossier['efficacite']['drift_moyen_realise']}%
  Drift objectif: {dossier['efficacite']['drift_objectif'] or 'non défini'}%
  Drift tendance 3 semaines: {dossier['efficacite']['drift_tendance_3sem']}

📋 QUALITÉ SÉANCES:
  Programmées: {dossier['qualite_seances']['programmees']}
  Complétées: {dossier['qualite_seances']['completees']}
  Taux complétion: {dossier['qualite_seances']['taux_completion']}%

💬 SIGNAUX TEXTUELS (notes des séances):
  Notes: {'; '.join(dossier['signaux_textuels']['notes_seances']) if dossier['signaux_textuels']['notes_seances'] else 'Aucune note'}
  Mots d'alerte détectés: {', '.join(dossier['signaux_textuels']['alertes_detectees']) if dossier['signaux_textuels']['alertes_detectees'] else 'Aucun'}
  Mots positifs détectés: {', '.join(dossier['signaux_textuels']['positifs_detectes']) if dossier['signaux_textuels']['positifs_detectes'] else 'Aucun'}
  Tendance ressenti: {dossier['signaux_textuels']['tendance_ressenti']} (score: {dossier['signaux_textuels']['score_ressenti']})

"""
        except Exception as e:
            week_summary = f"\n[Erreur génération dossier analyse: {e}]\n"
            print(f"❌ Erreur dossier analyse: {e}")
            import traceback
            traceback.print_exc()

    # Calculer le numéro de la semaine suivante
    if current_week > 0:
        next_week = current_week + 1
        if next_week > 52:
            next_week = 1

    # Formatter les objectifs planifiés si disponibles
    planned_objectives_text = ""

    # Récupérer l'objectif final (semi-marathon) depuis le weekly plan
    final_objective_text = ""
    if weekly_plan and 'summary' in weekly_plan and 'objective' in weekly_plan['summary']:
        obj = weekly_plan['summary']['objective']
        final_objective_text = f"""
=== OBJECTIF FINAL ===
Type: {obj.get('type', 'semi_marathon')}
Temps cible: {obj.get('target_time', '1:45:00')}
Allure cible: {obj.get('target_pace', '4:58')}/km
Distance: {obj.get('target_distance', 21.1)} km
"""

    if planned_run:
        planned_objectives_text = f"""
=== OBJECTIFS CE RUN (Programme Semaine) ===
Type prévu: {planned_run.get('type_display', 'N/D')}
Distance cible: {planned_run.get('distance_km', 'N/D')} km
Allure cible: {planned_run.get('pace_target', 'N/D')}
FC cible: {planned_run.get('fc_target', 'N/D')}
k cible: {planned_run.get('k_target', 'N/D')}
Drift max: {planned_run.get('drift_target', 'N/D')}%
Zones cibles: {', '.join([f'Z{z}' for z in planned_run.get('zones_target', [])]) if planned_run.get('zones_target') else 'N/D'}
Notes coach: {planned_run.get('notes', 'N/D')}
{final_objective_text}
⚠️ COMPARE LE RUN ACTUEL AVEC CES OBJECTIFS DANS TON ANALYSE"""

    # Formatter les données pour le prompt
    data_text = f"""
=== RUN ACTUEL ===
Type: {run_type} | Mode: {mode_run} | Dernier de la semaine: {"OUI" if is_last_run_of_week else "NON"}
Distance: {distance_actuel} | Allure: {allure_actuel}
k: {k_actuel} | Drift: {drift_actuel} | Cadence: {cadence_actuel} | FC: {fc_actuel}
Zones FC: {zones_actuel_str}
Ressenti: Note {rating}/5, Difficulté {difficulty}/5, Jambes: {legs}, Cardio: {cardio}
Notes: {notes if notes else "Aucune"}

=== MOYENNES 10 DERNIERS ===
{moyennes_text}
{planned_objectives_text}
{week_summary}
=== PROGRAMME SEMAINE SUIVANTE ===
Numéro de semaine à afficher: {next_week}
(Si dernier run de la semaine, génère le programme ET les objectifs de la semaine {next_week})
"""

    # Remplacer {data} dans le prompt
    final_prompt = prompt_template.replace("{data}", data_text)

    # Appel API Gemini 2.0
    if not gemini_client:
        return "⚠️ Service IA temporairement indisponible"

    try:
        # Augmenter max_output_tokens si dernier run de la semaine (bilan + programme semaine suivante)
        max_tokens = 3000 if is_last_run_of_week else 1200

        response = gemini_client.models.generate_content(
            model='gemini-2.0-flash',
            contents=final_prompt,
            config={
                'max_output_tokens': max_tokens,
                'temperature': 0.3
            }
        )
        # Gemini génère directement le HTML structuré
        ai_comment = response.text.strip()

        # 🧹 Nettoyer les balises markdown si présentes
        if ai_comment.startswith('```html'):
            ai_comment = ai_comment[7:]  # Enlever ```html
        if ai_comment.startswith('```'):
            ai_comment = ai_comment[3:]  # Enlever ```
        if ai_comment.endswith('```'):
            ai_comment = ai_comment[:-3]  # Enlever ``` final
        ai_comment = ai_comment.strip()

        # 🧹 Vérifier et corriger les balises HTML non fermées
        open_divs = ai_comment.count('<div')
        close_divs = ai_comment.count('</div>')
        if open_divs > close_divs:
            ai_comment += '</div>' * (open_divs - close_divs)
            print(f"⚠️ Ajouté {open_divs - close_divs} </div> manquant(s)")

        # 🆕 Si PAS le dernier run de la semaine, ajouter les runs restants du programme
        if not is_last_run_of_week and weekly_plan and 'runs' in weekly_plan:
            remaining_runs_html = generate_remaining_runs_html(weekly_plan, planned_run, activities, run_date_iso)
            if remaining_runs_html:
                ai_comment += remaining_runs_html

        return ai_comment
    except Exception as e:
        print(f"❌ Erreur génération coaching IA: {e}")
        return f"⚠️ Erreur génération: {str(e)}"




print("✅ Helpers OK")

# -------------------
# 👟 Calcul kilométrage chaussures
# -------------------
def calculate_shoe_kilometers(activities, profile):
    """
    Calcule le kilométrage total parcouru depuis la date d'achat des chaussures.

    Args:
        activities: Liste des activités
        profile: Profil utilisateur avec shoes_purchase_date

    Returns:
        tuple: (total_km, status)
            - total_km: Kilométrage total (float)
            - status: 'ok' (<600km), 'warning' (600-800km), 'danger' (>800km), 'unknown' (pas de date)
    """
    shoes_date_str = profile.get('shoes_purchase_date', '')
    print(f"👟 DEBUG: shoes_purchase_date = {shoes_date_str}")
    print(f"👟 DEBUG: profile keys = {list(profile.keys())}")

    if not shoes_date_str:
        print("👟 DEBUG: Pas de shoes_purchase_date trouvé")
        return (0.0, 'unknown')

    try:
        # Parser la date d'achat des chaussures (format: YYYY-MM-DD)
        shoes_date = datetime.strptime(shoes_date_str, '%Y-%m-%d')

        total_km = 0.0

        for act in activities:
            # Récupérer la date de l'activité
            act_date_str = act.get('date', '')
            if not act_date_str:
                continue

            # Parser la date de l'activité (format ISO: YYYY-MM-DDTHH:MM:SSZ)
            try:
                act_date = datetime.fromisoformat(act_date_str.replace('Z', '+00:00'))
            except ValueError:
                # Fallback: essayer sans timezone
                try:
                    act_date = datetime.strptime(act_date_str.split('T')[0], '%Y-%m-%d')
                except ValueError:
                    continue

            # Si l'activité est après l'achat des chaussures
            if act_date.date() >= shoes_date.date():
                # Essayer d'obtenir la distance
                distance_m = act.get('distance', 0) or 0

                # Si pas de distance, essayer d'obtenir depuis les points
                if not distance_m:
                    points = act.get('points', [])
                    if points and len(points) > 0:
                        # La distance totale est dans le dernier point
                        last_point = points[-1]
                        distance_m = last_point.get('distance', 0) or 0

                total_km += distance_m / 1000.0

        # Déterminer le statut d'usure
        if total_km < 600:
            status = 'ok'
        elif total_km <= 800:
            status = 'warning'
        else:
            status = 'danger'

        return (round(total_km, 1), status)

    except Exception as e:
        print(f"⚠️ Erreur calcul km chaussures: {e}")
        return (0.0, 'unknown')


# -------------------
# Fonction météo (Open-Meteo)
# -------------------

from collections import Counter

def get_temperature_for_run(lat, lon, start_datetime_str, duration_minutes):
    try:
        # ✅ Parse ISO 8601 (Z ou +02:00)
        start_dt = parser.isoparse(start_datetime_str)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # ✅ Supprime le fuseau pour comparer avec les données naïves de l'API
        start_dt = start_dt.replace(tzinfo=None)
        end_dt = end_dt.replace(tzinfo=None)

        print(f"🕒 Heure début (start_dt): {start_dt}, fin (end_dt): {end_dt}")
    except Exception as e:
        print("❌ Erreur parsing datetime pour météo:", e, start_datetime_str)
        return None, None, None, None

    today = date.today()
    yesterday = today - timedelta(days=1)
    is_today = start_dt.date() == today
    is_yesterday = start_dt.date() == yesterday

   # ✅ Utilise forecast pour aujourd'hui et hier
    if is_today or is_yesterday:
        query_type = "forecast"
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,weathercode"
            f"&timezone=auto"
        )
    else:
        query_type = "archive"
        # Archive pour avant-hier et plus
        date_str = start_dt.strftime("%Y-%m-%d")
        url = (
            f"https://archive-api.open-meteo.com/v1/archive?"
            f"latitude={lat}&longitude={lon}"
            f"&start_date={date_str}&end_date={date_str}"
            f"&hourly=temperature_2m,weathercode"
            f"&timezone=auto"
        )

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        hours = data.get("hourly", {}).get("time", [])
        temps = data.get("hourly", {}).get("temperature_2m", [])
        weathercodes = data.get("hourly", {}).get("weathercode", [])

        if not hours or not temps:
            print("⚠️ Aucune donnée horaire trouvée.")
            return None, None, None, None

        # Convertit toutes les heures en datetime (naïves) pour comparaison
        hours_dt = [datetime.fromisoformat(h) for h in hours]

        # Trouver la température la plus proche pour début et fin
        def closest_temp(target_dt):
            diffs = [abs((dt - target_dt).total_seconds()) for dt in hours_dt]
            idx = diffs.index(min(diffs))
            return temps[idx] if temps[idx] is not None else None

        temp_debut = closest_temp(start_dt)
        temp_fin = closest_temp(end_dt)

        # Moyenne sur la fenêtre de course
        temp_values = [
            temp for dt, temp in zip(hours_dt, temps)
            if start_dt <= dt <= end_dt and temp is not None
        ]

        # ✅ Si pas de moyenne, utiliser au moins temp_debut ou temp_fin
        avg_temp = (
            round(sum(temp_values) / len(temp_values), 1)
            if temp_values else temp_debut or temp_fin
        )

        # Code météo le plus fréquent pendant la course
# ✅ Trouver le code météo dominant avec une marge de 30 min

        margin = timedelta(minutes=30)
        weather_in_window = [
            wc for dt, wc in zip(hours_dt, weathercodes)
            if (start_dt - margin) <= dt <= (end_dt + margin) and wc is not None
        ]

        if weather_in_window:
            # Si on a trouvé des codes météo dans la fenêtre élargie, on prend le plus fréquent
            most_common_code = Counter(weather_in_window).most_common(1)[0][0]
        else:
            # Sinon, on prend le code météo le plus proche du début de la course
            diffs = [abs((dt - start_dt).total_seconds()) for dt in hours_dt]
            most_common_code = weathercodes[diffs.index(min(diffs))] if diffs else None

        return avg_temp, temp_debut, temp_fin, most_common_code

    except Exception as e:
        print("❌ Erreur lors de la requête ou du traitement météo:", e)
        return None, None, None, None



# -------------------
# Loaders (Drive-only via helpers.data_access)
# -------------------
# Cache simple pour le profil (réinitialis é à chaque redémarrage worker)
_profile_cache = {'data': None, 'timestamp': 0}
_PROFILE_CACHE_TTL = 60  # secondes

def invalidate_profile_cache():
    """Invalide le cache du profil après modification"""
    _profile_cache['data'] = None
    _profile_cache['timestamp'] = 0

def load_profile():
    """Charge le profil avec cache de 60 secondes"""
    current_time = time.time()

    # Vérifier le cache
    if _profile_cache['data'] and (current_time - _profile_cache['timestamp']) < _PROFILE_CACHE_TTL:
        return _profile_cache['data']

    # Charger depuis Drive
    try:
        profile = load_profile_from_drive()
        _profile_cache['data'] = profile
        _profile_cache['timestamp'] = current_time
        return profile
    except DriveUnavailableError:
        return {"birth_date": "", "weight": 0, "events": []}

def load_feedbacks():
    """Charge les feedbacks depuis outputs/run_feedbacks.json"""
    try:
        feedbacks = read_output_json('run_feedbacks.json') or {}
        print(f"✅ {len(feedbacks)} feedbacks chargés")
        return feedbacks
    except Exception as e:
        print(f"⚠️ Erreur chargement feedbacks: {e}")
        return {}

def calculate_personalized_targets(profile, activities):
    """
    Calcule les objectifs personnalisés de k et drift basés sur :
    - 60% données historiques (P75 des meilleurs runs par type)
    - 40% formules scientifiques (FC max Tanaka, drift selon âge)

    Args:
        profile: Dict profil utilisateur (age, poids, objectifs)
        activities: Liste des activités avec k_moy et deriv_cardio

    Returns:
        Dict avec objectifs par type de séance :
        {
            'endurance': {'k_target': 1.14, 'drift_target': 1.04},
            'tempo': {'k_target': 0.95, 'drift_target': 1.08},
            'fractionné': {'k_target': 0.85, 'drift_target': 1.12}
        }
    """
    # Calculer l'âge
    birth_date_str = profile.get('birth_date', '')
    if birth_date_str:
        birth_year = int(birth_date_str[:4])
        age = datetime.now().year - birth_year
    else:
        age = 50  # Valeur par défaut

    # FC max selon Tanaka (plus précise que 220-age)
    fc_max = 208 - (0.7 * age)

    # Objectifs théoriques selon la science
    # Dérive cardiaque théorique selon formule : -0.0514 + (0.0240 × %FCmax) - (0.0172 × age)
    # Homme = 0, donc on ignore le terme sexe
    def theoretical_drift(fc_percentage):
        """Calcule drift théorique pour un % de FC max donné"""
        # Cette formule donne le drift en bpm/min
        drift_rate = -0.0514 + (0.0240 * fc_percentage) - (0.0172 * age)
        # Sur 30 min de run, conversion en ratio
        # Un run de 30 min avec drift_rate bpm/min = augmentation totale
        # drift ratio = (FC_fin / FC_début) approximé par 1 + (drift_total / FC_moyenne)
        drift_total_bpm = drift_rate * 30
        fc_moyenne = fc_max * (fc_percentage / 100)
        drift_ratio = 1 + (drift_total_bpm / fc_moyenne) if fc_moyenne > 0 else 1.0
        return max(1.0, drift_ratio)  # Au minimum 1.0

    # k théorique : dépend de l'intensité (plus c'est intense, plus k baisse)
    # Formule empirique basée sur Heart Rate Pace Factor
    def theoretical_k(fc_percentage):
        """k diminue avec l'intensité"""
        # À 65% FCmax (endurance) : k élevé (~1.2)
        # À 85% FCmax (tempo) : k moyen (~0.95)
        # À 95% FCmax (fractionné) : k faible (~0.75)
        base_k = 2.0 - (fc_percentage / 100) * 1.5
        return max(0.5, base_k)

    # Types de séances et leurs intensités FC typiques
    session_types_config = {
        'endurance': {'fc_pct': 65, 'min_runs': 5},
        'tempo': {'fc_pct': 80, 'min_runs': 3},
        'fractionné': {'fc_pct': 90, 'min_runs': 3}
    }

    targets = {}

    for session_type, config in session_types_config.items():
        # Mapper les types réels vers endurance/tempo/fractionné
        def matches_session_type(act):
            """Détermine si une activité correspond au type de séance"""
            type_sortie = act.get('type_sortie', '')
            is_fractionne = act.get('is_fractionne', False)

            if session_type == 'fractionné':
                return is_fractionne is True
            elif session_type == 'endurance':
                # Long runs = endurance
                return type_sortie == 'long_run' and not is_fractionne
            elif session_type == 'tempo':
                # Runs normaux (5k/10k) non fractionnés = tempo
                return type_sortie in ['normal_5k', 'normal_10k'] and not is_fractionne
            return False

        # Filtrer les runs de ce type avec données valides
        type_runs = [
            act for act in activities
            if matches_session_type(act)
            and isinstance(act.get('k_moy'), (int, float))
            and isinstance(act.get('deriv_cardio'), (int, float))
        ]

        # Objectifs théoriques
        k_theo = theoretical_k(config['fc_pct'])
        drift_theo = theoretical_drift(config['fc_pct'])

        if len(type_runs) >= config['min_runs']:
            # Assez de données : mix historique (60%) + théorie (40%)
            # Prendre les meilleurs (P75 = top 25%)
            k_values = sorted([act['k_moy'] for act in type_runs])
            drift_values = sorted([act['deriv_cardio'] for act in type_runs])

            p75_index = int(len(k_values) * 0.75)
            k_historical = np.median(k_values[p75_index:]) if p75_index < len(k_values) else np.median(k_values)

            # Pour drift, on veut les meilleurs (plus bas)
            p25_index = int(len(drift_values) * 0.25)
            drift_historical = np.median(drift_values[:p25_index+1]) if p25_index > 0 else np.median(drift_values)

            # Mix 60/40
            k_target = 0.6 * k_historical + 0.4 * k_theo
            drift_target = 0.6 * drift_historical + 0.4 * drift_theo
        else:
            # Pas assez de données : 100% théorique
            k_target = k_theo
            drift_target = drift_theo

        targets[session_type] = {
            'k_target': round(k_target, 2),
            'drift_target': round(drift_target, 2),
            'fc_max': round(fc_max, 0),
            'sample_size': len(type_runs)
        }

    return targets

# -------------------
# Fonctions spécifiques (inchangées sauf enrich_activities etc)
# -------------------
def get_fcmax_from_fractionnes(activities):
    fcmax = 0
    for act in activities:
        if act.get("type_sortie") == "fractionné" or act.get("is_fractionne") is True:
            for point in act.get("points", []):
                hr = point.get("hr")
                if hr is not None and hr > fcmax:
                    fcmax = hr
    return fcmax

def _compute_denivele_pos(points):
    """Dénivelé positif cumulé (D+) en mètres : somme des hausses d'altitude."""
    if not points:
        return 0.0
    alts = np.array([p.get("alt", 0) for p in points], dtype=float)
    delta = np.diff(alts, prepend=alts[0])
    denivele = float(np.sum(delta[delta > 0]))
    return round(denivele, 1)


def enrich_single_activity(activity, fc_max_fractionnes):
    points = activity.get("points", [])
    if not points or len(points) < 5:
        return activity

    distances = np.array([p["distance"]/1000 for p in points])
    fcs = np.array([p.get("hr") if p.get("hr") is not None else np.nan for p in points])
    vels = np.array([p.get("vel", 0) for p in points])
    alts = np.array([p.get("alt", 0) for p in points])

    delta_dist = np.diff(distances, prepend=distances[0]) * 1000
    delta_alt = np.diff(alts, prepend=alts[0])
    delta_dist[delta_dist == 0] = 0.001

    pentes = (delta_alt / delta_dist) * 100
    allures_brutes = np.where(vels > 0, (1 / vels) * 16.6667, np.nan)
    allures_corrigees = np.where((allures_brutes - 0.2 * pentes) < 0, np.nan, allures_brutes - 0.2 * pentes)

    ratios = np.where(allures_corrigees > 0, fcs / allures_corrigees, np.nan)
    valid = (~np.isnan(allures_corrigees)) & (~np.isnan(fcs))

    # Extraire aussi les temps pour le calcul temporel de la dérive
    times = np.array([p.get("time", 0) for p in points])
    times = times[valid]
    distances, fcs, allures_corrigees, ratios, vels = distances[valid], fcs[valid], allures_corrigees[valid], ratios[valid], vels[valid]

    if len(distances) < 5:
        return activity

    # Données complètes pour les courbes (pas de skip)
    times_full = times.copy()
    distances_full = distances.copy()
    fcs_full = fcs.copy()
    allures_corrigees_full = allures_corrigees.copy()
    ratios_full = ratios.copy()
    vels_full = vels.copy()

    # ========== NOUVEAU: Exclure les 5 premières MINUTES (pas mètres) ==========
    time_start = times[0]
    skip_time_sec = 300  # 5 minutes = 300 secondes
    mask_after_5min = (times - time_start) >= skip_time_sec

    times_analysis = times[mask_after_5min]
    distances_analysis = distances[mask_after_5min]
    fcs_analysis = fcs[mask_after_5min]
    allures_corrigees_analysis = allures_corrigees[mask_after_5min]
    ratios_analysis = ratios[mask_after_5min]
    vels_analysis = vels[mask_after_5min]

    if len(times_analysis) < 5:
        # Pas assez de données après 5 min, fallback sur 300m
        skip_distance_km = 0.3
        mask_after_300m = distances >= skip_distance_km
        times_analysis = times[mask_after_300m]
        distances_analysis = distances[mask_after_300m]
        fcs_analysis = fcs[mask_after_300m]
        allures_corrigees_analysis = allures_corrigees[mask_after_300m]
        ratios_analysis = ratios[mask_after_300m]
        vels_analysis = vels[mask_after_300m]

    total_duration = points[-1]["time"] - points[0]["time"]
    slope, _ = np.polyfit(distances_analysis, ratios_analysis, 1)
    r_squared = np.corrcoef(distances_analysis, ratios_analysis)[0,1]**2
    collapse_threshold = np.mean(allures_corrigees_analysis[:max(1,len(allures_corrigees_analysis)//3)]) * 1.10
    collapse_distance = next((d for a, d in zip(allures_corrigees_analysis, distances_analysis) if a > collapse_threshold), distances_analysis[-1] if len(distances_analysis) > 0 else 0)
    cv_allure = np.std(allures_corrigees_analysis) / np.mean(allures_corrigees_analysis)
    cv_cardio = np.std(ratios_analysis) / np.mean(ratios_analysis)
    seuil_90 = 0.9 * fc_max_fractionnes
    above_90_count = sum(1 for hr in fcs_full if hr > seuil_90)  # Sur données complètes
    time_above_90 = (above_90_count / len(fcs_full)) * total_duration if len(fcs_full) else 0
    split = max(1, len(allures_corrigees_analysis)//3)
    endurance_index = np.mean(allures_corrigees_analysis[-split:]) / np.mean(allures_corrigees_analysis[:split])
    fc_moy, allure_moy = np.mean(fcs_analysis), np.mean(allures_corrigees_analysis)
    k_moy = 0.43 * (fc_moy / allure_moy) - 5.19 if allure_moy > 0 else "-"

    # ========== NOUVEAU CALCUL DÉRIVE CARDIAQUE ==========
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
                deriv_cardio = round(deriv_cardio_pct, 1)  # Arrondi à 0,1%
    seuil_bas, seuil_haut = 0.6 * fc_max_fractionnes, 0.7 * fc_max_fractionnes
    zone2_count = sum(1 for hr in fcs_full if seuil_bas < hr < seuil_haut)  # Sur données complètes
    pourcentage_zone2 = (zone2_count / len(fcs_full)) * 100 if len(fcs_full) else 0
    ratio_fc_allure_global = np.mean(ratios_analysis)  # Sur données après 300m
    gain_alt = _compute_denivele_pos(points)

    # 🆕 Calculer distance et allure pour l'activité
    total_dist_km = points[-1].get("distance", 0) / 1000.0
    total_time_min = (points[-1].get("time", 0) - points[0].get("time", 0)) / 60.0
    allure_moy = total_time_min / total_dist_km if total_dist_km > 0 else None
    allure_formatted = f"{int(allure_moy)}:{int((allure_moy - int(allure_moy)) * 60):02d}" if allure_moy else "-"

    activity.update({
        "drift_slope": round(slope, 4),
        "drift_r2": round(r_squared, 4),
        "collapse_distance_km": round(collapse_distance, 2),
        "cv_allure": round(cv_allure, 4),
        "cv_cardio": round(cv_cardio, 4),
        "time_above_90_pct_fcmax": round(time_above_90, 1),
        "endurance_index": round(endurance_index, 4),
        "k_moy": round(k_moy, 3) if isinstance(k_moy, float) else "-",
        "deriv_cardio": round(deriv_cardio, 1) if isinstance(deriv_cardio, (int, float)) else "-",
        "pourcentage_zone2": round(pourcentage_zone2, 1),
        "ratio_fc_allure_global": round(ratio_fc_allure_global, 3),
        "gain_alt": gain_alt,
        "distance_km": round(total_dist_km, 2),  # 🆕 Ajouter distance
        "allure": allure_formatted,  # 🆕 Ajouter allure formatée
    })

    return activity
    
def normalize_cadence_in_place(activities):
    """
    Convertit une cadence brute (cad_raw / cadence / cad) en 'cad_spm' (steps/min, deux pieds).
    - Aucun appel réseau
    - Heuristique one-foot: médiane < 120 => x2
    - N'écrase pas si 'cad_spm' existe déjà
    Retourne (activities, modified:bool)
    """
    modified = False
    for act in activities or []:
        pts = act.get("points") or []
        if not pts:
            continue

        # Si déjà normalisé quelque part, on ne touche à rien
        if any(isinstance(p.get("cad_spm"), (int, float)) for p in pts):
            continue

        # Série brute par point (ordre de priorité)
        raw = []
        for p in pts:
            v = (p.get("cad_raw") if p.get("cad_raw") is not None else
                 p.get("cadence")  if p.get("cadence")  is not None else
                 p.get("cad")      if p.get("cad")      is not None else
                 None)
            raw.append(v)

        vals = [v for v in raw if isinstance(v, (int, float))]
        if not vals:
            # pas de cadence dispo
            act.setdefault("cadence_meta", {
                "present": False, "units": "spm", "source": "none",
                "coverage_pct": 0.0, "normalized": False, "one_foot_detected": False
            })
            continue

        # Détection "one-foot"
        median_val = sorted(vals)[len(vals)//2]
        one_foot = median_val < 120.0
        factor = 2.0 if one_foot else 1.0

        filled = 0
        for i, p in enumerate(pts):
            v = raw[i]
            if isinstance(v, (int, float)):
                p["cad_spm"] = float(v) * factor
                filled += 1
            else:
                p.setdefault("cad_spm", None)

        act["cadence_meta"] = {
            "present": True, "units": "spm", "source": "stream|raw",
            "coverage_pct": round(100.0*filled/max(1,len(pts)), 1),
            "normalized": bool(factor == 2.0),
            "one_foot_detected": bool(one_foot),
        }
        modified = True

    return activities, modified


def _cadence_kpis(points):
    """
    KPIs de cadence à partir de 'cad_spm' :
      - cad_mean_spm (moyenne, spm)
      - cad_cv_pct   (coefficient de variation, %)
      - cad_drift_spm_per_h (pente vs temps, spm/heure)
    Renvoie des '-' si données insuffisantes.
    """
    if not points:
        return {"cad_mean_spm": "-", "cad_cv_pct": "-", "cad_drift_spm_per_h": "-"}

    vals, times = [], []
    t0 = None
    for p in points:
        c = p.get("cad_spm")
        t = p.get("time")
        if isinstance(c, (int, float)) and isinstance(t, (int, float)):
            vals.append(float(c))
            if t0 is None:
                t0 = t
            times.append(float(t - t0))

    if len(vals) < 20:
        return {"cad_mean_spm": "-", "cad_cv_pct": "-", "cad_drift_spm_per_h": "-"}

    v = np.array(vals, dtype=float)
    m = float(np.nanmean(v))
    s = float(np.nanstd(v))
    cv_pct = round((s / m) * 100.0, 1) if m > 0 else None

    t = np.array(times, dtype=float)
    if np.nanvar(t) > 0 and len(t) == len(v):
        slope_per_sec = float(np.polyfit(t, v, 1)[0])
        drift_spm_per_h = round(slope_per_sec * 3600.0, 2)
    else:
        drift_spm_per_h = None

    return {
        "cad_mean_spm": round(m, 1),
        "cad_cv_pct": cv_pct if cv_pct is not None else "-",
        "cad_drift_spm_per_h": drift_spm_per_h if drift_spm_per_h is not None else "-"
    }


def enrich_activities(activities, profile=None):
    fc_max_fractionnes = get_fcmax_from_fractionnes(activities)
    print(f"📈 FC max fractionnés: {fc_max_fractionnes}")

    for idx, activity in enumerate(activities):
        # 1) Assigner le type de séance si manquant/forcé (règles simples par distance)
        if activity.get("type_sortie") in (None, "-", "inconnue") or activity.get("force_recompute", False):
            activity["type_sortie"] = classify_run_type(activity)

        # 2) Enrichissements numériques (k, dérive cardio, etc.)
        activity = enrich_single_activity(activity, fc_max_fractionnes)

        # 3) Recalculer cardiac_analysis avec les valeurs actuelles du profil (hr_rest, hr_max)
        # TOUJOURS recalculer pour tenir compte des changements du profil
        if profile:
            cardiac_analysis = analyze_cardiac_health(activity, profile)
            if cardiac_analysis:
                activity['cardiac_analysis'] = cardiac_analysis

        print(f"🏃 Act#{idx+1} ➔ type: {activity.get('type_sortie')}, k_moy: {activity.get('k_moy')}")
        activity.pop("force_recompute", None)

    # 4) Ajouter moyennes 10 dernières séances et tendance
    activities = add_historical_context(activities)

    return activities


def add_historical_context(activities):
    """
    Ajoute pour chaque activité:
    - k_avg_10: moyenne k des 10 dernières séances du même type
    - drift_avg_10: moyenne drift des 10 dernières séances du même type
    - k_trend: tendance (+1 si amélioration, -1 si dégradation, 0 si stable)
    - drift_trend: tendance (-1 si amélioration, +1 si dégradation, 0 si stable)
    """
    # Mapper les types réels vers catégories d'entraînement
    def get_session_category(act):
        """
        Retourne la catégorie de session.
        Utilise session_category si déjà défini (après reclassification),
        sinon applique l'ancienne logique pour compatibilité.
        """
        # Si session_category est déjà défini, l'utiliser directement
        if act.get('session_category'):
            return act.get('session_category')

        # Sinon, utiliser l'ancienne logique (pour compatibilité avec anciennes données)
        type_sortie = act.get('type_sortie', '')
        is_fractionne = act.get('is_fractionne', False)

        if is_fractionne:
            return 'fractionné'
        elif type_sortie in ['long_run', 'endurance', 'tempo_rapide', 'tempo_recup']:
            return type_sortie
        elif type_sortie in ['normal_5k', 'normal_10k']:
            # Ces types obsolètes ont dû être reclassifiés dans index()
            # On ne devrait plus les voir ici (OPTIMISATION)
            return type_sortie  # Retourner tel quel au lieu de reclassifier
        return None

    for idx, activity in enumerate(activities):
        current_category = get_session_category(activity)

        # Ajouter la catégorie pour utilisation dans le template
        activity['session_category'] = current_category

        if not current_category:
            activity['k_avg_10'] = None
            activity['drift_avg_10'] = None
            activity['k_trend'] = 0
            activity['drift_trend'] = 0
            continue

        # Récupérer les 10 dernières séances du même type AVANT celle-ci
        previous_same_type = [
            act for i, act in enumerate(activities[idx+1:])
            if get_session_category(act) == current_category
            and isinstance(act.get('k_moy'), (int, float))
            and isinstance(act.get('deriv_cardio'), (int, float))
        ][:10]  # Limiter aux 10 premières trouvées

        if previous_same_type:
            # Moyennes des 10 dernières
            k_values = [act['k_moy'] for act in previous_same_type]
            drift_values = [act['deriv_cardio'] for act in previous_same_type]

            activity['k_avg_10'] = np.mean(k_values)
            activity['drift_avg_10'] = np.mean(drift_values)

            # Intervalles 80% (P10 et P90)
            activity['k_p10'] = np.percentile(k_values, 10)
            activity['k_p90'] = np.percentile(k_values, 90)
            activity['drift_p10'] = np.percentile(drift_values, 10)
            activity['drift_p90'] = np.percentile(drift_values, 90)

            # Calculer tendance (comparer première moitié vs deuxième moitié)
            if len(k_values) >= 6:
                mid = len(k_values) // 2
                k_recent_avg = np.mean(k_values[:mid])  # Plus récentes
                k_older_avg = np.mean(k_values[mid:])   # Plus anciennes

                drift_recent_avg = np.mean(drift_values[:mid])
                drift_older_avg = np.mean(drift_values[mid:])

                # Pour k: augmentation = amélioration (+1)
                k_diff = k_recent_avg - k_older_avg
                activity['k_trend'] = 1 if k_diff > 0.15 else (-1 if k_diff < -0.15 else 0)

                # Pour drift: diminution = amélioration (-1)
                drift_diff = drift_recent_avg - drift_older_avg
                activity['drift_trend'] = -1 if drift_diff < -0.03 else (1 if drift_diff > 0.03 else 0)
            else:
                activity['k_trend'] = 0
                activity['drift_trend'] = 0
        else:
            activity['k_avg_10'] = None
            activity['drift_avg_10'] = None
            activity['k_trend'] = 0
            activity['drift_trend'] = 0

    return activities

print("✅ Activities OK")

# --- Helper : payload vide mais JS valide (et clés attendues présentes) ---
def _empty_dashboard_payload():
    return {
        "type_sortie": "-",
        "date": "-",
        "distance_km": 0,
        "duration_min": 0,
        "allure": "-",
        "fc_moy": "-",
        "fc_max": "-",
        "k_moy": "-",
        "deriv_cardio": "-",
        "gain_alt": 0,
        "drift_slope": "-",
        "cv_allure": "-",
        "cv_cardio": "-",
        "collapse_distance_km": "-",
        "pourcentage_zone2": "-",
        "time_above_90_pct_fcmax": "-",
        "ratio_fc_allure_global": "-",
        "avg_temperature": None,
        "temp_debut": None,
        "temp_fin": None,
        "temperature": None,
        "weather_code": None,
        "weather_emoji": "❓",
        "labels": "[]",
        "allure_curve": "[]",
        "points_fc": "[]",
        "points_alt": "[]",
        "history_dates": "[]",
        "history_k": "[]",
        "history_drift": "[]",
    }


# -------------------
# Dashboard principal
# -------------------
def compute_dashboard_data(activities):
    print(f"➡ compute_dashboard_data: activities={len(activities) if activities else 0}")

    # 1) Pas d'activités -> payload vide mais JS valide
    if not activities:
        return _empty_dashboard_payload()

    # 2) Prendre la plus récente activité QUI A DES POINTS (et ne plus l'écraser ensuite)
    last = max(
        (a for a in activities if isinstance(a.get("points"), list) and a["points"]),
        key=_date_key,
        default=None
    )
    if last is None:
        return _empty_dashboard_payload()

    points = last["points"]
    if not points:
        return _empty_dashboard_payload()

    print("\n🔍 DEBUG --- Vérification température")

    # --- Date
    date_str = "-"
    try:
        date_str = datetime.strptime(last.get("date"), "%Y-%m-%dT%H:%M:%S%z").strftime("%Y-%m-%d")
    except Exception as e:
        print("❌ Erreur parsing date:", e)
        date_str = (last.get("date") or "-")[:10]

    print("📅 Date activité:", date_str)

    # --- Coordonnées (GPS)
    lat, lon = None, None
    if "lat" in points[0] and "lng" in points[0]:
        lat, lon = points[0]["lat"], points[0]["lng"]
    elif last.get("start_latlng"):
        try:
            lat, lon = last["start_latlng"][0], last["start_latlng"][1]
        except Exception:
            lat, lon = None, None

    # --- Météo : utiliser si déjà stockée, sinon calcul + sauvegarde sur Drive
    avg_temperature = last.get("avg_temperature")
    weather_code = last.get("weather_code")
    temp_debut = avg_temperature
    temp_fin = avg_temperature

    if lat is not None and lon is not None and date_str:
        if avg_temperature is None or weather_code is None:
            start_datetime_str = last.get("date")  # "2025-07-18T19:45:57Z" par ex.
            duration_minutes = (points[-1]["time"] - points[0]["time"]) / 60 if points else 0
            try:
                avg_temperature, temp_debut, temp_fin, weather_code = get_temperature_for_run(
                    lat, lon, start_datetime_str, duration_minutes
                )
                # Sauvegarde dans l'activité
                last["avg_temperature"] = avg_temperature
                last["weather_code"] = weather_code
                # Mise à jour du fichier Drive pour éviter un recalcul futur
                save_activities_to_drive(activities)
                print(f"🌡️ Température calculée et sauvegardée : {avg_temperature}°C")
            except Exception as e:
                print("⚠️ get_temperature_for_run a échoué :", e)
        else:
            print(f"🌡️ Température lue depuis activities.json : {avg_temperature}°C")
    else:
        print("⚠️ Impossible d’appeler météo: coordonnées ou date manquantes.")

    if weather_code is None:
        weather_code = -1
    weather_emoji = WEATHER_CODE_MAP.get(weather_code, "❓")

    # --- Métriques globales
    total_dist = points[-1]["distance"] / 1000.0
    total_time = (points[-1]["time"] - points[0]["time"]) / 60.0
    allure_moy = total_time / total_dist if total_dist > 0 else None

    # Séquences point-par-point (longueurs alignées)
    labels = [round(p.get("distance", 0) / 1000.0, 3) for p in points]
    if labels and labels[0] != 0:
        labels[0] = 0.0

    # FC & Alt : garder la même longueur que labels
    points_fc = [p.get("hr") if p.get("hr") is not None else None for p in points]
    base_alt = points[0].get("alt", 0) if points[0].get("alt") is not None else 0
    points_alt = [(p.get("alt", base_alt) - base_alt) if p.get("alt") is not None else 0 for p in points]

    # Allure "escaliers" tous les 500m (min/km)
    allure_curve = []
    bloc_start_idx, next_bloc_dist, last_allure = 0, 500.0, None
    for i, p in enumerate(points):
        dist = p.get("distance", 0.0)
        if dist >= next_bloc_dist or i == len(points) - 1:
            bloc_points = points[bloc_start_idx:i + 1]
            if bloc_points:
                d = bloc_points[-1].get("distance", 0) - bloc_points[0].get("distance", 0)
                t = bloc_points[-1].get("time", 0) - bloc_points[0].get("time", 0)
                if d > 0:
                    last_allure = (t / 60.0) / (d / 1000.0)
            allure_curve.extend([last_allure] * len(bloc_points))
            bloc_start_idx = i + 1
            next_bloc_dist += 500.0
    if len(allure_curve) < len(points):
        allure_curve.extend([last_allure] * (len(points) - len(allure_curve)))

    # FC moy / max sur la séance (ignore None)
    hr_vals = [h for h in points_fc if isinstance(h, (int, float))]

    # Historique k / dérive cardiaque (uniquement si numériques)
    history_dates, history_k, history_drift = [], [], []
    for act in activities:
        k = act.get("k_moy")
        d = act.get("deriv_cardio")
        if not isinstance(k, (int, float)) or not isinstance(d, (int, float)):
            continue
        dt = act.get("date") or "-"
        try:
            ds = datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S%z").strftime("%Y-%m-%d")
        except Exception:
            ds = dt[:10] if isinstance(dt, str) else "-"
        history_dates.append(ds)
        history_k.append(k)
        history_drift.append(d)

    # Limiter la taille de l'historique (esthétique)
    MAXH = 50
    if len(history_dates) > MAXH:
        history_dates  = history_dates[-MAXH:]
        history_k      = history_k[-MAXH:]
        history_drift  = history_drift[-MAXH:]

    print("📊 Dashboard calculé")

    # --- Retour : objets simples + séries JSON (pour |safe dans le template)
    return {
        "type_sortie": last.get("type_sortie", "-"),
        "date": date_str,
        "distance_km": round(total_dist, 2),
        "duration_min": round(total_time, 1),
        "allure": (
            f"{int(allure_moy)}:{int((allure_moy - int(allure_moy)) * 60):02d}"
            if isinstance(allure_moy, (int, float)) and allure_moy > 0 else "-"
        ),
        "fc_moy": round(sum(hr_vals) / len(hr_vals), 1) if hr_vals else "-",
        "fc_max": max(hr_vals) if hr_vals else "-",
        "k_moy": last.get("k_moy", "-"),
        "deriv_cardio": last.get("deriv_cardio", "-"),
        "gain_alt": _compute_denivele_pos(points),
        "drift_slope": last.get("drift_slope", "-"),
        "cv_allure": last.get("cv_allure", "-"),
        "cv_cardio": last.get("cv_cardio", "-"),
        "collapse_distance_km": last.get("collapse_distance_km", "-"),
        "pourcentage_zone2": last.get("pourcentage_zone2", "-"),
        "time_above_90_pct_fcmax": last.get("time_above_90_pct_fcmax", "-"),
        "ratio_fc_allure_global": last.get("ratio_fc_allure_global", "-"),
        "avg_temperature": avg_temperature,
        "temp_debut": temp_debut,
        "temp_fin": temp_fin,
        "temperature": avg_temperature,
        "weather_code": weather_code,
        "weather_emoji": weather_emoji,

        # Séries pour les graphiques (JSON strings)
        "labels": json.dumps(labels, ensure_ascii=False),
        "allure_curve": json.dumps(allure_curve, ensure_ascii=False),
        "points_fc": json.dumps(points_fc, ensure_ascii=False),
        "points_alt": json.dumps(points_alt, ensure_ascii=False),
        "history_dates": json.dumps(history_dates, ensure_ascii=False),
        "history_k": json.dumps(history_k, ensure_ascii=False),
        "history_drift": json.dumps(history_drift, ensure_ascii=False),
    }


# --- PHASE 2: Analyse par tronçons ---

def compute_segments(activity):
    """
    Calcule les métriques par segments (tronçons) pour une activité.

    Returns:
        list: Liste de dicts avec métriques par segment
    """
    points = activity.get('points', [])
    if not points or len(points) < 2:
        return []

    distance_totale_m = points[-1].get('distance', 0)
    distance_totale_km = distance_totale_m / 1000
    if distance_totale_km < 1:
        return []

    # 🆕 Skip 300 premiers mètres pour analyse des segments
    skip_distance_m = 300  # 300 mètres
    distance_utilisable_m = distance_totale_m - skip_distance_m
    distance_utilisable_km = distance_utilisable_m / 1000

    if distance_utilisable_km < 1:
        # Course trop courte pour skipper 300m, on utilise tout
        skip_distance_m = 0
        distance_utilisable_m = distance_totale_m
        distance_utilisable_km = distance_totale_km

    # Déterminer nombre de segments (basé sur distance utilisable)
    if distance_utilisable_km < 7:
        nb_segments = 2
    elif distance_utilisable_km < 12:
        nb_segments = 3
    else:
        nb_segments = 4

    segment_distance_m = distance_utilisable_m / nb_segments
    segments = []
    prev_segment = None

    for seg_num in range(1, nb_segments + 1):
        # Décaler tous les segments de skip_distance_m
        start_dist_m = skip_distance_m + (seg_num - 1) * segment_distance_m
        end_dist_m = skip_distance_m + seg_num * segment_distance_m

        segment_points = [p for p in points if start_dist_m <= p.get('distance', 0) <= end_dist_m]
        if len(segment_points) < 2:
            continue

        # Calculs métriques
        fcs = [p.get('hr', 0) for p in segment_points if p.get('hr')]
        speeds_ms = [p.get('vel', 0) for p in segment_points if p.get('vel')]

        if not fcs or not speeds_ms:
            continue

        fc_start = fcs[0]
        fc_end = fcs[-1]
        fc_avg = sum(fcs) / len(fcs)
        fc_max_seg = max(fcs)

        avg_speed_ms = sum(speeds_ms) / len(speeds_ms)
        pace_min_per_km = (1000 / avg_speed_ms / 60) if avg_speed_ms > 0 else 0

        # Dérive intra-segment
        drift_intra = fc_end - fc_start if fc_end and fc_start else 0

        segment_data = {
            'number': seg_num,
            'start_km': start_dist_m / 1000,
            'end_km': end_dist_m / 1000,
            'pace_min_per_km': pace_min_per_km,
            'fc_start': fc_start,
            'fc_end': fc_end,
            'fc_avg': fc_avg,
            'fc_max': fc_max_seg,
            'drift_intra': drift_intra,
            'fc_diff_vs_prev': None,
            'pace_diff_vs_prev': None
        }

        # Comparaison vs segment précédent
        if prev_segment:
            segment_data['fc_diff_vs_prev'] = fc_avg - prev_segment['fc_avg']
            segment_data['pace_diff_vs_prev'] = (pace_min_per_km - prev_segment['pace_min_per_km']) * 60

        segments.append(segment_data)
        prev_segment = segment_data

    return segments


def detect_segment_patterns(segments):
    """
    Détecte des patterns dans la progression des segments.

    Returns:
        list: Liste des patterns détectés
    """
    if not segments or len(segments) < 2:
        return []

    patterns = []

    # Pattern: DÉPART_TROP_RAPIDE
    if segments[0]['pace_min_per_km'] < segments[-1]['pace_min_per_km'] * 0.95:
        pace_diff = (segments[-1]['pace_min_per_km'] - segments[0]['pace_min_per_km']) * 60
        if pace_diff > 10:
            patterns.append('DÉPART_TROP_RAPIDE')

    # Pattern: BAISSE_FIN_COURSE
    if len(segments) >= 3:
        last_pace = segments[-1]['pace_min_per_km']
        avg_pace_before = sum(s['pace_min_per_km'] for s in segments[:-1]) / (len(segments) - 1)
        if last_pace > avg_pace_before * 1.05:
            patterns.append('BAISSE_FIN_COURSE')

    # Pattern: FC_MONTE_TOUT_LE_TEMPS
    fc_increases = sum(1 for i in range(1, len(segments)) if segments[i]['fc_avg'] > segments[i-1]['fc_avg'])
    if fc_increases == len(segments) - 1:
        patterns.append('FC_MONTE_TOUT_LE_TEMPS')

    # Pattern: DÉRIVE_EXCESSIVE
    for seg in segments:
        if seg['drift_intra'] > 10:
            patterns.append(f"DÉRIVE_EXCESSIVE_T{seg['number']}")

    # Pattern: EFFORT_BIEN_GÉRÉ
    pace_variance = max(s['pace_min_per_km'] for s in segments) - min(s['pace_min_per_km'] for s in segments)
    fc_variance = max(s['fc_avg'] for s in segments) - min(s['fc_avg'] for s in segments)
    if pace_variance < 0.1 and fc_variance < 5:
        patterns.append('EFFORT_BIEN_GÉRÉ')

    return patterns


# --- PHASE 3 Sprint 1: Comparaisons historiques ---

def calculate_segment_comparisons(activity, activities, segments):
    """
    Compare chaque segment vs historique (15 derniers runs du même type).

    Returns:
        list: Comparaisons par segment avec percentiles
    """
    if not segments:
        return []

    type_sortie = activity.get('type_sortie', 'inconnu')

    # Filtrer runs du même type (max 15)
    same_type_runs = [a for a in activities if a.get('type_sortie') == type_sortie and a.get('id') != activity.get('id')][:15]

    if len(same_type_runs) < 3:
        return []

    comparisons = []

    for seg in segments:
        seg_num = seg['number']

        # Extraire métriques du même segment sur les runs passés
        historical_paces = []
        historical_fcs = []
        historical_drifts = []

        for past_run in same_type_runs:
            past_segments = compute_segments(past_run)
            if len(past_segments) >= seg_num:
                past_seg = past_segments[seg_num - 1]
                if past_seg.get('pace_min_per_km'):
                    historical_paces.append(past_seg['pace_min_per_km'])
                if past_seg.get('fc_avg'):
                    historical_fcs.append(past_seg['fc_avg'])
                if past_seg.get('drift_intra') is not None:
                    historical_drifts.append(past_seg['drift_intra'])

        if not historical_paces:
            continue

        # Calculer moyennes historiques
        avg_hist_pace = sum(historical_paces) / len(historical_paces)
        avg_hist_fc = sum(historical_fcs) / len(historical_fcs) if historical_fcs else 0
        avg_hist_drift = sum(historical_drifts) / len(historical_drifts) if historical_drifts else 0

        # Comparaisons
        pace_diff_sec = (seg['pace_min_per_km'] - avg_hist_pace) * 60
        fc_diff = seg['fc_avg'] - avg_hist_fc if avg_hist_fc else 0
        drift_diff = seg['drift_intra'] - avg_hist_drift if avg_hist_drift else 0

        # Tendances
        pace_trend = "faster" if pace_diff_sec < -3 else ("slower" if pace_diff_sec > 3 else "similar")
        fc_trend = "lower" if fc_diff < -2 else ("higher" if fc_diff > 2 else "similar")
        drift_trend = "better" if drift_diff < -0.5 else ("worse" if drift_diff > 0.5 else "similar")

        # Percentiles
        pace_percentile = sum(1 for p in historical_paces if seg['pace_min_per_km'] <= p) / len(historical_paces) * 100
        fc_percentile = sum(1 for f in historical_fcs if seg['fc_avg'] <= f) / len(historical_fcs) * 100 if historical_fcs else 50

        comparisons.append({
            'segment_number': seg_num,
            'sample_size': len(historical_paces),
            'comparison': {
                'pace_diff_sec': pace_diff_sec,
                'fc_diff': fc_diff,
                'drift_diff': drift_diff,
                'pace_trend': pace_trend,
                'fc_trend': fc_trend,
                'drift_trend': drift_trend
            },
            'percentiles': {
                'pace': int(pace_percentile),
                'fc': int(fc_percentile)
            }
        })

    return comparisons


# --- PHASE 3 Sprint 2: Analyse santé cardiaque ---

def check_profile_completion(profile):
    """
    Vérifie si le profil est complété à 100%.

    Returns:
        dict: {'complete': bool, 'percentage': int, 'missing_fields': list}
    """
    required_fields = {
        'birth_date': lambda v: v and v != "",
        'weight': lambda v: v and v > 0,
        'hr_rest': lambda v: v and v > 0,
        'hr_max': lambda v: v and v > 0,
    }

    missing = []
    completed = 0

    for field, validator in required_fields.items():
        value = profile.get(field)
        if validator(value):
            completed += 1
        else:
            missing.append(field)

    total = len(required_fields)
    percentage = int((completed / total) * 100)

    return {
        'complete': len(missing) == 0,
        'percentage': percentage,
        'missing_fields': missing
    }


def check_objectives_completion(profile):
    """
    Vérifie si les objectifs sont complétés à 100%.

    Returns:
        dict: {'complete': bool, 'percentage': int, 'missing_fields': list}
    """
    objectives = profile.get('objectives', {})

    required_fields = {
        'main_goal': lambda v: v and v != "",
        'running_style': lambda v: v and v != "",
        'intensity_tolerance': lambda v: v and v > 0,
    }

    missing = []
    completed = 0

    for field, validator in required_fields.items():
        value = objectives.get(field)
        if validator(value):
            completed += 1
        else:
            missing.append(field)

    total = len(required_fields)
    percentage = int((completed / total) * 100)

    return {
        'complete': len(missing) == 0,
        'percentage': percentage,
        'missing_fields': missing
    }


def calculate_lthr(activities, profile):
    """
    Calcule le LTHR (Lactate Threshold Heart Rate) basé sur les 10 derniers runs >7km.

    Args:
        activities: Liste de toutes les activités
        profile: Profil utilisateur

    Returns:
        dict: {'lthr': int, 'calculated_from': int, 'runs_used': list}
    """
    # Filtrer les runs de type tempo/endurance/long_run (>7km pour exclure récupération)
    tempo_runs = []
    runs_details = []

    for activity in reversed(activities):  # Du plus récent au plus ancien
        fc_moy = activity.get('fc_moy', 0)
        if fc_moy <= 0:
            continue

        # Classifier le run selon distance
        dist_km = activity.get('distance_km', 0)
        if dist_km < 7:
            continue  # Exclure les runs courts (récupération/tempo court)

        tempo_runs.append(fc_moy)
        runs_details.append({
            'date': activity.get('date', ''),
            'distance_km': dist_km,
            'fc_moy': fc_moy,
            'session_category': activity.get('session_category', '')
        })

        if len(tempo_runs) >= 10:
            break

    if not tempo_runs:
        return {
            'lthr': None,
            'calculated_from': 0,
            'runs_used': [],
            'status': 'insufficient_data'
        }

    lthr = int(sum(tempo_runs) / len(tempo_runs))

    # Calculer le pourcentage de réserve cardiaque
    hr_rest = profile.get('hr_rest', 59)
    hr_max = profile.get('hr_max', 170)
    hr_reserve = hr_max - hr_rest
    lthr_percentage = ((lthr - hr_rest) / hr_reserve) * 100 if hr_reserve > 0 else 0

    # Déterminer dans quelle zone se situe le LTHR
    if lthr_percentage < 60:
        lthr_zone = 1
    elif lthr_percentage < 70:
        lthr_zone = 2
    elif lthr_percentage < 80:
        lthr_zone = 3
    elif lthr_percentage < 90:
        lthr_zone = 4
    else:
        lthr_zone = 5

    return {
        'lthr': lthr,
        'calculated_from': len(tempo_runs),
        'runs_used': runs_details,
        'lthr_percentage': round(lthr_percentage, 1),
        'lthr_zone': lthr_zone,
        'status': 'ok'
    }


def analyze_cardiac_health(activity, profile):
    """
    Analyse santé cardiaque avec 5 zones FC et alertes.

    Returns:
        dict: Analyse complète santé cardiaque
    """
    points = activity.get('points', [])
    if not points:
        return {'status': 'no_data', 'alerts': [], 'observations': [], 'recommendations': []}

    # Méthode Karvonen (basée sur FC repos et FC max réelles)
    hr_rest = profile.get('hr_rest', 59)
    hr_max = profile.get('hr_max', 170)
    hr_reserve = hr_max - hr_rest  # Réserve cardiaque

    # Définir les 5 zones FC selon Karvonen
    # Formule: FC_zone = (réserve_cardiaque × %intensité) + FC_repos
    zones = {
        1: (hr_reserve * 0.50 + hr_rest, hr_reserve * 0.60 + hr_rest),  # Récupération (50-60%)
        2: (hr_reserve * 0.60 + hr_rest, hr_reserve * 0.70 + hr_rest),  # Endurance base (60-70%)
        3: (hr_reserve * 0.70 + hr_rest, hr_reserve * 0.80 + hr_rest),  # Tempo (70-80%)
        4: (hr_reserve * 0.80 + hr_rest, hr_reserve * 0.90 + hr_rest),  # Seuil (80-90%)
        5: (hr_reserve * 0.90 + hr_rest, hr_reserve * 1.00 + hr_rest),  # VO2 max (90-100%)
    }

    # Calculer temps dans chaque zone
    zone_times = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for i, p in enumerate(points):
        hr = p.get('hr')
        if hr is None or hr == 0:
            continue

        # Déterminer zone
        for zone_num, (min_hr, max_hr) in zones.items():
            if min_hr is not None and max_hr is not None and min_hr <= hr < max_hr:
                # Estimer durée (temps entre 2 points)
                if i < len(points) - 1:
                    duration = points[i+1].get('time', 0) - p.get('time', 0)
                    zone_times[zone_num] += duration
                break

    total_time = sum(zone_times.values())
    zone_percentages = {z: (t / total_time * 100) if total_time > 0 else 0 for z, t in zone_times.items()}

    # Métriques FC
    all_hrs = [p.get('hr', 0) for p in points if p.get('hr')]
    fc_avg = sum(all_hrs) / len(all_hrs) if all_hrs else 0
    fc_max = max(all_hrs) if all_hrs else 0
    fc_start = all_hrs[0] if all_hrs else 0
    fc_end = all_hrs[-1] if all_hrs else 0

    # Déterminer statut
    pct_zone5 = zone_percentages.get(5, 0)
    pct_zone4 = zone_percentages.get(4, 0)

    if pct_zone5 > 50:
        status = 'warning'
    elif pct_zone4 + pct_zone5 > 70:
        status = 'warning'
    elif pct_zone5 < 10 and zone_percentages.get(2, 0) > 50:
        status = 'excellent'
    else:
        status = 'good'

    # Alertes
    alerts = []
    if pct_zone5 > 60:
        alerts.append("⚠️ Plus de 60% du temps en Zone 5 (VO2 max) - intensité très élevée")
    if fc_max > hr_max * 0.98:
        alerts.append("⚠️ FC max atteinte proche du maximum personnel")

    # Observations
    observations = []
    if pct_zone5 > 30:
        observations.append(f"Effort intense: {pct_zone5:.0f}% en Zone 5")
    if zone_percentages.get(2, 0) > 50:
        observations.append(f"Bonne endurance de base: {zone_percentages[2]:.0f}% en Zone 2")
    if fc_end > fc_start * 1.15:
        observations.append(f"Dérive cardiaque notable: FC +{((fc_end - fc_start) / fc_start * 100):.0f}%")

    # Recommandations
    recommendations = []
    if pct_zone5 > 40:
        recommendations.append("Ajouter plus de sorties en Zone 2 pour la récupération")
    if zone_percentages.get(2, 0) < 20:
        recommendations.append("Augmenter le volume en endurance de base (Zone 2)")

    return {
        'status': status,
        'hr_zones': {
            'zone_times': zone_times,
            'zone_percentages': zone_percentages,
            'method': 'karvonen',
            'hr_rest': hr_rest,
            'hr_max': hr_max,
            'hr_reserve': hr_reserve
        },
        'fc_stats': {
            'fc_start': fc_start,
            'fc_end': fc_end,
            'fc_avg': fc_avg,
            'fc_max': fc_max
        },
        'alerts': alerts,
        'observations': observations,
        'recommendations': recommendations
    }

# --- Phase 3 Sprint 3: Programme Hebdomadaire ---

def calculate_weekly_score(adherence_rate, type_respect_rate,
                          total_distance_realized, total_distance_programmed,
                          week_activities, profile=None, run_details=None):
    """
    Calcule la note hebdomadaire /10 basée sur 5 facteurs.

    Pondération:
    - Volume (distance réalisée vs programmée): 20%
    - Qualité technique (k, drift vs objectifs): 30%
    - Adhésion au programme: 20%
    - Respect des types de séances: 20%
    - Régularité: 10%

    Returns:
        dict avec score, details, strengths, improvements
    """
    scores = {}

    # 1. VOLUME (20%)
    if total_distance_programmed > 0:
        volume_ratio = total_distance_realized / total_distance_programmed
        scores['volume'] = min(10, volume_ratio * 10)  # >100% = 10/10
    else:
        scores['volume'] = 5.0

    # 2. ADHÉSION (20%)
    scores['adherence'] = adherence_rate / 10  # 100% = 10/10

    # 3. RESPECT TYPES (20%)
    scores['type_respect'] = type_respect_rate / 10

    # 4. QUALITÉ TECHNIQUE (30%)
    quality_score = 7.0  # Par défaut: correct

    if profile and week_activities:
        personalized_targets = profile.get('personalized_targets', {})

        # Calculer k et drift moyens de la semaine
        k_values = []
        drift_values = []
        for act in week_activities:
            if act.get('k_moy'):
                k_values.append(act['k_moy'])
            if act.get('deriv_cardio'):
                drift_values.append(act['deriv_cardio'])

        if k_values and drift_values:
            avg_k = sum(k_values) / len(k_values)
            avg_drift = sum(drift_values) / len(drift_values)

            # Comparer avec objectifs (moyenne tous types)
            all_k_targets = [t.get('k_target', 5.0) for t in personalized_targets.values() if t.get('k_target')]
            all_drift_targets = [t.get('drift_target', 1.1) for t in personalized_targets.values() if t.get('drift_target')]

            if all_k_targets and all_drift_targets:
                avg_k_target = sum(all_k_targets) / len(all_k_targets)
                avg_drift_target = sum(all_drift_targets) / len(all_drift_targets)

                # Score basé sur écart aux objectifs
                k_gap = abs(avg_k - avg_k_target) / avg_k_target
                drift_gap = abs(avg_drift - avg_drift_target) / avg_drift_target

                # Plus l'écart est petit, meilleur le score
                k_score = max(0, 10 - (k_gap * 10))
                drift_score = max(0, 10 - (drift_gap * 10))
                quality_score = (k_score + drift_score) / 2

    scores['quality'] = quality_score

    # 5. RÉGULARITÉ (10%)
    # Score basé sur répartition des runs dans la semaine
    regularity_score = 7.0  # Par défaut
    if week_activities:
        # Idéal: runs bien répartis (pas tous le même jour)
        dates = [act.get('date', '')[:10] for act in week_activities]
        unique_days = len(set(dates))
        runs_count = len(week_activities)

        if runs_count > 0:
            # Score max si 1 run par jour différent
            regularity_score = min(10, (unique_days / runs_count) * 10)

    scores['regularity'] = regularity_score

    # CALCUL SCORE GLOBAL (moyenne pondérée)
    final_score = (
        scores['volume'] * 0.20 +
        scores['adherence'] * 0.20 +
        scores['type_respect'] * 0.20 +
        scores['quality'] * 0.30 +
        scores['regularity'] * 0.10
    )

    final_score = round(final_score, 1)

    # DÉTERMINER TENDANCE (nécessite historique)
    trend = "stable"  # Par défaut, sera comparé avec semaine précédente plus tard

    # IDENTIFIER POINTS FORTS
    strengths = []
    if scores['volume'] >= 9.0:
        strengths.append(f"Volume excellent ({total_distance_realized:.1f}km réalisés)")
    if scores['adherence'] >= 9.0:
        strengths.append(f"Adhésion parfaite ({adherence_rate:.0f}%)")
    if scores['type_respect'] >= 9.0:
        strengths.append("Types de séances bien respectés")
    if scores['quality'] >= 8.0:
        strengths.append("Qualité technique (k/drift) excellente")

    # IDENTIFIER AXES D'AMÉLIORATION
    improvements = []
    if scores['volume'] < 7.0:
        gap_km = total_distance_programmed - total_distance_realized
        improvements.append(f"Volume insuffisant (-{gap_km:.1f}km vs prévu)")
    if scores['adherence'] < 7.0:
        missed_count = len([r for r in (run_details or []) if r.get('status') == 'missed'])
        if missed_count > 0:
            improvements.append(f"Manque {missed_count} sortie(s)")
    if scores['type_respect'] < 7.0:
        improvements.append("Types de séances pas toujours respectés")
    if scores['quality'] < 7.0:
        improvements.append("Qualité technique à améliorer (k/drift)")

    return {
        'score': final_score,
        'volume': round(scores['volume'], 1),
        'adherence': round(scores['adherence'], 1),
        'type_respect': round(scores['type_respect'], 1),
        'quality': round(scores['quality'], 1),
        'regularity': round(scores['regularity'], 1),
        'trend': trend,
        'strengths': strengths,
        'improvements': improvements
    }


def analyze_past_week(previous_program, activities, profile=None):
    """
    Analyse la semaine précédente: compare runs réalisés vs programme.

    Args:
        previous_program: Dict du programme de la semaine précédente
        activities: Liste des activités (triées par date décroissante)
        profile: Dict profil utilisateur (optionnel, pour calcul qualité technique)

    Returns:
        dict: Analyse avec runs_completed, runs_missed, adherence_rate, details, score
    """
    if not previous_program or not previous_program.get('runs'):
        return None

    # Dates de la semaine programmée
    start_date_str = previous_program.get('start_date')  # "2025-11-18"
    end_date_str = previous_program.get('end_date')  # "2025-11-24"

    if not start_date_str or not end_date_str:
        return None

    try:
        week_start = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        week_end = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

    # Filtrer activités de cette semaine
    week_activities = []
    for act in activities:
        date_str = act.get('date', '')
        if date_str:
            try:
                if 'T' in date_str:
                    date_only = date_str.split('T')[0]
                else:
                    date_only = date_str[:10]
                act_date = datetime.strptime(date_only, '%Y-%m-%d').date()
                if week_start <= act_date <= week_end:
                    week_activities.append(act)
            except ValueError:
                continue

    # Analyser chaque run programmé
    programmed_runs = previous_program.get('runs', [])
    runs_completed = 0
    runs_missed = 0
    types_respected = 0
    run_details = []

    for prog_run in programmed_runs:
        prog_type = prog_run.get('type')  # 'sortie_longue', 'tempo', 'recuperation'
        prog_distance = prog_run.get('distance_km', 0)
        prog_day = prog_run.get('day', '')
        prog_date = prog_run.get('day_date', '')

        # Chercher un run réalisé correspondant (priorité au même jour)
        matched = False
        matched_activity = None
        type_respected = False

        for act in week_activities:
            act_date_str = act.get('date', '')
            if 'T' in act_date_str:
                act_date_only = act_date_str.split('T')[0]
            else:
                act_date_only = act_date_str[:10]

            # Match prioritaire: même jour
            same_day = (act_date_only == prog_date)

            if same_day:
                matched = True
                matched_activity = act
                # Vérifier si le type est respecté
                act_normalized_type = normalize_session_type(act)
                type_respected = (act_normalized_type == prog_type)
                break

        # Si pas de match par jour, chercher par type compatible dans la semaine
        if not matched:
            for act in week_activities:
                act_normalized_type = normalize_session_type(act)
                if act_normalized_type == prog_type:
                    matched = True
                    matched_activity = act
                    type_respected = True
                    break

        if matched:
            runs_completed += 1
            if type_respected:
                types_respected += 1
            # Ajouter le type normalisé à l'activité matchée
            matched_activity['normalized_type'] = normalize_session_type(matched_activity)
            run_details.append({
                'programmed': prog_run,
                'realized': matched_activity,
                'status': 'completed',
                'type_respected': type_respected
            })
        else:
            runs_missed += 1
            run_details.append({
                'programmed': prog_run,
                'realized': None,
                'status': 'missed',
                'type_respected': False
            })

    total_programmed = len(programmed_runs)
    adherence_rate = (runs_completed / total_programmed * 100) if total_programmed > 0 else 0
    type_respect_rate = (types_respected / runs_completed * 100) if runs_completed > 0 else 0

    # Calculer distances
    total_distance_programmed = previous_program.get('summary', {}).get('total_distance', 0)
    total_distance_realized = sum(act.get('distance_km', 0) for act in week_activities)

    # Calculer la note /10 (NOUVEAU)
    score_metrics = calculate_weekly_score(
        adherence_rate=adherence_rate,
        type_respect_rate=type_respect_rate,
        total_distance_realized=total_distance_realized,
        total_distance_programmed=total_distance_programmed,
        week_activities=week_activities,
        profile=profile,
        run_details=run_details
    )

    return {
        'week_number': previous_program.get('week_number'),
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_programmed': total_programmed,
        'runs_completed': runs_completed,
        'runs_missed': runs_missed,
        'types_respected': types_respected,
        'adherence_rate': round(adherence_rate, 1),
        'type_respect_rate': round(type_respect_rate, 1),
        'run_details': run_details,
        'total_distance_programmed': total_distance_programmed,
        'total_distance_realized': total_distance_realized,
        # NOUVEAU: Score et métriques
        'score': score_metrics['score'],
        'score_details': score_metrics,
        'trend': score_metrics.get('trend', 'stable'),
        'strengths': score_metrics.get('strengths', []),
        'improvements': score_metrics.get('improvements', [])
    }


def generate_weekly_program(profile, activities, week_summary_text=""):
    """
    Génère un programme hebdomadaire de 4 runs personnalisé.
    Pattern: récup 5-6km → tempo 9km → adaptatif 5km → long run 12-15km

    Args:
        profile: Dict profil utilisateur
        activities: Liste des activités récentes
        week_summary_text: Texte du bilan de la semaine précédente (optionnel)

    Returns:
        dict: Programme avec 4 runs (structure complète)
    """
    # Extraction profil
    objectives = profile.get('objectives', {})
    preferences = profile.get('preferences', {})
    personalized_targets = profile.get('personalized_targets', {})
    main_goal = objectives.get('main_goal', 'semi_marathon')
    running_style = objectives.get('running_style', 'moderate')
    intensity_tolerance = objectives.get('intensity_tolerance', 50)
    min_pace_str = preferences.get('min_comfortable_pace', '5:20')
    max_pace_str = preferences.get('max_comfortable_pace', '5:40')

    # Convertir allures en sec/km
    def pace_to_sec(pace_str):
        parts = pace_str.split(':')
        return int(parts[0]) * 60 + int(parts[1])

    min_pace_sec = pace_to_sec(min_pace_str)
    max_pace_sec = pace_to_sec(max_pace_str)
    avg_pace_sec = (min_pace_sec + max_pace_sec) / 2

    # Calculer moyennes récentes (4 dernières semaines)
    recent_activities = activities[:12] if len(activities) > 12 else activities

    avg_distance = 0
    avg_pace = avg_pace_sec
    avg_fc = 140

    if recent_activities:
        distances = [act.get('distance_km', 10) for act in recent_activities if act.get('distance_km')]
        paces = [act.get('pace_min_per_km', avg_pace_sec) for act in recent_activities if act.get('pace_min_per_km')]
        fcs = [act.get('fc_moy', 140) for act in recent_activities if act.get('fc_moy')]

        if distances:
            avg_distance = sum(distances) / len(distances)
        if paces:
            avg_pace = sum(paces) / len(paces)
        if fcs:
            avg_fc = sum(fcs) / len(fcs)

    # Déterminer la semaine actuelle
    today = date.today()
    week_number = today.isocalendar()[1]

    # Calculer dates de la semaine (lundi → dimanche)
    days_since_monday = today.weekday()
    monday = today - timedelta(days=days_since_monday)
    sunday = monday + timedelta(days=6)

    # Calculate average pace by run type from last 10 runs of each type
    # 🎯 NOUVELLE LOGIQUE: Basée sur performances réelles + marge de sécurité
    pace_by_type = {}

    for run_type in ['tempo_recup', 'endurance', 'long_run']:
        type_paces = []
        type_count = 0
        for act in activities:
            if (act.get('session_category') == run_type or act.get('type_sortie') == run_type):
                pace_val = act.get('pace_min_per_km')

                # Si pace_min_per_km absent ou 0, essayer de parser depuis 'allure'
                if not pace_val or pace_val == 0:
                    allure_str = act.get('allure', '')
                    if allure_str and ':' in allure_str:
                        try:
                            # Parser "5:10" vers secondes (5*60 + 10 = 310)
                            parts = allure_str.split(':')
                            pace_val = int(parts[0]) * 60 + int(parts[1])
                        except (ValueError, IndexError):
                            pace_val = 0

                if pace_val and pace_val > 0:
                    type_paces.append(pace_val)
                    type_count += 1
                    if type_count >= 10:  # Moyenne des 10 derniers du même type
                        break

        if type_paces:
            # Moyenne des 10 derniers runs de ce type
            pace_by_type[run_type] = sum(type_paces) / len(type_paces)

    # 🆕 FALLBACK INTELLIGENT: Si pas assez d'historique, calculer depuis tous les runs récents
    # Au lieu d'utiliser les préférences fixes qui peuvent être obsolètes
    if not pace_by_type:
        # Prendre les 20 derniers runs, calculer P75 (75e percentile = tempo réaliste)
        all_recent_paces = []
        for act in activities[:20]:
            pace_val = act.get('pace_min_per_km')
            if not pace_val or pace_val == 0:
                allure_str = act.get('allure', '')
                if allure_str and ':' in allure_str:
                    try:
                        parts = allure_str.split(':')
                        pace_val = int(parts[0]) * 60 + int(parts[1])
                    except (ValueError, IndexError):
                        pace_val = 0
            if pace_val and pace_val > 0:
                all_recent_paces.append(pace_val)

        if all_recent_paces:
            all_recent_paces.sort()
            p75_index = int(len(all_recent_paces) * 0.75)
            baseline_pace = all_recent_paces[p75_index]  # Allure P75 = tempo réaliste

            # Dériver les autres allures depuis cette baseline
            pace_by_type['tempo_recup'] = baseline_pace + 30  # +30 sec pour récup
            pace_by_type['endurance'] = baseline_pace + 10    # +10 sec pour endurance
            pace_by_type['long_run'] = baseline_pace + 15     # +15 sec pour long run

    # --- RUN 1: RÉCUPÉRATION 5-6km (Lundi) ---
    run1_distance = 5.5
    run1_pace_sec = pace_by_type.get('tempo_recup', avg_pace) + 20
    run1_pace_min = int(run1_pace_sec // 60)
    run1_pace_sec_remain = int(run1_pace_sec % 60)
    run1_pace_str = f"{run1_pace_min}:{run1_pace_sec_remain:02d}/km"
    run1_predicted_time_sec = run1_distance * run1_pace_sec
    run1_predicted_hours = int(run1_predicted_time_sec // 3600)
    run1_predicted_mins = int((run1_predicted_time_sec % 3600) // 60)
    run1_predicted_secs = int(run1_predicted_time_sec % 60)
    run1_predicted_time = f"{run1_predicted_hours:02d}:{run1_predicted_mins:02d}:{run1_predicted_secs:02d}"
    run1_fc_min = int(avg_fc - 15)
    run1_fc_max = int(avg_fc - 5)

    # --- RUN 2: TEMPO LÉGER 8-10km (Mercredi) ---
    run2_distance = 9.0
    run2_pace_sec = pace_by_type.get('endurance', avg_pace)  # Use real endurance average
    run2_pace_min = int(run2_pace_sec // 60)
    run2_pace_sec_remain = int(run2_pace_sec % 60)
    run2_pace_str = f"{run2_pace_min}:{run2_pace_sec_remain:02d}/km"
    run2_predicted_time_sec = run2_distance * run2_pace_sec
    run2_predicted_hours = int(run2_predicted_time_sec // 3600)
    run2_predicted_mins = int((run2_predicted_time_sec % 3600) // 60)
    run2_predicted_secs = int(run2_predicted_time_sec % 60)
    run2_predicted_time = f"{run2_predicted_hours:02d}:{run2_predicted_mins:02d}:{run2_predicted_secs:02d}"
    run2_fc_min = int(avg_fc - 5)
    run2_fc_max = int(avg_fc + 5)

    # --- RUN 3: ADAPTATIF 5km (Vendredi) - Fractionné OU Récupération ---
    # Déterminer le type selon le bilan de la semaine précédente
    run3_is_fractionne = False
    run3_reason = ""

    if week_summary_text:
        # Analyser le bilan pour décider
        keywords_fractionne = ['manque intensité', 'manque d\'intensité', 'zones.*faible', 'Z3.*faible', 'Z4.*faible', 'seuil insuffisant', 'tempo insuffisant']
        keywords_recup = ['fatigue', 'k élevé', 'k.*élevé', 'dérive élevé', 'dérive.*élevé', 'surentraînement', 'récupération nécessaire']

        import re
        for kw in keywords_fractionne:
            if re.search(kw, week_summary_text, re.IGNORECASE):
                run3_is_fractionne = True
                run3_reason = "Manque d'intensité détecté - travail Z4-Z5"
                break

        for kw in keywords_recup:
            if re.search(kw, week_summary_text, re.IGNORECASE):
                run3_is_fractionne = False
                run3_reason = "Fatigue détectée - privilégier récupération"
                break

    # Si pas de bilan ou pas de mots-clés détectés, alterner intelligemment
    if not run3_reason:
        # Par défaut : récupération (plus sûr avant long run)
        run3_is_fractionne = False
        run3_reason = "Récupération pré-long run par défaut"

    run3_distance = 5.0

    if run3_is_fractionne:
        # Fractionné : 5km avec intervalles, allure rapide
        run3_type = 'fractionne'
        run3_type_display = 'Fractionné'
        run3_pace_sec = avg_pace - 30  # 30 sec/km plus rapide que la moyenne
        run3_fc_min = int(avg_fc + 10)
        run3_fc_max = int(avg_fc + 25)
        run3_zones = [4, 5]
        run3_k_target = personalized_targets.get('tempo_rapide', {}).get('k_target', 6.5)
        run3_drift_target = personalized_targets.get('tempo_rapide', {}).get('drift_target', 12.0)
        run3_notes = f'Fractionné: intervalles 400-800m. {run3_reason}'
    else:
        # Récupération
        run3_type = 'recuperation'
        run3_type_display = 'Récupération'
        run3_pace_sec = pace_by_type.get('tempo_recup', avg_pace) + 25
        run3_fc_min = int(avg_fc - 15)
        run3_fc_max = int(avg_fc - 5)
        run3_zones = [1, 2]
        run3_k_target = personalized_targets.get('tempo_recup', {}).get('k_target', 5.0)
        run3_drift_target = personalized_targets.get('tempo_recup', {}).get('drift_target', 6.5)
        run3_notes = f'Récupération pré-long run. {run3_reason}'

    run3_pace_min = int(run3_pace_sec // 60)
    run3_pace_sec_remain = int(run3_pace_sec % 60)
    run3_pace_str = f"{run3_pace_min}:{run3_pace_sec_remain:02d}/km"
    run3_predicted_time_sec = run3_distance * run3_pace_sec
    run3_predicted_hours = int(run3_predicted_time_sec // 3600)
    run3_predicted_mins = int((run3_predicted_time_sec % 3600) // 60)
    run3_predicted_secs = int(run3_predicted_time_sec % 60)
    run3_predicted_time = f"{run3_predicted_hours:02d}:{run3_predicted_mins:02d}:{run3_predicted_secs:02d}"

    # --- RUN 4: LONG RUN 12km+ (Dimanche) ---
    run4_distance = 12.0 if avg_distance < 10 else min(avg_distance * 1.2, 15)
    run4_pace_sec = pace_by_type.get('long_run', avg_pace) + 5  # Use real long_run average + small margin
    run4_pace_min = int(run4_pace_sec // 60)
    run4_pace_sec_remain = int(run4_pace_sec % 60)
    run4_pace_str = f"{run4_pace_min}:{run4_pace_sec_remain:02d}/km"
    run4_predicted_time_sec = run4_distance * run4_pace_sec
    run4_predicted_hours = int(run4_predicted_time_sec // 3600)
    run4_predicted_mins = int((run4_predicted_time_sec % 3600) // 60)
    run4_predicted_secs = int(run4_predicted_time_sec % 60)
    run4_predicted_time = f"{run4_predicted_hours:02d}:{run4_predicted_mins:02d}:{run4_predicted_secs:02d}"
    run4_fc_min = int(avg_fc - 10)
    run4_fc_max = int(avg_fc)

    # Construire le programme
    program = {
        'week_number': week_number,
        'start_date': monday.strftime('%Y-%m-%d'),
        'end_date': sunday.strftime('%Y-%m-%d'),
        'generated_at': datetime.now().isoformat(),
        'runs': [
            {
                'day': 'Lundi',
                'day_date': monday.strftime('%Y-%m-%d'),
                'type': 'recuperation',
                'type_display': 'Récupération',
                'distance_km': run1_distance,
                'pace_target': run1_pace_str,
                'fc_target': f"{run1_fc_min}-{run1_fc_max} bpm",
                'fc_target_min': run1_fc_min,
                'fc_target_max': run1_fc_max,
                'predicted_time': run1_predicted_time,
                'zones_target': [1, 2],  # Zones 1-2
                'k_target': personalized_targets.get('tempo_recup', {}).get('k_target', 5.0),
                'drift_target': personalized_targets.get('tempo_recup', {}).get('drift_target', 6.5),
                'notes': 'Relâchement total, endurance de base. Profitez du plaisir de courir.'
            },
            {
                'day': 'Mercredi',
                'day_date': (monday + timedelta(days=2)).strftime('%Y-%m-%d'),
                'type': 'tempo_leger',
                'type_display': 'Tempo Léger',
                'distance_km': run2_distance,
                'pace_target': run2_pace_str,
                'fc_target': f"{run2_fc_min}-{run2_fc_max} bpm",
                'fc_target_min': run2_fc_min,
                'fc_target_max': run2_fc_max,
                'predicted_time': run2_predicted_time,
                'zones_target': [2, 3],  # Zones 2-3
                'k_target': personalized_targets.get('endurance', {}).get('k_target', 5.5),
                'drift_target': personalized_targets.get('endurance', {}).get('drift_target', 8.0),
                'notes': 'Allure confortable, zone tempo. Respiration contrôlée.'
            },
            {
                'day': 'Vendredi',
                'day_date': (monday + timedelta(days=4)).strftime('%Y-%m-%d'),
                'type': run3_type,
                'type_display': run3_type_display,
                'distance_km': run3_distance,
                'pace_target': run3_pace_str,
                'fc_target': f"{run3_fc_min}-{run3_fc_max} bpm",
                'fc_target_min': run3_fc_min,
                'fc_target_max': run3_fc_max,
                'predicted_time': run3_predicted_time,
                'zones_target': run3_zones,
                'k_target': run3_k_target,
                'drift_target': run3_drift_target,
                'notes': run3_notes
            },
            {
                'day': 'Dimanche',
                'day_date': (monday + timedelta(days=6)).strftime('%Y-%m-%d'),
                'type': 'long_run',
                'type_display': 'Long Run',
                'distance_km': run4_distance,
                'pace_target': run4_pace_str,
                'fc_target': f"{run4_fc_min}-{run4_fc_max} bpm",
                'fc_target_min': run4_fc_min,
                'fc_target_max': run4_fc_max,
                'predicted_time': run4_predicted_time,
                'zones_target': [2, 3],  # Zones 2-3
                'k_target': personalized_targets.get('long_run', {}).get('k_target', 5.2),
                'drift_target': personalized_targets.get('long_run', {}).get('drift_target', 12.0),
                'notes': 'Sortie longue endurance. Construire la capacité aérobie. Cocher "dernier run" après.'
            }
        ],
        'summary': {
            'total_distance': run1_distance + run2_distance + run3_distance + run4_distance,
            'total_time_predicted': f"{int((run1_predicted_time_sec + run2_predicted_time_sec + run3_predicted_time_sec + run4_predicted_time_sec) // 3600):02d}:{int(((run1_predicted_time_sec + run2_predicted_time_sec + run3_predicted_time_sec + run4_predicted_time_sec) % 3600) // 60):02d}",
            'balance': 'Pattern semi-marathon: récup → tempo → récup → long run'
        }
    }

    # NOUVEAU: Enrichir avec objectifs
    global_objective = profile.get('global_objective', '')
    main_goal = objectives.get('main_goal', 'semi_marathon')

    # Parser temps cible depuis global_objective (format: "Semi marathon wn 1h45" ou "1:45:00")
    target_time = None
    target_pace = None
    target_distance = 21.1  # Default semi-marathon

    if '1h45' in global_objective or '1:45' in global_objective:
        target_time = "1:45:00"
        target_seconds = 1*3600 + 45*60  # 6300s
        pace_sec = target_seconds / target_distance  # 298s/km
        target_pace = f"{int(pace_sec//60)}:{int(pace_sec%60):02d}"
    elif '2h' in global_objective or '2:00' in global_objective:
        target_time = "2:00:00"
        target_seconds = 2*3600
        pace_sec = target_seconds / target_distance
        target_pace = f"{int(pace_sec//60)}:{int(pace_sec%60):02d}"

    # Calculer meilleure performance récente
    best_pace = None
    best_distance = 0
    for act in activities[:20]:  # 20 derniers runs
        dist = act.get('distance_km', 0)
        pace = act.get('pace_min_per_km', 0)
        if dist > best_distance:
            best_distance = dist
            if pace and pace > 0:
                pace_min = int(pace // 60)
                pace_sec = int(pace % 60)
                best_pace = f"{pace_min}:{pace_sec:02d}"

    # Gap entre objectif et réalité
    pace_gap = None
    if target_pace and best_pace:
        try:
            target_sec = int(target_pace.split(':')[0])*60 + int(target_pace.split(':')[1])
            best_sec = int(best_pace.split(':')[0])*60 + int(best_pace.split(':')[1])
            pace_gap = best_sec - target_sec  # secondes à gagner (positif = besoin amélioration)
        except:
            pass

    # Ajouter objectifs au summary
    program['summary']['objective'] = {
        'type': main_goal,
        'target_time': target_time,
        'target_pace': target_pace,
        'target_distance': target_distance,
        'current_best_pace': best_pace,
        'current_best_distance': round(best_distance, 1),
        'pace_gap_seconds': pace_gap,
        'weeks_to_go': None  # À calculer si target_date défini
    }

    # Ajouter focus semaine
    program['summary']['focus'] = week_summary_text or "Maintenir qualité et volume"

    return program


def check_and_recalibrate_objectives(profile, activities, past_week_analysis):
    """
    Vérifie si les objectifs doivent être recalibrés et les ajuste si nécessaire.

    Déclencheurs:
    1. Objectifs atteints (k/drift < target pendant 2 semaines)
    2. Stagnation (4 semaines consécutives avec score < 7 ET pas de progrès)

    Returns:
        dict: {'recalibrated': bool, 'changes': [], 'reason': str}
    """
    personalized_targets = profile.get('personalized_targets', {})
    if not personalized_targets:
        return {'recalibrated': False, 'reason': 'Pas d\'objectifs définis'}

    # Charger historique des scores (dernières 8 semaines)
    scores_history = []
    try:
        scores_data = read_output_json('weekly_scores.json') or {}
        scores_history = scores_data.get('scores', [])[-8:]  # 8 dernières semaines
    except:
        pass

    # DÉCLENCHEUR 1: Objectifs atteints
    # Vérifier les 10 derniers runs de chaque type
    objectives_met = {}
    for run_type, targets in personalized_targets.items():
        k_target = targets.get('k_target')
        drift_target = targets.get('drift_target')

        if not k_target or not drift_target:
            continue

        # Prendre les 10 derniers runs de ce type
        type_runs = [act for act in activities
                     if act.get('session_category') == run_type
                     or act.get('type_sortie') == run_type][:10]

        if len(type_runs) >= 5:
            k_values = [act.get('k_moy') for act in type_runs if act.get('k_moy')]
            drift_values = [act.get('deriv_cardio') for act in type_runs if act.get('deriv_cardio')]

            if k_values and drift_values:
                avg_k = sum(k_values) / len(k_values)
                avg_drift = sum(drift_values) / len(drift_values)

                # Objectif atteint si moyenne < cible
                k_met = avg_k <= k_target
                drift_met = avg_drift <= drift_target

                objectives_met[run_type] = {
                    'k_met': k_met,
                    'drift_met': drift_met,
                    'both_met': k_met and drift_met,
                    'avg_k': avg_k,
                    'avg_drift': avg_drift
                }

    # Compter combien de types ont atteint leurs objectifs
    types_met = [t for t, m in objectives_met.items() if m.get('both_met')]

    if len(types_met) >= 2:
        # Au moins 2 types ont atteint objectifs → RESSERRER
        changes = []
        for run_type in types_met:
            old_k = personalized_targets[run_type]['k_target']
            old_drift = personalized_targets[run_type]['drift_target']

            # Resserrer de 5%
            new_k = round(old_k * 0.95, 2)
            new_drift = round(old_drift * 0.95, 2)

            personalized_targets[run_type]['k_target'] = new_k
            personalized_targets[run_type]['drift_target'] = new_drift

            changes.append(f"{run_type}: k {old_k}→{new_k}, drift {old_drift}→{new_drift}")

        # Sauvegarder
        save_profile_local(profile)
        invalidate_profile_cache()

        return {
            'recalibrated': True,
            'reason': 'Objectifs atteints',
            'types': types_met,
            'changes': changes
        }

    # DÉCLENCHEUR 2: Stagnation (4 semaines score < 7)
    if len(scores_history) >= 4:
        recent_scores = [s.get('score', 0) for s in scores_history[-4:]]
        if all(s < 7.0 for s in recent_scores):
            # 4 semaines avec score < 7 → Objectifs trop ambitieux, RELÂCHER
            changes = []
            for run_type, targets in personalized_targets.items():
                old_k = targets.get('k_target', 5.0)
                old_drift = targets.get('drift_target', 1.1)

                # Relâcher de 3%
                new_k = round(old_k * 1.03, 2)
                new_drift = round(old_drift * 1.03, 2)

                personalized_targets[run_type]['k_target'] = new_k
                personalized_targets[run_type]['drift_target'] = new_drift

                changes.append(f"{run_type}: k {old_k}→{new_k}, drift {old_drift}→{new_drift}")

            # Sauvegarder
            save_profile_local(profile)
            invalidate_profile_cache()

            return {
                'recalibrated': True,
                'reason': 'Stagnation détectée (4 semaines < 7/10)',
                'changes': changes
            }

    return {'recalibrated': False, 'reason': 'Pas de recalibrage nécessaire'}


# --- Phase 3 Sprint 5: Analyse Progression ---

def analyze_progression(activities, weeks=4):
    """
    Analyse la progression sur X semaines.

    Args:
        activities: Liste des activités (triées par date décroissante)
        weeks: Nombre de semaines à analyser (défaut 4)

    Returns:
        dict: Analyse de progression avec tendances par type
    """
    # Calculer date limite (X semaines en arrière)
    today = datetime.now()
    cutoff_date = today - timedelta(weeks=weeks)

    # Filtrer activités récentes
    recent_activities = []
    for act in activities:
        date_str = act.get('date', '')
        if date_str:
            try:
                # Parse ISO format: 2025-11-09T11:28:42Z
                # Retirer timezone pour comparaison simple
                if 'T' in date_str:
                    date_only = date_str.split('T')[0]
                else:
                    date_only = date_str[:10]
                act_date = datetime.strptime(date_only, '%Y-%m-%d')
                if act_date >= cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0):
                    recent_activities.append(act)
            except ValueError:
                continue

    if len(recent_activities) < 3:
        return {
            'period': f'{weeks} weeks',
            'runs_completed': len(recent_activities),
            'insufficient_data': True,
            'message': f'Au moins 3 runs nécessaires pour analyser la progression (trouvé: {len(recent_activities)})'
        }

    # Grouper par type de séance
    by_type = {}
    for act in recent_activities:
        type_sortie = act.get('type_sortie', 'inconnu')
        if type_sortie not in by_type:
            by_type[type_sortie] = []
        by_type[type_sortie].append(act)

    # Analyser chaque type
    type_analysis = {}
    for type_sortie, acts in by_type.items():
        if len(acts) < 2:
            continue  # Besoin d'au moins 2 runs pour calculer tendance

        # Extraire métriques (ordre chronologique inversé car activities est décroissant)
        acts_chrono = list(reversed(acts))  # Du plus ancien au plus récent

        paces = [act.get('pace_min_per_km', 0) for act in acts_chrono if act.get('pace_min_per_km')]
        fcs = [act.get('fc_moy', 0) for act in acts_chrono if act.get('fc_moy')]
        drifts = [act.get('deriv_cardio', 0) for act in acts_chrono if act.get('deriv_cardio')]

        # Calculer tendances (dernière valeur - première valeur)
        pace_trend = 0
        fc_trend = 0
        drift_trend = 0

        if len(paces) >= 2:
            # Moyenne 2 premiers vs moyenne 2 derniers
            first_half = paces[:len(paces)//2]
            second_half = paces[len(paces)//2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            pace_trend = avg_second - avg_first  # Négatif = amélioration

        if len(fcs) >= 2:
            first_half = fcs[:len(fcs)//2]
            second_half = fcs[len(fcs)//2:]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            fc_trend = avg_second - avg_first  # Négatif = amélioration

        if len(drifts) >= 2:
            first_half = drifts[:len(drifts)//2]
            second_half = drifts[len(drifts)//2:]
            avg_first = sum(first_half) / len(first_half) if first_half else 0
            avg_second = sum(second_half) / len(second_half) if second_half else 0
            drift_trend = avg_second - avg_first  # Négatif = amélioration

        # Déterminer tendance globale pour ce type
        trend = "stable"
        if pace_trend < -0.05:  # Au moins 3 sec/km plus rapide
            if fc_trend <= 0:  # FC stable ou en baisse
                trend = "improving"
            else:
                trend = "faster_but_harder"  # Plus rapide mais FC plus élevée
        elif pace_trend > 0.05:  # Au moins 3 sec/km plus lent
            trend = "declining"

        type_analysis[type_sortie] = {
            'count': len(acts),
            'avg_pace_trend': pace_trend,
            'avg_fc_trend': fc_trend,
            'avg_drift_trend': drift_trend,
            'trend': trend,
            'recent_avg_pace': sum(paces[-3:]) / len(paces[-3:]) if len(paces) >= 3 else (paces[-1] if paces else 0),
            'recent_avg_fc': sum(fcs[-3:]) / len(fcs[-3:]) if len(fcs) >= 3 else (fcs[-1] if fcs else 0)
        }

    # Calculer tendance globale
    improving_count = sum(1 for t in type_analysis.values() if t['trend'] == 'improving')
    declining_count = sum(1 for t in type_analysis.values() if t['trend'] == 'declining')

    overall_trend = "stable"
    if improving_count > declining_count:
        overall_trend = "improving"
    elif declining_count > improving_count:
        overall_trend = "declining"

    # Calculer fitness score (0-10)
    # Basé sur: nombre de runs, variété, tendances
    fitness_score = 5.0  # Base

    # Bonus runs réguliers
    runs_per_week = len(recent_activities) / weeks
    if runs_per_week >= 3:
        fitness_score += 1.0
    elif runs_per_week >= 2:
        fitness_score += 0.5

    # Bonus variété
    type_variety = len(by_type)
    if type_variety >= 3:
        fitness_score += 0.5

    # Bonus/malus tendances
    fitness_score += 1.0 * improving_count
    fitness_score -= 0.5 * declining_count

    # Cap 0-10
    fitness_score = max(0, min(10, fitness_score))

    return {
        'period': f'{weeks} weeks',
        'runs_completed': len(recent_activities),
        'runs_per_week': round(runs_per_week, 1),
        'type_variety': type_variety,
        'by_type': type_analysis,
        'overall_trend': overall_trend,
        'fitness_score': round(fitness_score, 1),
        'fitness_change': 0.0  # Placeholder pour comparaison future
    }


@app.route("/")
def index():
    start_time = time.time()
    log_step("Début index()", start_time)
    print("➡ index(): start")

    # --- Drive-only guard ---
    try:
        activities = load_activities_from_drive()
        print(f"➡ activities loaded: {len(activities)}")
    except DriveUnavailableError as e:
        print("❌ load_activities_from_drive failed:", e)
        return render_template(
            "index.html",
            dashboard={},
            activities_for_carousel=[],
            drive_error=f"⚠️ Données indisponibles (Drive) : {e}",
        )

    # ⚡ OPTIMISATION : Désactiver les traitements lourds au chargement de la page
    # Ces traitements peuvent être lancés manuellement via /refresh

    modified = False

    # 👣 Normalisation cadence (rapide, local)
    activities, changed_norm = normalize_cadence_in_place(activities)
    modified = modified or changed_norm

    # 📊 Enrichissement intelligent : calculer type_sortie, k_moy et deriv_cardio SEULEMENT pour les activités manquantes
    fc_max_fractionnes = get_fcmax_from_fractionnes(activities)
    enriched_count = 0
    type_count = 0
    for idx, activity in enumerate(activities):
        # 1) Classifier uniquement si type manquant ou invalide (OPTIMISATION)
        old_type = activity.get("type_sortie")
        needs_classification = not old_type or old_type in ['-', 'inconnue', 'normal_5k', 'normal_10k']

        if needs_classification:
            new_type = classify_run_type(activity)
            if old_type != new_type:
                activity["type_sortie"] = new_type
                print(f"🔄 Reclassification {activity.get('date')}: {old_type} → {new_type} (dist: {activity.get('distance_km')}km)")
                type_count += 1
                modified = True
                # Effacer session_category uniquement si le type a changé
                if 'session_category' in activity:
                    del activity['session_category']

        # 2) Enrichir si k_moy ou deriv_cardio manquants
        if (not isinstance(activity.get("k_moy"), (int, float)) or
            not isinstance(activity.get("deriv_cardio"), (int, float))):
            activities[idx] = enrich_single_activity(activity, fc_max_fractionnes)
            enriched_count += 1
            modified = True

    if enriched_count > 0 or type_count > 0:
        print(f"📊 {enriched_count} activités enrichies (k_moy, deriv_cardio), {type_count} types définis")

    if modified:
        save_activities_to_drive(activities)
        print("💾 activities.json mis à jour")

    # 🔽 Tri décroissant par date pour fiabiliser dashboard + carrousel
    activities_sorted = sorted(activities, key=_date_key, reverse=True)

    # 📊 Ajouter contexte historique (moyennes 10 dernières, tendances) - APRÈS le tri!
    activities_sorted = add_historical_context(activities_sorted)
    print("📊 Contexte historique ajouté (k_avg_10, drift_avg_10, tendances)")


    log_step("Activities chargées et complétées", start_time)
    print(f"📂 {len(activities)} activités prêtes")

    # Calcul du dashboard
    dashboard = compute_dashboard_data(activities_sorted)
    log_step("Dashboard calculé", start_time)

    # Charger le profil (nécessaire pour analyse cardiaque et commentaires IA)
    profile = load_profile()

    # 💓 Calculer LTHR (Lactate Threshold Heart Rate) depuis les 10 derniers runs >7km
    lthr_data = calculate_lthr(activities_sorted, profile)
    if lthr_data['status'] == 'ok':
        # Sauvegarder le LTHR dans le profil
        old_lthr = profile.get('lthr')
        profile['lthr'] = lthr_data['lthr']
        profile['lthr_calculated_from'] = lthr_data['calculated_from']
        profile['lthr_percentage'] = lthr_data['lthr_percentage']
        profile['lthr_zone'] = lthr_data['lthr_zone']

        # Sauvegarder toujours (pour s'assurer que la première fois fonctionne)
        save_profile_local(profile)
        invalidate_profile_cache()  # Invalider cache après modification
        if old_lthr != lthr_data['lthr']:
            print(f"💓 LTHR calculé et sauvegardé: {lthr_data['lthr']} bpm (Zone {lthr_data['lthr_zone']}, {lthr_data['lthr_percentage']:.1f}% réserve, basé sur {lthr_data['calculated_from']} runs)")
        else:
            print(f"💓 LTHR confirmé: {lthr_data['lthr']} bpm (inchangé)")
    else:
        print(f"⚠️ LTHR non calculé: {lthr_data['status']}")

    # 🎯 Charger les objectifs personnalisés depuis le profil
    # Note: Les objectifs sont maintenant gérés via /objectifs et ne sont plus recalculés automatiquement
    personalized_targets = profile.get('personalized_targets', {})
    print(f"🎯 Objectifs chargés: {personalized_targets}")

    # Charger les feedbacks
    feedbacks = load_feedbacks()

    # 🆕 Charger les commentaires IA sauvegardés
    ai_comments = load_ai_comments()
    zones_comments = load_zones_comments()

    # Construction du carrousel
    activities_for_carousel = []
    print("➡ building carousel from most recent", min(10, len(activities_sorted)), "activities")
    for act in activities_sorted[:10]:  # 10 plus récentes par date
        log_step(f"Début carrousel activité {act.get('date')}", start_time)
        print("   slide candidate:", act.get('date'))
        points = act.get("points", [])
        print("   -> points:", len(points))
        if not points:
            print("   -> skipped (no points)")
            continue

        labels = [round(p["distance"] / 1000, 3) for p in points]
        points_fc = [p.get("hr", 0) for p in points]
        points_alt = [p.get("alt", 0) - points[0].get("alt", 0) for p in points]

        # Calcul allure_curve tous les 500m
        allure_curve = []
        bloc_start_idx, next_bloc_dist, last_allure = 0, 500, None
        for i, p in enumerate(points):
            if p["distance"] >= next_bloc_dist or i == len(points) - 1:
                bloc_points = points[bloc_start_idx:i + 1]
                bloc_dist = bloc_points[-1]["distance"] - bloc_points[0]["distance"]
                bloc_time = bloc_points[-1]["time"] - bloc_points[0]["time"]
                if bloc_dist > 0:
                    last_allure = (bloc_time / 60) / (bloc_dist / 1000)
                allure_curve.extend([last_allure] * len(bloc_points))
                bloc_start_idx = i + 1
                next_bloc_dist += 500
        while len(allure_curve) < len(points):
            allure_curve.append(last_allure)

        # Statistiques globales
        total_dist_km = points[-1]["distance"] / 1000
        total_time_min = (points[-1]["time"] - points[0]["time"]) / 60
        allure_moy = total_time_min / total_dist_km if total_dist_km > 0 else None
        fc_max = max(points_fc) if points_fc else None
        gain_alt = _compute_denivele_pos(points)

        # 🌡️ Météo
        avg_temperature = act.get("avg_temperature")
        weather_code = act.get("weather_code")
        weather_emoji = WEATHER_CODE_MAP.get(weather_code, "❓")

        # Date formatée
        try:
            date_str = act.get("date", "")
            if date_str:
                # Utiliser parser.isoparse qui gère "Z" (UTC)
                date_parsed = parser.isoparse(date_str)
                date_formatted = date_parsed.strftime("%Y-%m-%d")
            else:
                date_formatted = "-"
        except Exception as e:
            print(f"⚠️ Erreur parsing date {act.get('date')}: {e}")
            date_formatted = "-"
            
        # 👣 KPIs de cadence (à partir de cad_spm)
        cad_kpis = _cadence_kpis(points)

        # 📊 Historiques et comparaisons (10 derniers runs du MÊME type)
        current_type = act.get("session_category") or act.get("type_sortie", "-")
        current_idx = activities_sorted.index(act)

        # Filtrer les runs du même type (activités précédentes)
        same_type_runs = []
        for prev_act in activities_sorted[current_idx + 1:]:
            prev_type = prev_act.get("session_category") or prev_act.get("type_sortie")
            if prev_type == current_type:
                same_type_runs.append(prev_act)
            if len(same_type_runs) >= 10:
                break

        # Historique dérive cardiaque (10 derniers du même type)
        drift_history = []
        for prev_act in same_type_runs:
            deriv = prev_act.get("deriv_cardio")
            if isinstance(deriv, (int, float)):
                drift_history.append(deriv)
        drift_history.reverse()  # Du plus ancien au plus récent

        # Historique k_moy (10 derniers du même type)
        k_history = []
        for prev_act in same_type_runs:
            k = prev_act.get("k_moy")
            if isinstance(k, (int, float)):
                k_history.append(k)
        k_history.reverse()

        # Comparaisons (moyennes des 10 derniers - sans la valeur actuelle)
        k_moy_current = act.get("k_moy")
        deriv_current = act.get("deriv_cardio")

        k_comparison = None
        if k_history and isinstance(k_moy_current, (int, float)):
            k_avg = np.mean(k_history)
            k_diff_pct = ((k_moy_current - k_avg) / k_avg) * 100 if k_avg != 0 else 0
            if k_diff_pct > 5:
                k_comparison = f"↗ +{k_diff_pct:.0f}% vs moy"
            elif k_diff_pct < -5:
                k_comparison = f"↘ {k_diff_pct:.0f}% vs moy"
            else:
                k_comparison = f"→ Similaire"

        drift_comparison = None
        if drift_history and isinstance(deriv_current, (int, float)):
            drift_avg = np.mean(drift_history)
            drift_diff_pct = ((deriv_current - drift_avg) / drift_avg) * 100 if drift_avg != 0 else 0
            if drift_diff_pct > 5:
                drift_comparison = f"↗ +{drift_diff_pct:.0f}% vs moy"
            elif drift_diff_pct < -5:
                drift_comparison = f"↘ {drift_diff_pct:.0f}% vs moy"
            else:
                drift_comparison = f"→ Similaire"

        # Ajouter la valeur du run actuel à la fin (pour affichage sparkline)
        if isinstance(k_moy_current, (int, float)):
            k_history.append(k_moy_current)
        if isinstance(deriv_current, (int, float)):
            drift_history.append(deriv_current)

        drift_history_last20 = json.dumps(drift_history) if len(drift_history) >= 2 else None
        k_history_last20 = json.dumps(k_history) if len(k_history) >= 2 else None

        # Format temps mm:ss au lieu de décimales
        duration_mmss = f"{int(total_time_min)}:{int((total_time_min - int(total_time_min)) * 60):02d}"

        # 🆕 Phase 3: Calcul segments, patterns, comparaisons, santé cardiaque et commentaires IA
        segments = compute_segments(act)
        print(f"   📊 Segments calculés: {len(segments) if segments else 0}")

        patterns = detect_segment_patterns(segments) if segments else []
        print(f"   🔍 Patterns détectés: {len(patterns) if patterns else 0}")

        segment_comparisons = calculate_segment_comparisons(act, activities_sorted, segments) if segments else None
        cardiac_analysis = analyze_cardiac_health(act, profile)
        print(f"   ❤️ Analyse cardiaque: {cardiac_analysis.get('status') if cardiac_analysis else 'N/A'}")

        # 📊 Zones FC - Calculer zones réelles + moyenne des 10 derniers
        zones_reel_dict = {}
        zones_avg_dict = {}

        # Zones réelles du run actuel
        if cardiac_analysis and cardiac_analysis.get('hr_zones'):
            hr_zones = cardiac_analysis['hr_zones']
            zone_pcts = hr_zones.get('zone_percentages', {})
            for z in range(1, 6):
                # Support both integer keys (from fresh analyze_cardiac_health()) and string keys (from JSON)
                zones_reel_dict[z] = zone_pcts.get(z, zone_pcts.get(str(z), 0))

        # Calculer moyenne zones des 10 derniers runs du même type
        if current_type and current_type != "-" and len(same_type_runs) > 0:
            same_type_zones = {1: [], 2: [], 3: [], 4: [], 5: []}

            for prev_act in same_type_runs:
                # Recalculer zones FC depuis les points HR
                if prev_act.get('points'):
                    prev_cardiac = analyze_cardiac_health(prev_act, profile)
                    if prev_cardiac and prev_cardiac.get('hr_zones'):
                        prev_zones = prev_cardiac['hr_zones'].get('zone_percentages', {})
                        for z in range(1, 6):
                            # Support both integer keys (from fresh analyze_cardiac_health()) and string keys (from JSON)
                            pct = prev_zones.get(z, prev_zones.get(str(z), 0))
                            if pct > 0:
                                same_type_zones[z].append(pct)

            # Calculer moyennes
            for z in range(1, 6):
                if same_type_zones[z]:
                    zones_avg_dict[z] = sum(same_type_zones[z]) / len(same_type_zones[z])
                else:
                    zones_avg_dict[z] = 0

            zones_avg_str = ", ".join([f"Z{z}: {zones_avg_dict.get(z, 0):.1f}%" for z in range(1, 6)])
            print(f"   📊 Zones moyennes calculées (10 derniers {current_type}): {zones_avg_str}")

        # Feedback par défaut (sera remplacé par feedback utilisateur quand disponible)
        feedback = act.get('feedback', {
            'rating_stars': 3,
            'difficulty': 3,
            'legs_feeling': 'normal',
            'cardio_feeling': 'normal',
            'enjoyment': 'normal',
            'notes': '',
            'mode_run': 'training'  # Par défaut: entraînement
        })

        # 🆕 Charger le commentaire zones FC sauvegardé s'il existe
        # Génération IA désactivée au chargement (généré via bouton "Générer commentaire IA")
        zones_analysis_comment = zones_comments.get(act.get("date"), {}).get("comment", "") if zones_comments and act.get("date") in zones_comments else ""

        # Génération commentaire IA désactivée (trop lent au chargement)
        ai_comment = ""

        # Récupérer le feedback de l'activité
        activity_id = str(act.get('activity_id', ''))
        feedback = feedbacks.get(activity_id, {})

        activities_for_carousel.append({
            "date": date_formatted,
            "date_iso": act.get("date"),  # Date ISO complète pour les routes
            "type_sortie": act.get("type_sortie", "-"),
            "session_category": act.get("session_category"),  # Nouveau système de classification
            "is_fractionne": act.get("is_fractionne", False),
            "fractionne_prob": act.get("fractionne_prob", 0.0),
            "distance_km": round(total_dist_km, 2),
            "duration_min": round(total_time_min, 1),
            "duration_mmss": duration_mmss,
            "fc_moy": round(np.mean(points_fc), 1) if points_fc else "-",
            "fc_max": fc_max,
            "allure": f"{int(allure_moy)}:{int((allure_moy - int(allure_moy)) * 60):02d}" if allure_moy else "-",
            "gain_alt": gain_alt,
            "k_moy": act.get("k_moy", "-"),
            "deriv_cardio": round(act.get("deriv_cardio"), 2) if isinstance(act.get("deriv_cardio"), (int, float)) else "-",
            "drift_history_last20": drift_history_last20,
            "k_history_last20": k_history_last20,
            "k_comparison": k_comparison or "Pas de comparaison",
            "drift_comparison": drift_comparison or "Pas de comparaison",
            # Moyennes et tendances historiques
            "k_avg_10": act.get("k_avg_10"),
            "drift_avg_10": act.get("drift_avg_10"),
            "k_trend": act.get("k_trend", 0),
            "drift_trend": act.get("drift_trend", 0),
            "session_category": act.get("session_category"),
            # Intervalles 80% (P10-P90)
            "k_p10": act.get("k_p10"),
            "k_p90": act.get("k_p90"),
            "drift_p10": act.get("drift_p10"),
            "drift_p90": act.get("drift_p90"),
            "temperature": avg_temperature,
            "weather_emoji": weather_emoji,
            "labels": json.dumps(labels),
            "points_fc": json.dumps(points_fc),
            "points_alt": json.dumps(points_alt),
            "allure_curve": json.dumps(allure_curve),
            "cad_mean_spm": cad_kpis["cad_mean_spm"],
            "cad_cv_pct": cad_kpis["cad_cv_pct"],
            "cad_drift_spm_per_h": cad_kpis["cad_drift_spm_per_h"],

            # 🆕 Phase 3: Données segments, patterns, comparaisons, santé cardiaque et IA
            "segments": segments or [],
            "patterns": patterns or [],
            "segment_comparisons": segment_comparisons,
            "cardiac_analysis": cardiac_analysis,
            # 🆕 Charger le commentaire IA sauvegardé s'il existe
            "ai_comment": ai_comments.get(act.get("date"), {}).get("comment", "") if act.get("date") in ai_comments else "",
            "ai_comment_saved": act.get("date") in ai_comments,
            "ai_comment_segments": ai_comments.get(act.get("date"), {}).get("segments_count", 0) if act.get("date") in ai_comments else 0,
            "ai_comment_patterns": ai_comments.get(act.get("date"), {}).get("patterns_count", 0) if act.get("date") in ai_comments else 0,
            "feedback": feedback,
            # 📊 Zones FC - Distribution réelle + moyenne 10 derniers
            "zones_reel": zones_reel_dict,
            "zones_avg": zones_avg_dict,
            "zones_analysis_comment": zones_analysis_comment,

        })

    print("➡ activities_for_carousel count:", len(activities_for_carousel))

    # 🆕 Charger les running stats par type de run
    running_stats = {}
    stats_file = 'running_stats.json'
    if os.path.exists(stats_file):
        try:
            with open(stats_file, 'r') as f:
                running_stats = json.load(f)
            print(f"✅ Running stats chargées depuis {stats_file}")
            print(f"🔍 Keys in running_stats: {list(running_stats.keys())}")
            if 'stats_by_type' in running_stats:
                print(f"🔍 Types disponibles: {list(running_stats['stats_by_type'].keys())}")
        except Exception as e:
            print(f"⚠️ Erreur lecture running_stats.json: {e}")
    else:
        # Si le fichier n'existe pas, le générer
        print("📊 running_stats.json absent, génération...")
        update_running_stats_after_webhook()
        if os.path.exists(stats_file):
            with open(stats_file, 'r') as f:
                running_stats = json.load(f)

    # Phase 3 Sprint 3: Programme hebdomadaire (profile déjà chargé plus haut)
    # 🔄 Logique de renouvellement hebdomadaire
    today = date.today()
    current_week_number = today.isocalendar()[1]

    # Charger le programme existant s'il existe
    try:
        existing_program = read_weekly_plan()
        existing_week = existing_program.get('week_number') if existing_program else None
    except Exception:
        existing_program = None
        existing_week = None

    # Vérifier si on doit régénérer le programme
    # Ne pas régénérer si le programme existant est pour une semaine future (transition manuelle)
    should_regenerate = False
    if existing_program is None:
        should_regenerate = True
    elif existing_week < current_week_number:
        # Programme pour une semaine passée, on doit régénérer
        should_regenerate = True
    elif existing_week == current_week_number:
        # Programme pour la semaine actuelle, on garde
        should_regenerate = False
    else:
        # existing_week > current_week_number : Programme pour une semaine future (transition manuelle), on garde
        should_regenerate = False

    if should_regenerate:
        print(f"📅 Génération nouveau programme hebdomadaire (semaine {current_week_number})")
        weekly_program = generate_weekly_program(profile, activities)
        write_weekly_plan(weekly_program)
        print(f"💾 Programme hebdomadaire sauvegardé pour semaine {current_week_number}")

        # Si on change de semaine, on analyse la semaine précédente
        past_week_analysis = None
        past_week_comment = None
        if existing_week is not None and existing_week != current_week_number:
            print(f"📊 Analyse semaine précédente (semaine {existing_week})...")
            past_week_analysis = analyze_past_week(existing_program, activities_sorted, profile)
            if past_week_analysis:
                print(f"✅ Semaine {existing_week}: {past_week_analysis['runs_completed']}/{past_week_analysis['total_programmed']} runs réalisés ({past_week_analysis['adherence_rate']}% adhésion)")
                # Générer commentaire IA sur la semaine écoulée
                past_week_comment = generate_past_week_comment(past_week_analysis)
                if past_week_comment:
                    print(f"🤖 Commentaire semaine écoulée généré: {past_week_comment[:50]}...")
                    # Sauvegarder le bilan pour l'afficher toute la semaine
                    past_week_analysis['comment'] = past_week_comment
                    write_output_json('past_week_analysis.json', past_week_analysis)
                    print(f"💾 Bilan semaine {existing_week} sauvegardé")

                    # NOUVEAU: Sauvegarder le score dans l'historique
                    try:
                        scores_data = read_output_json('weekly_scores.json') or {'scores': []}
                        scores_data['scores'].append({
                            'week': past_week_analysis['week_number'],
                            'week_start': past_week_analysis['start_date'],
                            'score': past_week_analysis.get('score', 0),
                            'trend': past_week_analysis.get('trend', 'stable')
                        })
                        # Garder seulement les 12 dernières semaines
                        scores_data['scores'] = scores_data['scores'][-12:]
                        write_output_json('weekly_scores.json', scores_data)
                        print(f"📊 Score {past_week_analysis.get('score', 0)}/10 sauvegardé dans l'historique")
                    except Exception as e:
                        print(f"⚠️ Erreur sauvegarde score: {e}")

                    # NOUVEAU: Vérifier si recalibrage nécessaire
                    try:
                        recalibration_result = check_and_recalibrate_objectives(profile, activities_sorted, past_week_analysis)
                        if recalibration_result['recalibrated']:
                            print(f"🎯 RECALIBRAGE AUTO: {recalibration_result['reason']}")
                            for change in recalibration_result.get('changes', []):
                                print(f"   → {change}")
                            # Ajouter notification dans le bilan
                            past_week_analysis['recalibration'] = recalibration_result
                            write_output_json('past_week_analysis.json', past_week_analysis)
                    except Exception as e:
                        print(f"⚠️ Erreur recalibrage: {e}")

                else:
                    past_week_comment = None
                    print(f"⚠️ Impossible de générer le commentaire IA pour la semaine {existing_week}")
            else:
                print(f"⚠️ Impossible d'analyser la semaine {existing_week}")
        else:
            # Pas de changement de semaine, mais charger le bilan sauvegardé s'il existe
            # Le bilan doit être de la semaine AVANT le programme en cours (existing_week - 1)
            try:
                saved_analysis = read_output_json('past_week_analysis.json')
                expected_week = existing_week - 1 if existing_week else None
                if saved_analysis and expected_week and saved_analysis.get('week_number') == expected_week:
                    past_week_analysis = saved_analysis
                    past_week_comment = saved_analysis.get('comment')
                    print(f"📋 Bilan semaine {saved_analysis.get('week_number')} chargé depuis cache (programme semaine {existing_week})")
            except Exception:
                pass
    else:
        # Réutiliser le programme existant
        weekly_program = existing_program
        # Charger le bilan sauvegardé s'il existe
        past_week_analysis = None
        past_week_comment = None
        try:
            saved_analysis = read_output_json('past_week_analysis.json')
            # Vérifier que le bilan sauvegardé est pour la semaine précédente (par rapport au programme actuel)
            if saved_analysis and saved_analysis.get('week_number') == existing_week - 1:
                past_week_analysis = saved_analysis
                past_week_comment = saved_analysis.get('comment')
                print(f"📋 Bilan semaine {saved_analysis.get('week_number')} chargé depuis cache (programme réutilisé)")
        except Exception:
            pass
        print(f"♻️ Réutilisation programme existant (semaine {current_week_number})")

    print(f"📅 Programme hebdomadaire généré: {len(weekly_program['runs'])} runs, {weekly_program['summary']['total_distance']} km total")

    # Phase 3 Sprint 5: Analyse progression
    progression_analysis = analyze_progression(activities, weeks=4)
    print(f"📈 Analyse progression: {progression_analysis['runs_completed']} runs, score {progression_analysis.get('fitness_score', 'N/A')}/10")

    # 👟 Calcul kilométrage chaussures
    shoe_km, shoe_status = calculate_shoe_kilometers(activities_sorted, profile)
    print(f"👟 Chaussures: {shoe_km} km, statut: {shoe_status}")

    # 🆕 Lire le numéro de version depuis VERSION file
    try:
        version_path = os.path.join(os.path.dirname(__file__), 'VERSION')
        with open(version_path, 'r') as f:
            app_version = f.read().strip()
    except (FileNotFoundError, OSError):
        app_version = "unknown"

    # ✅ Vérifier complétion profil et objectifs
    profile_completion = check_profile_completion(profile)
    objectives_completion = check_objectives_completion(profile)
    print(f"✅ Profil: {profile_completion['percentage']}% complet")
    print(f"✅ Objectifs: {objectives_completion['percentage']}% complets")

    return render_template(
        "index.html",
        dashboard=dashboard,
        activities_for_carousel=activities_for_carousel,
        running_stats=running_stats,
        weekly_program=weekly_program,  # Phase 3 Sprint 3
        progression_analysis=progression_analysis,  # Phase 3 Sprint 5
        shoe_km=shoe_km,  # Kilométrage chaussures
        shoe_status=shoe_status,  # Statut d'usure chaussures
        personalized_targets=personalized_targets,  # 🎯 Objectifs personnalisés k et drift
        past_week_analysis=past_week_analysis,  # 📊 Analyse semaine écoulée (réalisé vs programmé)
        past_week_comment=past_week_comment,  # 🤖 Commentaire IA sur semaine écoulée
        app_version=app_version,  # 🆕 Numéro de version
        profile=load_profile(),  # 👤 Profil utilisateur pour personnalisation
        profile_completion=profile_completion,  # ✅ Complétion profil
        objectives_completion=objectives_completion  # ✅ Complétion objectifs
    )


@app.route('/generate_ai_comment/<activity_date>')
def generate_ai_comment(activity_date):
    """
    Génère un commentaire IA pour une activité spécifique à la demande.

    Args:
        activity_date: Date de l'activité au format ISO (ex: 2025-11-09T11:28:42Z)

    Returns:
        JSON avec le commentaire IA ou une erreur
    """
    try:
        # Charger profil et activités
        profile = load_profile()
        activities = load_activities_from_drive()

        # Trouver l'activité correspondante AVANT d'enrichir (OPTIMISATION)
        activity = None
        for act in activities:
            if act.get('date') == activity_date:
                activity = act
                break

        if not activity:
            return jsonify({'error': 'Activité non trouvée'}), 404

        # ✅ VALIDATION : Vérifier que l'activité a des données GPS valides
        # Support des 2 formats : ancien (lat_stream/lon_stream) et nouveau (points array)
        lat_stream = activity.get('lat_stream', [])
        lon_stream = activity.get('lon_stream', [])
        points = activity.get('points', [])

        # Vérifier l'ancien format (streams) OU le nouveau format (points)
        has_old_format = lat_stream and lon_stream and len(lat_stream) >= 10 and len(lon_stream) >= 10
        has_new_format = points and len(points) >= 10

        if not has_old_format and not has_new_format:
            return jsonify({
                'error': '❌ Cette activité n\'a pas de données GPS valides (synchronisation Strava incomplète)',
                'needs_gps': True
            }), 400

        # L'activité est déjà enrichie via enrich_activities() plus haut
        # Juste vérifier que le type est bien défini
        if activity.get("type_sortie") in (None, "-", "inconnue"):
            activity["type_sortie"] = classify_run_type(activity)
            print(f"🏃 Type de séance détecté: {activity['type_sortie']}")

        # ✅ VALIDATION : Vérifier que l'allure est valide après enrichissement
        allure = activity.get('allure')
        if not allure or allure == '-:--' or allure == '-' or allure == 'N/A':
            return jsonify({
                'error': '❌ Impossible de calculer l\'allure pour cette activité (données GPS insuffisantes)',
                'needs_pace': True
            }), 400

        # Le profil est déjà chargé plus haut

        # Calculer segments et patterns
        segments = compute_segments(activity)
        if not segments:
            return jsonify({'error': 'Impossible de calculer les segments (run trop court?)'}), 400

        patterns = detect_segment_patterns(segments)

        # Calculer comparaisons et analyse cardiaque
        segment_comparisons = calculate_segment_comparisons(activity, activities, segments)
        cardiac_analysis = analyze_cardiac_health(activity, profile)

        # Charger les feedbacks réels
        feedbacks = load_feedbacks()
        activity_id = str(activity.get('activity_id', ''))
        feedback = feedbacks.get(activity_id, {
            'rating_stars': 3,
            'difficulty': 3,
            'legs_feeling': 'normal',
            'cardio_feeling': 'normal',
            'enjoyment': 'normal',
            'notes': ''
        })
        
        # 🆕 Vérifier que le feedback a été rempli avant de générer le commentaire principal
        if activity_id not in feedbacks:
            return jsonify({
                'error': 'Veuillez d\'abord remplir le ressenti de la séance avant de générer le commentaire IA.',
                'needs_feedback': True
            }), 400
        
        if activity_id in feedbacks:
            print(f"✅ Feedback chargé pour activité {activity_id}")

        # Vérifier que le client Gemini est disponible
        if not gemini_client:
            return jsonify({'error': 'Service IA temporairement indisponible (API key manquante)'}), 503

        # 🆕 Générer le commentaire IA avec nouveau prompt coaching
        print(f"🤖 Génération commentaire IA coaching pour {activity_date}...")
        ai_comment = generate_coaching_comment(
            activity, feedback, profile, activities, cardiac_analysis
        )
        print(f"✅ Commentaire coaching généré: {len(ai_comment)} caractères")

        # 🆕 Sauvegarder le commentaire généré
        save_ai_comment(activity_date, ai_comment, len(segments), len(patterns))

        # 🎯 Parser et sauvegarder les objectifs si c'est le dernier run de la semaine
        is_last_run = feedback.get('is_last_run_of_week', False)
        if is_last_run:
            try:
                # Extraire le numéro de semaine depuis la date
                run_date = datetime.strptime(activity_date[:10], '%Y-%m-%d')
                next_week = run_date.isocalendar()[1] + 1
                if next_week > 52:
                    next_week = 1

                # Parser les objectifs depuis le HTML généré
                objectives = parse_weekly_objectives_from_html(ai_comment, next_week)
                if objectives:
                    write_weekly_objectives(next_week, objectives)
                    print(f"🎯 Objectifs semaine {next_week} extraits et sauvegardés")
            except Exception as e:
                print(f"⚠️ Erreur extraction objectifs: {e}")

        return jsonify({
            'success': True,
            'comment': ai_comment,
            'segments_count': len(segments),
            'patterns_count': len(patterns)
        })

    except Exception as e:
        print(f"❌ Erreur génération commentaire IA: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Erreur: {str(e)}'}), 500

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    # --- Drive-only guard ---
    try:
        prof = load_profile_from_drive()
    except DriveUnavailableError as e:
        return render_template(
            "profile.html",
            profile={},
            drive_error=f"⚠️ Données indisponibles (Drive) : {e}",
        )

    if request.method == 'POST':
        prof['birth_date'] = request.form.get('birth_date', '')
        weight = request.form.get('weight', '')
        prof['weight'] = float(weight) if weight else 0.0
        prof['global_objective'] = request.form.get('global_objective', '')
        prof['particular_objective'] = request.form.get('particular_objective', '')

        # 💓 Fréquences cardiaques
        hr_rest = request.form.get('hr_rest', '')
        prof['hr_rest'] = int(hr_rest) if hr_rest else 59
        hr_max = request.form.get('hr_max', '')
        prof['hr_max'] = int(hr_max) if hr_max else 170

        # 👟 Date d'achat des chaussures
        prof['shoes_purchase_date'] = request.form.get('shoes_purchase_date', '')

        # Événements (dates + noms)
        event_dates = request.form.getlist('event_date')
        event_names = request.form.getlist('event_name')
        events = []
        for d, n in zip(event_dates, event_names):
            d, n = d.strip(), n.strip()
            if d and n:
                events.append({'date': d, 'name': n})
        prof['events'] = events

        save_profile_local(prof)
        invalidate_profile_cache()  # Invalider cache après modification
        print(f"👟 Profil sauvegardé avec shoes_purchase_date={prof.get('shoes_purchase_date', 'non défini')}")
        return redirect('/')

    # Calculer les objectifs personnalisés pour affichage
    activities = load_activities_from_drive()
    personalized_targets = calculate_personalized_targets(prof, activities)

    return render_template('profile.html', profile=prof, personalized_targets=personalized_targets)


@app.route('/objectifs', methods=['GET'])
def objectifs():
    """Page de gestion des objectifs par type de run"""
    try:
        prof = load_profile_from_drive()
    except DriveUnavailableError as e:
        return render_template(
            "objectifs.html",
            profile={},
            drive_error=f"⚠️ Données indisponibles (Drive) : {e}",
        )

    # Charger les activités pour statistiques
    activities = load_activities_from_drive()

    # Compter les runs par type
    stats_by_type = {}
    for act in activities:
        cat = act.get('session_category')
        if cat:
            if cat not in stats_by_type:
                stats_by_type[cat] = {'count': 0, 'k_values': [], 'drift_values': []}
            stats_by_type[cat]['count'] += 1

            k = act.get('k_moy')
            drift = act.get('deriv_cardio')
            if isinstance(k, (int, float)):
                stats_by_type[cat]['k_values'].append(k)
            if isinstance(drift, (int, float)):
                stats_by_type[cat]['drift_values'].append(drift)

    # Calculer statistiques (moyenne, p20, p80)
    for cat, stats in stats_by_type.items():
        if stats['k_values']:
            stats['k_mean'] = np.mean(stats['k_values'])
            stats['k_p20'] = np.percentile(stats['k_values'], 20)
            stats['k_p80'] = np.percentile(stats['k_values'], 80)
        if stats['drift_values']:
            stats['drift_mean'] = np.mean(stats['drift_values'])
            stats['drift_p20'] = np.percentile(stats['drift_values'], 20)
            stats['drift_p80'] = np.percentile(stats['drift_values'], 80)

    return render_template(
        'objectifs.html',
        profile=prof,
        stats_by_type=stats_by_type
    )


@app.route('/api/objectifs/update', methods=['POST'])
def update_objectifs():
    """API pour mettre à jour les objectifs manuellement"""
    try:
        prof = load_profile_from_drive()
    except DriveUnavailableError as e:
        return jsonify({'error': str(e)}), 503

    data = request.json

    # Valider et mettre à jour les objectifs
    if 'personalized_targets' not in prof:
        prof['personalized_targets'] = {}

    for run_type in ['tempo_recup', 'tempo_rapide', 'endurance', 'long_run']:
        if run_type in data:
            k_target = data[run_type].get('k_target')
            drift_target = data[run_type].get('drift_target')

            if k_target is not None and drift_target is not None:
                if run_type not in prof['personalized_targets']:
                    prof['personalized_targets'][run_type] = {
                        'fc_max': 172.0,
                        'sample_size': 0
                    }

                prof['personalized_targets'][run_type]['k_target'] = float(k_target)
                prof['personalized_targets'][run_type]['drift_target'] = float(drift_target)

    # Sauvegarder
    save_profile_local(prof)
    invalidate_profile_cache()  # Invalider cache après modification

    return jsonify({'success': True, 'message': 'Objectifs mis à jour'})


@app.route('/zones-entrainement', methods=['GET'])
def zones_entrainement():
    """Page de documentation des zones d'entraînement"""
    try:
        prof = load_profile_from_drive()
    except DriveUnavailableError:
        prof = {'hr_rest': 59, 'hr_max': 170}  # Valeurs par défaut
    return render_template('zones_entrainement.html', profile=prof)


@app.route('/stats')
def stats_page():
    """Page de statistiques running avec graphiques"""
    from datetime import datetime, timedelta
    from collections import defaultdict

    try:
        activities = load_activities_from_drive()
    except DriveUnavailableError as e:
        return render_template('stats.html', error=str(e), stats_data=None)

    # Paramètres de période
    period = request.args.get('period', '6m')  # 1m, 6m, 1y
    run_type_filter = request.args.get('type', 'all')  # all, endurance, tempo_rapide, etc.

    # Calculer la date de début selon la période
    now = datetime.now()
    if period == '1m':
        start_date = now - timedelta(days=30)
        period_label = "1 mois"
    elif period == '6m':
        start_date = now - timedelta(days=180)
        period_label = "6 mois"
    else:  # 1y
        start_date = now - timedelta(days=365)
        period_label = "1 an"

    # Filtrer les activités par période et type
    filtered_activities = []
    for act in activities:
        try:
            act_date = datetime.strptime(act.get('date', '')[:10], '%Y-%m-%d')
            if act_date >= start_date:
                # Filtrer par type si spécifié
                act_type = act.get('session_category') or act.get('type_sortie', '')
                if run_type_filter == 'all' or act_type == run_type_filter:
                    filtered_activities.append({
                        'date': act_date,
                        'date_str': act.get('date', '')[:10],
                        'distance_km': act.get('distance_km', 0),
                        'allure_sec': convert_pace_to_seconds(act.get('allure', '0:00')),
                        'allure': act.get('allure', '-:--'),
                        'type': act_type,
                        'k_moy': act.get('k_moy', 0),
                        'deriv_cardio': act.get('deriv_cardio', 0)
                    })
        except (ValueError, TypeError):
            continue

    # Trier par date
    filtered_activities.sort(key=lambda x: x['date'])

    # Agréger par semaine (numéro de semaine ISO)
    weekly_data = defaultdict(lambda: {
        'distance_km': 0,
        'runs': 0,
        'allures': [],
        'k_values': [],
        'drift_values': []
    })

    for act in filtered_activities:
        week_key = act['date'].strftime('%Y-W%W')
        weekly_data[week_key]['distance_km'] += act['distance_km']
        weekly_data[week_key]['runs'] += 1
        if act['allure_sec'] > 0:
            weekly_data[week_key]['allures'].append(act['allure_sec'])
        if act['k_moy'] and act['k_moy'] > 0:
            weekly_data[week_key]['k_values'].append(act['k_moy'])
        if act['deriv_cardio'] and act['deriv_cardio'] > 0:
            weekly_data[week_key]['drift_values'].append(act['deriv_cardio'])

    # Préparer les données pour les graphiques
    weeks = sorted(weekly_data.keys())
    chart_labels = []
    chart_distances = []
    chart_paces = []
    chart_k = []
    chart_drift = []

    for week in weeks:
        data = weekly_data[week]
        # Formater le label de la semaine (ex: "S12")
        week_num = week.split('-W')[1]
        chart_labels.append(f"S{week_num}")
        chart_distances.append(round(data['distance_km'], 1))

        # Allure moyenne de la semaine (en secondes, puis converti en min:sec pour affichage)
        if data['allures']:
            avg_pace = sum(data['allures']) / len(data['allures'])
            chart_paces.append(round(avg_pace, 0))
        else:
            chart_paces.append(None)

        # k moyen
        if data['k_values']:
            chart_k.append(round(sum(data['k_values']) / len(data['k_values']), 3))
        else:
            chart_k.append(None)

        # Drift moyen
        if data['drift_values']:
            chart_drift.append(round(sum(data['drift_values']) / len(data['drift_values']), 1))
        else:
            chart_drift.append(None)

    # Statistiques globales
    total_distance = sum(act['distance_km'] for act in filtered_activities)
    total_runs = len(filtered_activities)
    avg_weekly_distance = total_distance / len(weeks) if weeks else 0

    # Allure moyenne globale
    all_paces = [act['allure_sec'] for act in filtered_activities if act['allure_sec'] > 0]
    avg_pace_sec = sum(all_paces) / len(all_paces) if all_paces else 0
    avg_pace_str = f"{int(avg_pace_sec // 60)}:{int(avg_pace_sec % 60):02d}" if avg_pace_sec > 0 else "-:--"

    # Types de runs disponibles pour le filtre
    run_types = list(set(act['type'] for act in filtered_activities if act['type']))

    stats_data = {
        'period': period,
        'period_label': period_label,
        'run_type_filter': run_type_filter,
        'run_types': sorted(run_types),
        'total_distance': round(total_distance, 1),
        'total_runs': total_runs,
        'avg_weekly_distance': round(avg_weekly_distance, 1),
        'avg_pace': avg_pace_str,
        'chart_labels': chart_labels,
        'chart_distances': chart_distances,
        'chart_paces': chart_paces,
        'chart_k': chart_k,
        'chart_drift': chart_drift,
        'activities': filtered_activities[-20:]  # 20 dernières pour le tableau
    }

    return render_template('stats.html', stats_data=stats_data)


def convert_pace_to_seconds(pace_str):
    """Convertit une allure 'M:SS' en secondes"""
    try:
        if not pace_str or pace_str in ['-:--', '-', 'N/A']:
            return 0
        parts = pace_str.replace('/km', '').strip().split(':')
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, AttributeError):
        pass
    return 0


@app.route('/api/objectifs/recalculate', methods=['POST'])
def recalculate_objectifs():
    """
    API pour recalculer automatiquement les objectifs avec une approche coach sportif:
    - k (efficacité): P30 (ambitieux mais atteignable)
    - drift (dérive cardio): P40 (réaliste physiologiquement)
    """
    try:
        prof = load_profile_from_drive()
        activities = load_activities_from_drive()
    except DriveUnavailableError as e:
        return jsonify({'error': str(e)}), 503

    # Grouper par type
    by_type = {}
    for act in activities:
        cat = act.get('session_category')
        if cat:
            if cat not in by_type:
                by_type[cat] = {'k': [], 'drift': []}

            k = act.get('k_moy')
            drift = act.get('deriv_cardio')
            if isinstance(k, (int, float)) and k > 0 and k < 15:  # Filter outliers
                by_type[cat]['k'].append(k)
            if isinstance(drift, (int, float)) and 0.8 < drift < 2.0:  # Filter outliers
                by_type[cat]['drift'].append(drift)

    # Calculer objectifs avec approche physiologique
    if 'personalized_targets' not in prof:
        prof['personalized_targets'] = {}

    # Limites plancher par type (approche coach sportif)
    drift_floors = {
        'tempo_recup': 1.03,    # Récup facile, on peut viser stable
        'tempo_rapide': 1.08,   # Effort intense, dérive normale
        'endurance': 1.05,      # Allure contrôlée
        'long_run': 1.04        # Distance, mais bien géré = peu de dérive
    }

    updated = {}
    for cat, values in by_type.items():
        if len(values['k']) >= 5 and len(values['drift']) >= 5:
            # k: P30 (ambitieux mais atteignable)
            k_target = round(np.percentile(values['k'], 30), 2)

            # drift: P40 (réaliste) + plancher physiologique
            drift_p40 = round(np.percentile(values['drift'], 40), 2)
            drift_floor = drift_floors.get(cat, 1.05)
            drift_target = max(drift_p40, drift_floor)  # Ne jamais descendre sous le plancher

            if cat not in prof['personalized_targets']:
                prof['personalized_targets'][cat] = {'fc_max': 172.0}

            prof['personalized_targets'][cat]['k_target'] = k_target
            prof['personalized_targets'][cat]['drift_target'] = drift_target
            prof['personalized_targets'][cat]['sample_size'] = len(values['k'])

            updated[cat] = {
                'k_target': k_target,
                'drift_target': drift_target,
                'sample_size': len(values['k'])
            }

    # Sauvegarder
    save_profile_local(prof)
    invalidate_profile_cache()  # Invalider cache après modification

    return jsonify({
        'success': True,
        'message': f'{len(updated)} objectifs recalculés',
        'targets': updated
    })
# ==================== ROUTES FEEDBACK ====================

@app.route('/feedback/<activity_date>')
def feedback_form(activity_date):
    """Affiche le formulaire de feedback pour une activité"""
    try:
        # Charger les activités pour récupérer les infos
        activities = load_activities_from_drive()

        # Trouver l'activité par date
        activity = None
        for act in activities:
            if act.get('date') == activity_date:
                activity = act
                break

        if not activity:
            return "Activité non trouvée", 404

        # Charger le feedback existant
        feedbacks = load_feedbacks()
        activity_id = str(activity.get('activity_id', ''))
        existing_feedback = feedbacks.get(activity_id, {})

        # Infos de l'activité
        distance_km = activity.get('distance_km', 0)
        duration_sec = activity.get('duration_sec', 0)
        duration_min = duration_sec / 60 if duration_sec else 0

        return render_template(
            'run_feedback.html',
            activity=activity,
            activity_date=activity_date,
            activity_id=activity_id,
            distance_km=round(distance_km, 2),
            duration_min=round(duration_min, 1),
            existing_feedback=existing_feedback
        )
    except Exception as e:
        return f"Erreur: {e}", 500


@app.route('/feedback/<activity_date>', methods=['POST'])
def save_feedback(activity_date):
    """Sauvegarde le feedback d'une activité"""
    try:
        # Récupérer les données du formulaire
        mode_run = request.form.get('mode_run', 'training')  # training ou race
        is_last_run_of_week = request.form.get('is_last_run_of_week') == 'true'  # Checkbox
        rating_stars = int(request.form.get('rating_stars', 3))
        difficulty = int(request.form.get('difficulty', 3))
        legs_feeling = request.form.get('legs_feeling', 'normal')
        cardio_feeling = request.form.get('cardio_feeling', 'moderate')
        enjoyment = int(request.form.get('enjoyment', 3))
        notes = request.form.get('notes', '').strip()

        # Charger les activités pour récupérer l'activity_id
        activities = load_activities_from_drive()
        activity = None
        for act in activities:
            if act.get('date') == activity_date:
                activity = act
                break

        if not activity:
            return "Activité non trouvée", 404

        activity_id = str(activity.get('activity_id', ''))

        # Charger les feedbacks existants
        feedbacks = load_feedbacks()

        # Créer/Mettre à jour le feedback
        from datetime import datetime
        feedbacks[activity_id] = {
            'activity_id': activity_id,
            'date': activity_date,
            'mode_run': mode_run,
            'is_last_run_of_week': is_last_run_of_week,
            'rating_stars': rating_stars,
            'difficulty': difficulty,
            'legs_feeling': legs_feeling,
            'cardio_feeling': cardio_feeling,
            'enjoyment': enjoyment,
            'notes': notes,
            'timestamp': datetime.now().isoformat()
        }

        # Sauvegarder dans le fichier
        feedback_file = Path(__file__).parent / 'outputs' / 'run_feedbacks.json'
        with open(feedback_file, 'w', encoding='utf-8') as f:
            json.dump(feedbacks, f, indent=2, ensure_ascii=False)

        print(f"✅ Feedback sauvegardé pour {activity_id}")

        # Rediriger vers la page d'accueil
        return redirect('/')
    except Exception as e:
        return f"Erreur sauvegarde: {e}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=True)
