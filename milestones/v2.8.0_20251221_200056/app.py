import os
import json
import io
import time
import pickle
import subprocess
from datetime import datetime, timedelta, date
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from dateutil import parser
from flask import Flask, render_template, request, redirect, jsonify
from openai import OpenAI
import anthropic
from dotenv import load_dotenv
from xgboost import XGBClassifier


# === Début bloc ENV universel (à coller après les imports) ===

# Dossier sécurité (Windows: C:\Track2TrainSecurity ; Linux: /opt/app/Track2TrainSecurity)
SEC_DIR = Path(
    os.getenv("STRAVA_SECURITY_DIR")
    or (r"C:\Track2TrainSecurity" if os.name == "nt" else "/opt/app/Track2TrainSecurity")
)
ENV_FILE = Path(os.getenv("STRAVA_SECURITY_PATH", SEC_DIR / "main.env"))


# 1) Charger .env du projet s'il existe
load_dotenv()

# 2) Charger main.env du dossier sécurité (override=True pour écraser si besoin)
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)
    print(f"✅ main.env chargé depuis {ENV_FILE}")
else:
    print(f"⚠️ main.env introuvable : {ENV_FILE}")

# 3) Si le chemin Google n'est pas défini, essayer services.json par défaut
if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    cred_path = SEC_DIR / "services.json"
    if cred_path.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)
        print(f"✅ services.json détecté : {cred_path}")
    else:
        print(f"⚠️ services.json manquant : {cred_path}")

# 4) Garde-fous (on ne va pas plus loin si une clé vitale manque)
for name in ["OPENAI_API_KEY", "FOLDER_ID", "GOOGLE_APPLICATION_CREDENTIALS"]:
    if not os.getenv(name):
        raise RuntimeError(f"Variable requise manquante: {name}")
# === Fin bloc ENV universel ===


# --- Helpers Drive (après bootstrap ENV !) ---

# --- Helpers coordonnées météo ---
def _extract_coords(act) -> tuple[float | None, float | None]:
    """Retourne (lat, lon) depuis un dict/row d'activité.
    Essaie start_latlng=[lat,lon], sinon start_lat/start_lng. None si introuvable.
    """
    lat = lon = None
    try:
        v = act.get("start_latlng")
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            lat, lon = v[0], v[1]
    except Exception:
        pass
    if lat is None:
        lat = act.get("start_lat") or act.get("start_latitude")
    if lon is None:
        lon = act.get("start_lng") or act.get("start_longitude")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except Exception:
        lat, lon = None, None
    return lat, lon

from data_access_local import (
    load_activities_local as load_activities_from_drive,
    load_profile_local as load_profile_from_drive,
    save_profile_local,
    save_activities_local as save_activities_to_drive,
    read_output_json_local as read_output_json,
    write_output_json_local as write_output_json,
    backup_activities_to_drive,
)

# Import des fonctions de calcul des statistiques par type de run
from calculate_running_stats import calculate_stats_by_type, save_running_stats

# Pour compatibilité (si jamais utilisé ailleurs)
class DriveUnavailableError(RuntimeError):
    pass

# Helpers factices pour compatibilité
def read_analysis(): return read_output_json('analysis.json')
def read_predictions(): return read_output_json('predictions.json')
def read_weekly_plan(): return read_output_json('weekly_plan.json')
def read_benchmark(): return read_output_json('benchmark.json')
def write_analysis(data): write_output_json('analysis.json', data)
def write_predictions(data): write_output_json('predictions.json', data)
def write_weekly_plan(data): write_output_json('weekly_plan.json', data)
def write_benchmark(data): write_output_json('benchmark.json', data)


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

app = Flask(__name__)


# --- Init OpenAI ---
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)
print("✅ OpenAI client initialisé")

# --- Init Anthropic (Claude Sonnet 4) ---
anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
anthropic_client = None
if anthropic_api_key:
    try:
        anthropic_client = anthropic.Anthropic(api_key=anthropic_api_key)
        print("✅ Anthropic client initialisé (Claude Sonnet 4)")
    except Exception as e:
        print(f"⚠️ Erreur init Anthropic: {e}")
else:
    print("⚠️ ANTHROPIC_API_KEY non définie")


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


# --- Fonction IA: Génération avec Claude Sonnet 4 ---
def generate_ai_coaching(prompt_content, max_tokens=500):
    """
    Fonction générique universelle pour générer du contenu avec Claude Sonnet 4

    Args:
        prompt_content: Le prompt à envoyer à Claude
        max_tokens: Nombre maximum de tokens (défaut: 500)

    Returns:
        str: La réponse de Claude ou un message par défaut si erreur
    """
    if not anthropic_client:
        return "⚠️ Coaching IA temporairement indisponible (clé API non configurée)."

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            messages=[{
                "role": "user",
                "content": prompt_content
            }]
        )
        return response.content[0].text
    except Exception as e:
        print(f"❌ Erreur generate_ai_coaching: {e}")
        return f"⚠️ Erreur lors de la génération du coaching IA. Veuillez réessayer plus tard."


def load_evolution_comments():
    """Charge les commentaires IA sauvegardés depuis outputs/evolution_comments.json"""
    try:
        comments = read_output_json('evolution_comments.json') or {}
        return comments
    except Exception as e:
        print(f"⚠️ Erreur chargement evolution_comments: {e}")
        return {}


def save_evolution_comments(comments):
    """Sauvegarde les commentaires IA dans outputs/evolution_comments.json"""
    try:
        write_output_json('evolution_comments.json', comments)
        print("💾 Commentaires IA sauvegardés")
    except Exception as e:
        print(f"⚠️ Erreur sauvegarde evolution_comments: {e}")


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


def generate_k_evolution_comment(activities_sorted, personalized_targets=None, force_regenerate=False):
    """
    Génère un commentaire IA contextualisé (15-25 mots) sur l'évolution de l'efficacité cardio (k_moy)
    sur les 10 dernières séances. Prend en compte allure, météo, dénivelé, type de séance et objectifs personnalisés.
    Utilise un cache pour éviter de regénérer à chaque fois.

    Args:
        activities_sorted: Liste des activités triées par date (plus récentes en premier)
        personalized_targets: Dict des objectifs personnalisés par type de séance
        force_regenerate: Si True, force la regénération même si un cache existe

    Returns:
        str: Commentaire IA contextualisé (max 30 mots) ou None si données insuffisantes
    """
    # Désactivé - les commentaires sont maintenant dans l'analyse principale
    return None

    if not anthropic_client:
        return None

    # Extraire les 10 dernières activités avec k_moy valide + contexte complet
    runs_data = []
    for act in activities_sorted[:10]:
        k = act.get("k_moy")
        if isinstance(k, (int, float)):
            runs_data.append({
                'k': k,
                'allure': act.get('allure', '-'),
                'type': act.get('type_sortie', 'inconnue'),
                'temp': act.get('temperature'),
                'denivele': act.get('gain_alt', 0),
                'date': act.get('date', '')[:10]  # Format YYYY-MM-DD
            })

    if len(runs_data) < 3:
        return None  # Pas assez de données

    # Clé de cache fixe (pas basée sur les valeurs pour qu'elle persiste)
    cache_key = "k_comment"

    # Charger le cache - toujours charger d'abord, sauf si force_regenerate
    if not force_regenerate:
        cached_comments = load_evolution_comments()
        if cache_key in cached_comments and cached_comments[cache_key]:
            print(f"📋 Commentaire k_evolution chargé depuis le cache")
            return cached_comments[cache_key]

    # Calculer statistiques
    k_values = [r['k'] for r in runs_data]
    k_first = k_values[-1]  # Plus ancien
    k_last = k_values[0]     # Plus récent
    k_avg = np.mean(k_values)
    k_trend = k_last - k_first

    # Construire détails contextuels pour chaque run (du plus ancien au plus récent)
    runs_details = []
    for run in reversed(runs_data):
        temp_str = f"{run['temp']:.0f}°C" if run['temp'] else "?"
        deniv_str = f"+{run['denivele']}m" if run['denivele'] > 0 else "plat"
        runs_details.append(
            f"k={run['k']:.2f} (allure {run['allure']}, {run['type']}, {temp_str}, {deniv_str})"
        )

    # Charger le template de prompt
    prompt_template = load_prompt("k_evolution")
    if not prompt_template:
        return None

    # Construire section objectifs personnalisés
    targets_section = ""
    if personalized_targets:
        targets_section = "\nOBJECTIFS PERSONNALISÉS (basés sur ton profil + historique):\n"
        for session_type in ['tempo_recup', 'tempo_rapide', 'endurance', 'long_run']:
            if session_type in personalized_targets:
                target = personalized_targets[session_type]
                # Format plus lisible pour l'IA
                type_display = session_type.replace('_', ' ')
                targets_section += f"- {type_display}: k objectif = {target['k_target']} (basé sur {target.get('sample_size', 0)} runs)\n"
    else:
        targets_section = "\nOBJECTIFS: Pas encore calculés (manque de données historiques)"

    # Construire le prompt à partir du template
    prompt = prompt_template.format(
        nb_runs=len(runs_data),
        runs_details='\n'.join(runs_details),
        k_first=f"{k_first:.2f}",
        k_last=f"{k_last:.2f}",
        k_avg=f"{k_avg:.2f}",
        k_trend=f"{k_trend:+.2f}",
        targets_section=targets_section
    )

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,  # Augmenté pour permettre commentaire contextualisé (15-25 mots)
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        comment = response.content[0].text.strip()
        # S'assurer que c'est bien 30 mots max (marge pour contexte enrichi)
        words = comment.split()
        if len(words) > 30:
            comment = ' '.join(words[:30])
        
        # Sauvegarder dans le cache
        cached_comments = load_evolution_comments()
        cached_comments[cache_key] = comment
        save_evolution_comments(cached_comments)
        
        return comment
    except Exception as e:
        print(f"❌ Erreur generate_k_evolution_comment: {e}")
        return None


def generate_drift_evolution_comment(activities_sorted, personalized_targets=None, force_regenerate=False):
    """
    Génère un commentaire IA contextualisé (15-25 mots) sur l'évolution de la dérive cardio (deriv_cardio)
    sur les 10 dernières séances. Prend en compte allure, météo, dénivelé, type de séance et objectifs personnalisés.
    Utilise un cache pour éviter de regénérer à chaque fois.

    Args:
        activities_sorted: Liste des activités triées par date (plus récentes en premier)
        personalized_targets: Dict des objectifs personnalisés par type de séance
        force_regenerate: Si True, force la regénération même si un cache existe

    Returns:
        str: Commentaire IA contextualisé (max 30 mots) ou None si données insuffisantes
    """
    # Désactivé - les commentaires sont maintenant dans l'analyse principale
    return None

    if not anthropic_client:
        return None

    # Extraire les 10 dernières activités avec deriv_cardio valide + contexte complet
    runs_data = []
    for act in activities_sorted[:10]:
        drift = act.get("deriv_cardio")
        if isinstance(drift, (int, float)):
            runs_data.append({
                'drift': drift,
                'allure': act.get('allure', '-'),
                'type': act.get('type_sortie', 'inconnue'),
                'temp': act.get('temperature'),
                'denivele': act.get('gain_alt', 0),
                'date': act.get('date', '')[:10]  # Format YYYY-MM-DD
            })

    if len(runs_data) < 3:
        return None  # Pas assez de données

    # Clé de cache fixe (pas basée sur les valeurs pour qu'elle persiste)
    cache_key = "drift_comment"

    # Charger le cache - toujours charger d'abord, sauf si force_regenerate
    if not force_regenerate:
        cached_comments = load_evolution_comments()
        if cache_key in cached_comments and cached_comments[cache_key]:
            print(f"📋 Commentaire drift_evolution chargé depuis le cache")
            return cached_comments[cache_key]

    # Calculer statistiques
    drift_values = [r['drift'] for r in runs_data]
    drift_first = drift_values[-1]  # Plus ancien
    drift_last = drift_values[0]     # Plus récent
    drift_avg = np.mean(drift_values)
    drift_trend = drift_last - drift_first

    # Construire détails contextuels pour chaque run (du plus ancien au plus récent)
    runs_details = []
    for run in reversed(runs_data):
        temp_str = f"{run['temp']:.0f}°C" if run['temp'] else "?"
        deniv_str = f"+{run['denivele']}m" if run['denivele'] > 0 else "plat"
        runs_details.append(
            f"dérive={run['drift']:.1f}% (allure {run['allure']}, {run['type']}, {temp_str}, {deniv_str})"
        )

    # Charger le template de prompt
    prompt_template = load_prompt("drift_evolution")
    if not prompt_template:
        return None

    # Construire section objectifs personnalisés
    targets_section = ""
    if personalized_targets:
        targets_section = "\nOBJECTIFS PERSONNALISÉS (basés sur ton profil + historique):\n"
        for session_type in ['tempo_recup', 'tempo_rapide', 'endurance', 'long_run']:
            if session_type in personalized_targets:
                target = personalized_targets[session_type]
                # Format plus lisible pour l'IA
                type_display = session_type.replace('_', ' ')
                targets_section += f"- {type_display}: dérive objectif = {target['drift_target']}% (basé sur {target.get('sample_size', 0)} runs)\n"
    else:
        targets_section = "\nOBJECTIFS: Pas encore calculés (manque de données historiques)"

    # Construire le prompt à partir du template
    prompt = prompt_template.format(
        nb_runs=len(runs_data),
        runs_details='\n'.join(runs_details),
        drift_first=f"{drift_first:.1f}",
        drift_last=f"{drift_last:.1f}",
        drift_avg=f"{drift_avg:.1f}",
        drift_trend=f"{drift_trend:+.1f}",
        targets_section=targets_section
    )

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=100,  # Augmenté pour permettre commentaire contextualisé (15-25 mots)
            messages=[{
                "role": "user",
                "content": prompt
            }]
        )
        comment = response.content[0].text.strip()
        # S'assurer que c'est bien 30 mots max (marge pour contexte enrichi)
        words = comment.split()
        if len(words) > 30:
            comment = ' '.join(words[:30])
        
        # Sauvegarder dans le cache
        cached_comments = load_evolution_comments()
        cached_comments[cache_key] = comment
        save_evolution_comments(cached_comments)
        
        return comment
    except Exception as e:
        print(f"❌ Erreur generate_drift_evolution_comment: {e}")
        return None


def generate_past_week_comment(past_week_analysis):
    """
    Génère un commentaire IA sur la semaine écoulée (réalisé vs programmé).

    Args:
        past_week_analysis: Dict résultat de analyze_past_week()

    Returns:
        str: Commentaire IA motivant (30-50 mots) ou None si données insuffisantes
    """
    if not anthropic_client or not past_week_analysis:
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
        run_details=run_details_text.strip()
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
def normalize_session_type(activity):
    """
    Normalise le type de séance vers les types standards du programme hebdo.
    Utilise le champ type_sortie existant et le mappe vers les types du programme.

    Retourne: 'sortie_longue', 'tempo', 'recuperation', ou 'fractionné'
    """
    # Si fractionné détecté
    if activity.get('is_fractionne', False):
        return 'fractionné'

    # Utiliser le type_sortie existant s'il est défini
    type_sortie = activity.get('type_sortie', '')

    # Mapping des types existants vers types programme
    if type_sortie == 'long_run':
        return 'sortie_longue'
    elif type_sortie == 'recovery':
        return 'recuperation'
    elif type_sortie in ['normal_5k', 'normal_10k']:
        # Pour normal_5k et normal_10k, on utilise la distance pour affiner
        dist_km = activity.get('distance_km', 0)
        if dist_km < 6:
            return 'recuperation'
        else:
            return 'tempo'
    elif type_sortie == 'fractionné':
        return 'fractionné'

    # Fallback: basé sur la distance si type_sortie n'est pas reconnu
    dist_km = activity.get('distance_km', 0)
    if dist_km > 11:
        return 'sortie_longue'
    elif dist_km < 6:
        return 'recuperation'
    else:
        return 'tempo'


def detect_session_type(activity):
    """
    Règles par distance (aucune substitution par XGBoost ici) :
    - > 11 km  -> long_run
    - < 8 km   -> normal_5k
    - sinon    -> normal_10k

    DEPRECATED: Utiliser normalize_session_type() à la place
    """
    pts = activity.get("points", [])
    if not pts:
        return activity.get("type_sortie", "inconnue") or "inconnue"

    dist_km = pts[-1]["distance"] / 1000.0

    if dist_km > 11:
        return "long_run"
    if dist_km < 8:
        return "normal_5k"
    return "normal_10k"

    
def _features_fractionne(activity):
    """Vecteur de 4 features simples pour XGBoost: [cv_allure, cv_fc, blocs_rapides, pct_temps_90].
    - blocs_rapides détectés avec une fenêtre glissante en distance (offset libre)
    """
    pts = activity.get("points", [])
    if len(pts) < 10:
        return [0.0, 0.0, 0.0, 0.0]

    fcs = np.array([p.get("hr") for p in pts], dtype=float)
    vels = np.array([p.get("vel") for p in pts], dtype=float)
    dists = np.array([p.get("distance") for p in pts], dtype=float)

    # Allures en min/km (nan si vel <= 0)
    allures = np.where(vels > 0, (1.0 / vels) * 16.6667, np.nan)

    # 1) CV allure & 2) CV FC
    def _cv(x):
        m = np.nanmean(x)
        if not np.isfinite(m) or m == 0:
            return 0.0
        return float(np.nanstd(x) / m)

    cv_allure = _cv(allures)
    cv_fc = _cv(fcs)

    # 3) Nombre de blocs rapides détectés via fenêtre glissante
    WINDOW_M   = 500     # longueur de la fenêtre en mètres
    FAST_DELTA = 0.40    # seuil de rapidité (min/km plus rapide que la moyenne)
    COOLDOWN_M = 200     # distance minimale entre deux détections pour éviter les doublons

    mean_all = np.nanmean(allures)
    thr_fast = mean_all - FAST_DELTA if np.isfinite(mean_all) else np.nan

    blocs_rapides = 0
    i = 0
    N = len(dists)
    last_hit_end_d = -1e9  # distance fin du dernier bloc validé

    while i < N - 1:
        # trouve j tel que distance(i → j) >= WINDOW_M
        j = i
        while j < N and (dists[j] - dists[i]) < WINDOW_M:
            j += 1
        if j >= N:
            break

        bloc_all = np.nanmean(allures[i:j+1])
        dist_i, dist_j = dists[i], dists[j]

        # Critère rapide + cooldown respecté
        is_fast = (np.isfinite(bloc_all) and np.isfinite(thr_fast) and bloc_all < thr_fast)
        far_enough = (dist_i - last_hit_end_d) >= COOLDOWN_M

        if is_fast and far_enough:
            blocs_rapides += 1
            last_hit_end_d = dist_j
            # saute à la fin du bloc + cooldown
            i = j
            while i < N and (dists[i] - last_hit_end_d) < COOLDOWN_M:
                i += 1
            continue

        # sinon avance juste d'un point
        i += 1

    # 4) % temps au-dessus de 90% FCmax de la séance
    if np.all(np.isnan(fcs)) or len(fcs) == 0:
        pct_90 = 0.0
    else:
        fcmax = np.nanmax(fcs)
        thr = 0.9 * fcmax if np.isfinite(fcmax) and fcmax > 0 else np.nan
        if np.isfinite(thr):
            pct_90 = float(np.nansum(fcs > thr) / np.count_nonzero(~np.isnan(fcs)))
        else:
            pct_90 = 0.0

    feats = [cv_allure, cv_fc, float(blocs_rapides), pct_90]
    # Remplace NaN/±inf par 0 pour le modèle
    feats = [0.0 if (not np.isfinite(v)) else float(v) for v in feats]
    return feats

    
    
def tag_session_types(activities):
    changed = False
    for act in activities:
        cur = act.get("type_sortie")
        if cur in (None, "-", "inconnue") or act.get("force_recompute", False):
            new_type = detect_session_type(act)
            if new_type != cur:
                act["type_sortie"] = new_type
                changed = True
        act.pop("force_recompute", None)
    return activities, changed
def apply_fractionne_flags(activities):
    """
    Ajoute/actualise :
      - is_fractionne: bool
      - fractionne_prob: float [0..1]
    Sans jamais modifier type_sortie.
    Règle: on évalue XGB seulement si distance <= 11 km ; sinon is_fractionne=False.
    PRIORITÉ aux labels manuels (is_fractionne_label) s'ils sont présents.
    """
    changed = False
    for act in activities:
        # 1) Priorité au label manuel
        if "is_fractionne_label" in act:
            lbl = bool(act["is_fractionne_label"])
            new_flag = lbl
            new_prob = 1.0 if lbl else 0.0

        else:
            # 2) Sinon, on calcule avec le modèle si possible
            pts = act.get("points", [])
            if not pts:
                new_flag, new_prob = False, 0.0
            else:
                dist_km = pts[-1].get("distance", 0) / 1000.0
                if dist_km > 11 or fractionne_model is None:
                    new_flag, new_prob = False, 0.0
                else:
                    feats = _features_fractionne(act)
                    try:
                        proba = float(fractionne_model.predict_proba(np.array([feats]))[0][1])
                        new_prob = round(proba, 3)
                        new_flag = (proba >= 0.5)  # seuil ajustable
                    except Exception as e:
                        print("🤖 XGBoost predict error:", e)
                        new_flag, new_prob = False, 0.0

        # 3) Appliquer si changement
        if act.get("is_fractionne") != new_flag or act.get("fractionne_prob") != new_prob:
            act["is_fractionne"] = new_flag
            act["fractionne_prob"] = new_prob
            changed = True

    return activities, changed


def _mean_cadence_spm(points):
    """Moyenne de cadence (spm) sur une activité, None si pas de données."""
    if not points:
        return None
    vals = [p.get("cad_spm") for p in points if isinstance(p.get("cad_spm"), (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else None


print("✅ Helpers OK")


# -------- XGBoost fractionné (chargement modèle) --------
MODEL_PATH = "fractionne_xgb.pkl"
fractionne_model = None  # global lecture seule

# ==== Auto-réentrainement XGBoost ====
AUTO_RETRAIN_XGB = True                 # désactive en mettant False si besoin
LAST_TRAIN_META = "ml/.last_train_meta.json"  # fichier local pour mémoriser le dernier état (compte d’activités)

def _load_last_train_meta():
    try:
        with open(LAST_TRAIN_META, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_trained_count": 0}

def _save_last_train_meta(count):
    os.makedirs(os.path.dirname(LAST_TRAIN_META), exist_ok=True)
    with open(LAST_TRAIN_META, "w", encoding="utf-8") as f:
        json.dump({"last_trained_count": int(count)}, f)

def _count_manual_labels(activities):
    pos = neg = 0
    for a in activities:
        if "is_fractionne_label" in a:
            if bool(a["is_fractionne_label"]): pos += 1
            else: neg += 1
    return pos, neg

def _should_retrain_xgb(activities):
    """
    Vrai si:
      - on a au moins 8 fractionnés (pos) ET 8 non-fractionnés (neg), ET
      - au moins 1 nouvelle activité depuis le dernier entraînement.
    """
    meta = _load_last_train_meta()
    last_cnt = meta.get("last_trained_count", 0)
    cur_cnt = len(activities)
    if cur_cnt <= last_cnt:
        return False

    pos, neg = _count_manual_labels(activities)
    if pos < 8 or neg < 8:
        print(f"ℹ️ Pas assez de labels pour auto-train (pos={pos}, neg={neg}, min=8 chacun)")
        return False

    print(f"🔁 Auto-train éligible: new_activities={cur_cnt - last_cnt}, labels(pos={pos}, neg={neg})")
    return True

def _retrain_fractionne_model_and_reload():
    """
    Lance ml/train_fractionne_xgb.py, recharge le modèle, mémorise le nb d'activités.
    """
    try:
        print("🤖 Auto-train: lancement ml/train_fractionne_xgb.py ...")
        subprocess.run(["python", "ml/train_fractionne_xgb.py"], check=True, timeout=300)
        # Recharge le modèle
        global fractionne_model
        fractionne_model = load_fractionne_model()
        # Mémorise le nouveau compteur
        activities = load_activities_from_drive()
        _save_last_train_meta(len(activities))
        print("✅ Auto-train OK et modèle rechargé.")
        return True
    except Exception as e:
        print("❌ Auto-train échoué:", e)
        return False


def load_fractionne_model(path=MODEL_PATH):
    try:
        with open(path, "rb") as f:
            model = pickle.load(f)
        print(f"🤖 XGBoost fractionné chargé: {path}")
        return model
    except FileNotFoundError:
        print("🤖 XGBoost fractionné introuvable → désactivé (pas de fichier .pkl).")
    except Exception as e:
        print("🤖 Erreur chargement XGBoost:", e)
    return None

# Charge à l'init
fractionne_model = load_fractionne_model()


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
        from datetime import datetime
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
            except:
                # Fallback: essayer sans timezone
                try:
                    act_date = datetime.strptime(act_date_str.split('T')[0], '%Y-%m-%d')
                except:
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



def get_weather_emoji_for_activity(activity):
    weather_code_map = {
        0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
        45: "🌫️", 48: "🌫️", 51: "🌦️", 53: "🌧️",
        55: "🌧️", 61: "🌧️", 63: "🌧️", 65: "🌧️",
        71: "❄️", 73: "❄️", 75: "❄️", 80: "🌧️",
        81: "🌧️", 82: "🌧️", 95: "⛈️", 96: "⛈️",
        99: "⛈️"
    }
    points = activity.get("points", [])
    if not points:
        return "❓"
    lat, lon = None, None
    if "lat" in points[0] and "lng" in points[0]:
        lat, lon = points[0]["lat"], points[0]["lng"]
    elif "start_latlng" in activity and activity["start_latlng"]:
        lat, lon = activity["start_latlng"][0], activity["start_latlng"][1]
    date_str = activity.get("date", None)
    if not lat or not lon or not date_str:
        return "❓"
    duration_minutes = (points[-1]["time"] - points[0]["time"]) / 60
    _, _, _, weather_code = get_temperature_for_run(lat, lon, date_str, duration_minutes)
    return weather_code_map.get(weather_code, "❓")
    
def ensure_weather_data(activities):
    """Vérifie que chaque activité a les données météo et les calcule si elles sont absentes."""
    updated = False

    for act in activities:
        if act.get("avg_temperature") is None or act.get("weather_code") is None:
            points = act.get("points", [])
            if not points:
                continue

            lat, lon = points[0].get("lat"), points[0].get("lng")
            duration = (points[-1]["time"] - points[0]["time"]) / 60

            avg_temp, _, _, weather_code = get_temperature_for_run(
                lat, lon, act.get("date"), duration
            )

            act["avg_temperature"] = avg_temp
            act["weather_code"] = weather_code
            updated = True
            print(f"🌤️ Météo ajoutée pour {act.get('date')} ➜ {avg_temp}°C / code {weather_code}")

    if updated:
        save_activities_to_drive(activities)
        print("💾 activities.json mis à jour avec la météo")

    return activities

# -------------------
# Loaders (Drive-only via helpers.data_access)
# -------------------
def load_profile():
    try:
        return load_profile_from_drive()
    except DriveUnavailableError:
        return {"birth_date": "", "weight": 0, "events": []}

def load_objectives():
    # Charge objectives.json depuis le répertoire outputs/ local
    return read_output_json('objectives.json') or {}

def load_short_term_prompt_from_drive():
    # Charge prompt_short_term.txt depuis outputs/ local
    return read_output_json('prompt_short_term.txt') or "Donne directement le JSON des objectifs à court terme."

def load_short_term_objectives():
    # Charge short_term_objectives.json depuis outputs/ local
    return read_output_json('short_term_objectives.json') or {}

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
    from datetime import datetime

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
    slope, intercept = np.polyfit(distances_analysis, ratios_analysis, 1)
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


def enrich_activities(activities):
    fc_max_fractionnes = get_fcmax_from_fractionnes(activities)
    print(f"📈 FC max fractionnés: {fc_max_fractionnes}")

    for idx, activity in enumerate(activities):
        # 1) Assigner le type de séance si manquant/forcé (règles simples par distance)
        if activity.get("type_sortie") in (None, "-", "inconnue") or activity.get("force_recompute", False):
            activity["type_sortie"] = detect_session_type(activity)

        # 2) Enrichissements numériques (k, dérive cardio, etc.)
        activity = enrich_single_activity(activity, fc_max_fractionnes)

        print(f"🏃 Act#{idx+1} ➔ type: {activity.get('type_sortie')}, k_moy: {activity.get('k_moy')}")
        activity.pop("force_recompute", None)

    # 3) Ajouter moyennes 10 dernières séances et tendance
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
        elif type_sortie == 'long_run':
            return 'long_run'
        elif type_sortie == 'endurance':
            return 'endurance'
        elif type_sortie == 'tempo_rapide':
            return 'tempo_rapide'
        elif type_sortie == 'tempo_recup':
            return 'tempo_recup'
        elif type_sortie in ['normal_5k', 'normal_10k']:
            # Ancienne logique - ne devrait plus être utilisée
            return 'tempo'
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


def allure_mmss_to_decimal(mmss):
    try:
        minutes, seconds = mmss.split(":")
        return int(minutes) + int(seconds) / 60
    except Exception:
        return 0.0
        
def convert_short_term_allures(short_term):
    if not short_term or "prochains_runs" not in short_term:
        return short_term
    for run in short_term["prochains_runs"]:
        if isinstance(run.get("allure"), str):
            run["allure_decimal"] = allure_mmss_to_decimal(run["allure"])
        else:
            run["allure_decimal"] = 0.0
    return short_term

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

    weather_code_map = {
        0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 48: "🌫️",
        51: "🌦️", 53: "🌧️", 55: "🌧️", 61: "🌧️", 63: "🌧️", 65: "🌧️",
        71: "❄️", 73: "❄️", 75: "❄️", 77: "❄️", 80: "🌧️", 81: "🌧️", 82: "🌧️",
        95: "⛈️", 96: "⛈️", 99: "⛈️"
    }

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
    weather_emoji = weather_code_map.get(weather_code, "❓")

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


# --- Fonction helper: Formater allure ---
def format_pace(pace_sec):
    """Convertit sec/km en format mm:ss"""
    mins = int(pace_sec // 60)
    secs = int(pace_sec % 60)
    return f"{mins}:{secs:02d}"


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

def analyze_cardiac_health(activity, profile):
    """
    Analyse santé cardiaque avec 5 zones FC et alertes.

    Returns:
        dict: Analyse complète santé cardiaque
    """
    points = activity.get('points', [])
    if not points:
        return {'status': 'no_data', 'alerts': [], 'observations': [], 'recommendations': []}

    # FC max théorique (formule Tanaka)
    age = profile.get('age', 52)
    fc_max_theo = 208 - (0.7 * age)

    # Définir les 5 zones FC
    zones = {
        1: (fc_max_theo * 0.50, fc_max_theo * 0.60),  # Récupération
        2: (fc_max_theo * 0.60, fc_max_theo * 0.70),  # Endurance base
        3: (fc_max_theo * 0.70, fc_max_theo * 0.80),  # Tempo
        4: (fc_max_theo * 0.80, fc_max_theo * 0.90),  # Seuil
        5: (fc_max_theo * 0.90, fc_max_theo * 1.00),  # VO2 max
    }

    # Calculer temps dans chaque zone
    zone_times = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for i, p in enumerate(points):
        hr = p.get('hr', 0)
        if hr == 0:
            continue

        # Déterminer zone
        for zone_num, (min_hr, max_hr) in zones.items():
            if min_hr <= hr < max_hr:
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
    if fc_max > fc_max_theo * 0.98:
        alerts.append("⚠️ FC max atteinte proche du maximum théorique")

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
            'fc_max_theo': fc_max_theo
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


# --- Phase 3: Génération commentaires IA avec prompts externes ---

def generate_segment_analysis(activity, feedback, profile, segments, patterns,
                              segment_comparisons=None, cardiac_analysis=None, activities=None):
    """
    Génère un commentaire IA enrichi en utilisant un prompt externe.

    Args:
        activity: Dict métriques globales du run
        feedback: Dict ressenti utilisateur
        profile: Dict profil utilisateur
        segments: Liste des segments calculés
        patterns: Liste des patterns détectés
        segment_comparisons: Comparaisons vs historique (Phase 3 Sprint 1)
        cardiac_analysis: Analyse santé cardiaque (Phase 3 Sprint 2)

    Returns:
        str: Commentaire coaching IA (200-350 mots)
    """
    # Charger le template de prompt
    prompt_template = load_prompt("session_analysis")
    if not prompt_template:
        return "⚠️ Template de prompt introuvable."

    # Extraction données profil
    objectives = profile.get('objectives', {})
    preferences = profile.get('preferences', {})
    main_goal = objectives.get('main_goal', 'semi_marathon')
    running_style = objectives.get('running_style', 'moderate')
    intensity_tolerance = objectives.get('intensity_tolerance', 50)
    min_pace = preferences.get('min_comfortable_pace', '5:20')
    max_pace = preferences.get('max_comfortable_pace', '5:40')
    enjoys_sweating = preferences.get('enjoys_sweating', False)
    target_event = objectives.get('target_event', '')

    # Extraction données activité
    date = activity.get('date', '')
    distance_km = f"{activity.get('distance_km', 0):.2f}"
    allure_moy = activity.get('allure', '-:--')
    fc_moy = f"{activity.get('fc_moy', 0):.0f}"
    fc_max_run = f"{activity.get('fc_max', 0):.0f}"

    # Dérive et k avec nouveau format (1 décimale pour drift %, 2 pour k)
    deriv_cardio_val = activity.get('deriv_cardio', 0)
    hr_drift_pct = f"{deriv_cardio_val:.1f}" if isinstance(deriv_cardio_val, (int, float)) else "N/D"

    k_moy_val = activity.get('k_moy', 0)
    k_moy = f"{k_moy_val:.2f}" if isinstance(k_moy_val, (int, float)) else "N/D"

    # Dénivelé et météo
    dplus_m = activity.get('gain_alt', 0)
    temperature = activity.get('temperature', 20)
    weather_emoji = activity.get('weather_emoji', '☀️')

    # Type de run et objectif physiologique
    type_run = activity.get('session_category', activity.get('type_sortie', 'tempo'))
    objectif_run_map = {
        'tempo_recup': 'Récupération active, FC basse, confort',
        'tempo_rapide': 'Tempo rapide, développement seuil',
        'endurance': 'Endurance aérobie, volume',
        'long_run': 'Endurance longue distance, résistance'
    }
    objectif_run = objectif_run_map.get(type_run, 'Course de base')

    # Cadence
    cad_mean_spm = activity.get('cad_mean_spm', 0)
    cad_cv_pct = activity.get('cad_cv_pct', 0)

    # Objectifs personnalisés
    personalized_targets = profile.get('personalized_targets', {})
    targets = personalized_targets.get(type_run, {})
    k_target = f"{targets.get('k_target', 0):.2f}" if targets else "N/D"
    drift_target = f"{targets.get('drift_target', 0):.1f}" if targets else "N/D"

    # Calcul écarts vs objectifs
    ecart_k = "N/D"
    ecart_drift = "N/D"
    if targets and isinstance(k_moy_val, (int, float)):
        k_target_val = targets.get('k_target', 0)
        if k_target_val > 0:
            ecart_k = f"{k_moy_val - k_target_val:+.2f}"
    if targets and isinstance(deriv_cardio_val, (int, float)):
        drift_target_val = targets.get('drift_target', 0)
        if drift_target_val > 0:
            ecart_drift = f"{deriv_cardio_val - drift_target_val:+.1f}"

    # Historique (moyennes 10 derniers)
    k_avg_10 = activity.get('k_avg_10', None)
    drift_avg_10 = activity.get('drift_avg_10', None)
    k_avg_10_str = f"{k_avg_10:.2f}" if k_avg_10 else "N/D"
    drift_avg_10_str = f"{drift_avg_10:.1f}" if drift_avg_10 else "N/D"

    # Tendance
    k_trend = activity.get('k_trend', 0)
    drift_trend = activity.get('drift_trend', 0)
    if k_trend == 1:
        tendance_k = "amélioration"
    elif k_trend == -1:
        tendance_k = "dégradation"
    else:
        tendance_k = "stable"

    if drift_trend == -1:  # Pour drift, -1 = amélioration (baisse)
        tendance_drift = "amélioration"
    elif drift_trend == 1:
        tendance_drift = "dégradation"
    else:
        tendance_drift = "stable"

    tendance = f"k {tendance_k}, dérive {tendance_drift}"

    # Extraction feedback
    mode_run = feedback.get('mode_run', 'training')  # training ou race
    rating_stars = feedback.get('rating_stars', 3)
    difficulty = feedback.get('difficulty', 3)
    legs_feeling = feedback.get('legs_feeling', 'normal')
    cardio_feeling = feedback.get('cardio_feeling', 'moderate')
    enjoyment = feedback.get('enjoyment', 3)
    notes = feedback.get('notes', '').strip()

    # Convertir ressenti en échelle 1-10 (actuellement sur 5)
    ressenti_cardio = feedback.get('cardio_feeling_numeric', difficulty * 2)  # Approximation
    ressenti_jambes = feedback.get('legs_feeling_numeric', difficulty * 2)
    difficulte = difficulty * 2  # Convertir 1-5 en 1-10

    # Zones FC (depuis cardiac_analysis si disponible)
    zones_reel = "N/D"
    pace_by_zone = "N/D (non implémenté)"

    # Calculer moyennes historiques zones FC pour même type de run
    zones_avg = {}
    if activities and type_run:
        same_type_zones = {1: [], 2: [], 3: [], 4: [], 5: []}
        for act in activities[:50]:  # 50 dernières activités
            if act.get('session_category') == type_run or act.get('type_sortie') == type_run:
                act_zones = act.get('zone_percentages', {})
                if act_zones:
                    for z in range(1, 6):
                        pct = act_zones.get(str(z), 0)
                        if pct > 0:
                            same_type_zones[z].append(pct)

        # Calculer moyennes
        for z in range(1, 6):
            if same_type_zones[z]:
                zones_avg[z] = sum(same_type_zones[z]) / len(same_type_zones[z])
            else:
                zones_avg[z] = 0

    # Formatter les moyennes pour le prompt
    zones_avg_str = ", ".join([f"Z{z}: {zones_avg.get(z, 0):.1f}%" for z in range(1, 6)]) if zones_avg else "N/D"

    if cardiac_analysis and cardiac_analysis.get('hr_zones'):
        hr_zones = cardiac_analysis['hr_zones']
        zone_pcts = hr_zones['zone_percentages']
        zones_reel = ", ".join([f"Z{z}: {zone_pcts.get(z, 0):.1f}%" for z in range(1, 6)])

    # Calcul écart allure vs cible semi (~5:00-5:15/km)
    ecart_allure = "N/D"
    if allure_moy and allure_moy != '-:--':
        try:
            # Parser allure (format "5:22")
            parts = allure_moy.split(':')
            allure_decimal = int(parts[0]) + int(parts[1])/60  # Ex: 5.367
            allure_cible = 5.125  # Moyenne de 5:00-5:15 = 5:07.5
            diff_sec = (allure_decimal - allure_cible) * 60
            ecart_allure = f"{diff_sec:+.0f} sec/km vs cible semi"
        except:
            ecart_allure = "N/D"

    # Récupérer is_last_run_of_week depuis le feedback (checkbox manuelle)
    is_last_run_of_week = feedback.get('is_last_run_of_week', False)

    # Si dernier run de la semaine, analyser tous les runs de la semaine
    week_summary = ""
    current_week = 0
    if is_last_run_of_week and activities and date:
        from datetime import datetime
        try:
            current_date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            current_week = current_date.isocalendar()[1]
            current_year = current_date.isocalendar()[0]

            # Récupérer tous les runs de la semaine
            week_runs = []
            for act in activities:
                act_date_str = act.get('date', '')
                if act_date_str:
                    try:
                        act_date = datetime.fromisoformat(act_date_str.replace('Z', '+00:00'))
                        act_week = act_date.isocalendar()[1]
                        act_year = act_date.isocalendar()[0]
                        if act_week == current_week and act_year == current_year:
                            week_runs.append(act)
                    except:
                        pass

            # Trier par date
            week_runs.sort(key=lambda x: x.get('date', ''))

            # Générer le résumé de la semaine
            if week_runs:
                total_distance = sum(r.get('distance_km', 0) for r in week_runs)
                total_dplus = sum(r.get('gain_alt', 0) for r in week_runs)
                avg_k = sum(r.get('k_moy', 0) for r in week_runs if r.get('k_moy')) / len([r for r in week_runs if r.get('k_moy')]) if any(r.get('k_moy') for r in week_runs) else 0
                avg_drift = sum(r.get('deriv_cardio', 0) for r in week_runs if r.get('deriv_cardio')) / len([r for r in week_runs if r.get('deriv_cardio')]) if any(r.get('deriv_cardio') for r in week_runs) else 0

                week_summary = f"\n\n=== BILAN SEMAINE {current_week} ===\n"
                week_summary += f"Nombre de runs : {len(week_runs)}\n"
                week_summary += f"Distance totale : {total_distance:.1f} km\n"
                week_summary += f"Dénivelé total : {total_dplus:.0f} m\n"
                week_summary += f"k moyen semaine : {avg_k:.2f}\n"
                week_summary += f"Dérive moyenne semaine : {avg_drift:.1f}%\n\n"

                week_summary += "Détail des runs :\n"
                for i, run in enumerate(week_runs, 1):
                    run_date = run.get('date', '')[:10]
                    run_dist = run.get('distance_km', 0)
                    run_allure = run.get('allure', '-:--')
                    run_k = run.get('k_moy', 0)
                    run_drift = run.get('deriv_cardio', 0)
                    run_type = run.get('session_category', run.get('type_sortie', 'N/D'))
                    week_summary += f"  Run {i} ({run_date}) : {run_dist:.1f}km, {run_allure}/km, k={run_k:.2f}, dérive={run_drift:.1f}%, type={run_type}\n"
        except Exception as e:
            week_summary = f"\n[Erreur génération bilan semaine: {e}]\n"

    # Remplacer toutes les variables dans le template
    prompt = prompt_template.format(
        mode_run=mode_run,
        type_run=type_run,
        objectif_run=objectif_run,
        distance_km=distance_km,
        dplus_m=dplus_m,
        allure_moy=allure_moy,
        pace_by_zone=pace_by_zone,
        zones_avg=zones_avg_str,
        zones_reel=zones_reel,
        hr_drift_pct=hr_drift_pct,
        k_moy=k_moy,
        k_target=k_target,
        drift_target=drift_target,
        ecart_k=ecart_k,
        ecart_drift=ecart_drift,
        k_avg_10=k_avg_10_str,
        drift_avg_10=drift_avg_10_str,
        tendance=tendance,
        cad_mean_spm=cad_mean_spm,
        cad_cv_pct=f"{cad_cv_pct:.1f}",
        temperature=f"{temperature:.0f}",
        weather_emoji=weather_emoji,
        ressenti_cardio=ressenti_cardio,
        ressenti_jambes=ressenti_jambes,
        difficulte=difficulte,
        ecart_allure=ecart_allure,
        fc_moy=fc_moy,
        is_last_run_of_week=is_last_run_of_week,
        week_summary=week_summary,
        current_week=current_week
    )

    # Générer le commentaire avec Claude (augmenté pour bilan semaine + programme)
    return generate_ai_coaching(prompt, max_tokens=5000)


# --- Phase 3 Sprint 3: Programme Hebdomadaire ---

def analyze_past_week(previous_program, activities):
    """
    Analyse la semaine précédente: compare runs réalisés vs programme.

    Args:
        previous_program: Dict du programme de la semaine précédente
        activities: Liste des activités (triées par date décroissante)

    Returns:
        dict: Analyse avec runs_completed, runs_missed, adherence_rate, details
    """
    if not previous_program or not previous_program.get('runs'):
        return None

    import datetime
    from datetime import timedelta
    from dateutil import parser as date_parser

    # Dates de la semaine programmée
    start_date_str = previous_program.get('start_date')  # "2025-11-18"
    end_date_str = previous_program.get('end_date')  # "2025-11-24"

    if not start_date_str or not end_date_str:
        return None

    try:
        week_start = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        week_end = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    except:
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
                act_date = datetime.datetime.strptime(date_only, '%Y-%m-%d').date()
                if week_start <= act_date <= week_end:
                    week_activities.append(act)
            except:
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
        'total_distance_programmed': previous_program.get('summary', {}).get('total_distance', 0),
        'total_distance_realized': sum(act.get('distance_km', 0) for act in week_activities)
    }


def generate_weekly_program(profile, activities):
    """
    Génère un programme hebdomadaire de 4 runs personnalisé.
    Pattern: 2x 5-6km, 1x 10-11km, 1x 12km+

    Args:
        profile: Dict profil utilisateur
        activities: Liste des activités récentes

    Returns:
        dict: Programme avec 4 runs (structure complète)
    """
    import datetime

    # Extraction profil
    objectives = profile.get('objectives', {})
    preferences = profile.get('preferences', {})
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
    today = datetime.date.today()
    week_number = today.isocalendar()[1]

    # Calculer dates de la semaine (lundi → dimanche)
    days_since_monday = today.weekday()
    monday = today - datetime.timedelta(days=days_since_monday)
    sunday = monday + datetime.timedelta(days=6)

    # --- RUN 1: RÉCUPÉRATION 5-6km (Lundi) ---
    run1_distance = 5.5
    run1_pace_sec = avg_pace + 20  # 20 sec/km plus lent
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

    # --- RUN 2: TEMPO LÉGER 5-6km (Mercredi) ---
    run2_distance = 6.0
    run2_pace_sec = avg_pace  # Allure moyenne
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

    # --- RUN 3: TEMPO 10-11km (Vendredi) ---
    run3_distance = 10.5
    run3_pace_sec = avg_pace - 10  # 10 sec/km plus rapide
    run3_pace_min = int(run3_pace_sec // 60)
    run3_pace_sec_remain = int(run3_pace_sec % 60)
    run3_pace_str = f"{run3_pace_min}:{run3_pace_sec_remain:02d}/km"
    run3_predicted_time_sec = run3_distance * run3_pace_sec
    run3_predicted_hours = int(run3_predicted_time_sec // 3600)
    run3_predicted_mins = int((run3_predicted_time_sec % 3600) // 60)
    run3_predicted_secs = int(run3_predicted_time_sec % 60)
    run3_predicted_time = f"{run3_predicted_hours:02d}:{run3_predicted_mins:02d}:{run3_predicted_secs:02d}"
    run3_fc_min = int(avg_fc)
    run3_fc_max = int(avg_fc + 10)

    # --- RUN 4: LONG RUN 12km+ (Dimanche) ---
    run4_distance = 12.0 if avg_distance < 10 else min(avg_distance * 1.2, 15)
    run4_pace_sec = avg_pace + 10  # 10 sec/km plus lent
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
        'generated_at': datetime.datetime.now().isoformat(),
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
                'notes': 'Relâchement total, endurance de base. Profitez du plaisir de courir.'
            },
            {
                'day': 'Mercredi',
                'day_date': (monday + datetime.timedelta(days=2)).strftime('%Y-%m-%d'),
                'type': 'tempo_leger',
                'type_display': 'Tempo Léger',
                'distance_km': run2_distance,
                'pace_target': run2_pace_str,
                'fc_target': f"{run2_fc_min}-{run2_fc_max} bpm",
                'fc_target_min': run2_fc_min,
                'fc_target_max': run2_fc_max,
                'predicted_time': run2_predicted_time,
                'zones_target': [2, 3],  # Zones 2-3
                'notes': 'Allure confortable, zone tempo. Respiration contrôlée.'
            },
            {
                'day': 'Vendredi',
                'day_date': (monday + datetime.timedelta(days=4)).strftime('%Y-%m-%d'),
                'type': 'tempo',
                'type_display': 'Tempo',
                'distance_km': run3_distance,
                'pace_target': run3_pace_str,
                'fc_target': f"{run3_fc_min}-{run3_fc_max} bpm",
                'fc_target_min': run3_fc_min,
                'fc_target_max': run3_fc_max,
                'predicted_time': run3_predicted_time,
                'zones_target': [3, 4],  # Zones 3-4
                'notes': 'Effort soutenu mais contrôlé. Maintenez l\'intensité.'
            },
            {
                'day': 'Dimanche',
                'day_date': (monday + datetime.timedelta(days=6)).strftime('%Y-%m-%d'),
                'type': 'long_run',
                'type_display': 'Long Run',
                'distance_km': run4_distance,
                'pace_target': run4_pace_str,
                'fc_target': f"{run4_fc_min}-{run4_fc_max} bpm",
                'fc_target_min': run4_fc_min,
                'fc_target_max': run4_fc_max,
                'predicted_time': run4_predicted_time,
                'zones_target': [2, 3],  # Zones 2-3
                'notes': 'Sortie longue endurance. Construire la capacité aérobie.'
            }
        ],
        'summary': {
            'total_distance': run1_distance + run2_distance + run3_distance + run4_distance,
            'total_time_predicted': f"{int((run1_predicted_time_sec + run2_predicted_time_sec + run3_predicted_time_sec + run4_predicted_time_sec) // 3600):02d}:{int(((run1_predicted_time_sec + run2_predicted_time_sec + run3_predicted_time_sec + run4_predicted_time_sec) % 3600) // 60):02d}",
            'balance': 'Semi-marathon: 2×5-6km + 1×10-11km + 1×12km+'
        }
    }

    return program


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
    import datetime
    from datetime import timedelta

    # Calculer date limite (X semaines en arrière)
    today = datetime.datetime.now()
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
                act_date = datetime.datetime.strptime(date_only, '%Y-%m-%d')
                if act_date >= cutoff_date.replace(hour=0, minute=0, second=0, microsecond=0):
                    recent_activities.append(act)
            except:
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
            objectives={},
            short_term={},
            activities_for_carousel=[],
            drive_error=f"⚠️ Données indisponibles (Drive) : {e}",
        )

    # ⚡ OPTIMISATION : Désactiver les traitements lourds au chargement de la page
    # Ces traitements peuvent être lancés manuellement via /refresh

    modified = False

    # 👣 Normalisation cadence (rapide, local)
    activities, changed_norm = normalize_cadence_in_place(activities)
    modified = modified or changed_norm

    # 🤖 Marquage fractionné (relativement rapide si modèle chargé)
    print("🤖 Marquage fractionné (is_fractionne / fractionne_prob)")
    activities, changed = apply_fractionne_flags(activities)
    modified = modified or changed

    # 📊 Enrichissement intelligent : calculer type_sortie, k_moy et deriv_cardio SEULEMENT pour les activités manquantes
    fc_max_fractionnes = get_fcmax_from_fractionnes(activities)
    enriched_count = 0
    type_count = 0
    for idx, activity in enumerate(activities):
        # 1) Assigner le type de séance si manquant
        if activity.get("type_sortie") in (None, "-", "inconnue"):
            activity["type_sortie"] = detect_session_type(activity)
            type_count += 1
            modified = True

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

    # 🎯 Charger les objectifs personnalisés depuis le profil
    # Note: Les objectifs sont maintenant gérés via /objectifs et ne sont plus recalculés automatiquement
    personalized_targets = profile.get('personalized_targets', {})
    print(f"🎯 Objectifs chargés: {personalized_targets}")

    # Charger les feedbacks
    feedbacks = load_feedbacks()

    # 🆕 Charger les commentaires IA sauvegardés
    ai_comments = load_ai_comments()

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
        weather_code_map = {
            0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
            45: "🌫️", 48: "🌫️", 51: "🌦️", 53: "🌧️",
            55: "🌧️", 61: "🌧️", 63: "🌧️", 65: "🌧️",
            71: "❄️", 73: "❄️", 75: "❄️", 80: "🌧️",
            81: "🌧️", 82: "🌧️", 95: "⛈️", 96: "⛈️", 99: "⛈️"
        }
        weather_emoji = weather_code_map.get(weather_code, "❓")

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

        # Feedback par défaut (sera remplacé par feedback utilisateur quand disponible)
        feedback = act.get('feedback', {
            'rating_stars': 3,
            'difficulty': 3,
            'legs_feeling': 'normal',
            'cardio_feeling': 'normal',
            'enjoyment': 'normal',
            'notes': ''
        })

        # Génération commentaire IA enrichi avec prompts externes
        # ⚡ OPTIMISATION: Désactivé au chargement page (trop lent)
        # Les commentaires IA seront générés à la demande via route dédiée
        ai_comment = ""
        # if segments and anthropic_client:
        #     try:
        #         print(f"   🤖 Génération commentaire IA...")
        #         ai_comment = generate_segment_analysis(
        #             act, feedback, profile, segments, patterns,
        #             segment_comparisons, cardiac_analysis
        #         )
        #         print(f"   ✅ Commentaire IA généré ({len(ai_comment)} car)")
        #     except Exception as e:
        #         print(f"   ⚠️ Erreur génération commentaire IA pour {act.get('date')}: {e}")
        #         ai_comment = "⚠️ Commentaire IA temporairement indisponible"

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
    import datetime
    today = datetime.date.today()
    current_week_number = today.isocalendar()[1]

    # Charger le programme existant s'il existe
    try:
        existing_program = read_weekly_plan()
        existing_week = existing_program.get('week_number') if existing_program else None
    except:
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
            past_week_analysis = analyze_past_week(existing_program, activities_sorted)
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
            except:
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
        except:
            pass
        print(f"♻️ Réutilisation programme existant (semaine {current_week_number})")

    # 🆕 Détecter si nouvelle activité (pour génération automatique des commentaires)
    # On considère qu'il y a une nouvelle activité si le nombre d'activités a changé
    # ou si la date de la plus récente est différente de celle en cache
    cached_comments = load_evolution_comments()
    last_activity_date = activities_sorted[0].get("date") if activities_sorted else None
    cached_last_date = cached_comments.get("_last_activity_date")
    has_new_run = (last_activity_date != cached_last_date)
    
    if has_new_run:
        print(f"🆕 Nouvelle activité détectée ({last_activity_date}), génération automatique des commentaires...")
        # Mettre à jour la date en cache
        cached_comments["_last_activity_date"] = last_activity_date
        save_evolution_comments(cached_comments)
        force_regenerate = True
    else:
        force_regenerate = False

    # 🆕 Commentaire IA sur l'évolution de l'efficacité cardio (10 dernières séances)
    k_evolution_comment = generate_k_evolution_comment(activities_sorted, personalized_targets, force_regenerate=force_regenerate)
    if k_evolution_comment:
        if force_regenerate:
            print(f"🤖 Commentaire IA efficacité cardio généré (nouveau run): {k_evolution_comment[:50]}...")
        else:
            print(f"📋 Commentaire IA efficacité cardio chargé depuis cache")
    else:
        print("ℹ️ Pas de commentaire IA efficacité cardio (données insuffisantes ou API non disponible)")

    # 🆕 Commentaire IA sur l'évolution de la dérive cardio (10 dernières séances)
    drift_evolution_comment = generate_drift_evolution_comment(activities_sorted, personalized_targets, force_regenerate=force_regenerate)
    if drift_evolution_comment:
        if force_regenerate:
            print(f"🤖 Commentaire IA dérive cardio généré (nouveau run): {drift_evolution_comment[:50]}...")
        else:
            print(f"📋 Commentaire IA dérive cardio chargé depuis cache")
    else:
        print("ℹ️ Pas de commentaire IA dérive cardio (données insuffisantes ou API non disponible)")
    print(f"📅 Programme hebdomadaire généré: {len(weekly_program['runs'])} runs, {weekly_program['summary']['total_distance']} km total")

    # Phase 3 Sprint 5: Analyse progression
    progression_analysis = analyze_progression(activities, weeks=4)
    print(f"📈 Analyse progression: {progression_analysis['runs_completed']} runs, score {progression_analysis.get('fitness_score', 'N/A')}/10")

    # 👟 Calcul kilométrage chaussures
    shoe_km, shoe_status = calculate_shoe_kilometers(activities_sorted, profile)
    print(f"👟 Chaussures: {shoe_km} km, statut: {shoe_status}")

    return render_template(
        "index.html",
        dashboard=dashboard,
        objectives=load_objectives(),
        short_term=load_short_term_objectives(),
        activities_for_carousel=activities_for_carousel,
        running_stats=running_stats,
        weekly_program=weekly_program,  # Phase 3 Sprint 3
        progression_analysis=progression_analysis,  # Phase 3 Sprint 5
        k_evolution_comment=k_evolution_comment,  # Commentaire IA sur évolution efficacité cardio
        drift_evolution_comment=drift_evolution_comment,  # Commentaire IA sur évolution dérive cardio
        shoe_km=shoe_km,  # Kilométrage chaussures
        shoe_status=shoe_status,  # Statut d'usure chaussures
        personalized_targets=personalized_targets,  # 🎯 Objectifs personnalisés k et drift
        past_week_analysis=past_week_analysis,  # 📊 Analyse semaine écoulée (réalisé vs programmé)
        past_week_comment=past_week_comment  # 🤖 Commentaire IA sur semaine écoulée
    )


    
@app.route("/refresh")
def refresh():
    """Recalcule et met à jour activities.json sur Drive"""
    print("♻️ Recalcul des activités...")
    try:
        # 1) Lire depuis Drive
        activities = load_activities_from_drive()

        # 2) Enrichir (ta fonction existante)
        activities = enrich_activities(activities)

        # 3) Écrire sur Drive
        save_activities_to_drive(activities)

        print("✅ activities.json mis à jour sur Drive")
        return "✅ Données mises à jour", 200

    except DriveUnavailableError as e:
        print(f"❌ Drive indisponible: {e}")
        return f"❌ Données non mises à jour (Drive): {e}", 503

    except Exception as e:
        print(f"❌ Erreur refresh: {e}")
        return f"❌ Erreur interne: {e}", 500


@app.route('/force_week_transition')
def force_week_transition():
    """Force la transition vers une nouvelle semaine (analyse semaine en cours + génère nouveau programme)"""
    print("🔄 Transition de semaine forcée manuellement...")

    try:
        # Charger les données nécessaires
        activities = load_activities_from_drive()
        activities = enrich_activities(activities)
        activities_sorted = sorted(activities, key=lambda x: x.get('date', ''), reverse=True)
        profile = load_profile()

        # Charger le programme actuel
        current_program = read_weekly_plan()
        current_week_number = current_program.get('week_number') if current_program else None

        if not current_program or not current_week_number:
            return "❌ Aucun programme actuel trouvé. Rechargez la page d'abord.", 404

        # Analyser la semaine en cours (même si pas terminée)
        print(f"📊 Analyse de la semaine en cours (semaine {current_week_number})...")
        past_week_analysis = analyze_past_week(current_program, activities_sorted)

        if past_week_analysis:
            # Générer le commentaire IA
            past_week_comment = generate_past_week_comment(past_week_analysis)
            if past_week_comment:
                past_week_analysis['comment'] = past_week_comment

            # Sauvegarder l'analyse
            write_output_json('past_week_analysis.json', past_week_analysis)
            print(f"✅ Analyse semaine {current_week_number}: {past_week_analysis['runs_completed']}/{past_week_analysis['total_programmed']} runs ({past_week_analysis['adherence_rate']}% adhésion)")
            print(f"💾 Analyse sauvegardée")
        else:
            print("⚠️ Impossible d'analyser la semaine en cours")
            return "❌ Erreur lors de l'analyse de la semaine", 500

        # Générer le nouveau programme pour la semaine suivante
        import datetime
        next_week_number = current_week_number + 1
        if next_week_number > 52:
            next_week_number = 1

        print(f"📅 Génération du nouveau programme (semaine {next_week_number})...")
        new_program = generate_weekly_program(profile, activities)
        new_program['week_number'] = next_week_number

        # Recalculer les dates pour la nouvelle semaine
        # Trouver le lundi de la semaine suivante
        today = datetime.date.today()
        current_iso_week = today.isocalendar()[1]

        if next_week_number == current_iso_week + 1:
            # Semaine suivante normale
            days_until_monday = (7 - today.weekday()) if today.weekday() != 0 else 7
            next_monday = today + datetime.timedelta(days=days_until_monday)
        else:
            # Transition manuelle, on prend le lundi de la semaine ISO demandée
            next_monday = datetime.date.fromisocalendar(today.year, next_week_number, 1)

        next_sunday = next_monday + datetime.timedelta(days=6)
        new_program['start_date'] = next_monday.isoformat()
        new_program['end_date'] = next_sunday.isoformat()
        new_program['generated_at'] = datetime.datetime.now().isoformat()

        # Mettre à jour les dates des runs
        for run in new_program['runs']:
            day_name = run['day']
            day_mapping = {
                'Lundi': 0, 'Mardi': 1, 'Mercredi': 2, 'Jeudi': 3,
                'Vendredi': 4, 'Samedi': 5, 'Dimanche': 6
            }
            if day_name in day_mapping:
                day_offset = day_mapping[day_name]
                run_date = next_monday + datetime.timedelta(days=day_offset)
                run['day_date'] = run_date.isoformat()

        # Sauvegarder le nouveau programme
        write_weekly_plan(new_program)
        print(f"💾 Nouveau programme sauvegardé pour semaine {next_week_number}")

        # Retourner un résumé
        result = {
            'success': True,
            'previous_week': current_week_number,
            'new_week': next_week_number,
            'analysis': {
                'runs_completed': past_week_analysis['runs_completed'],
                'total_programmed': past_week_analysis['total_programmed'],
                'adherence_rate': past_week_analysis['adherence_rate'],
                'types_respected': past_week_analysis.get('types_respected', 0),
                'type_respect_rate': past_week_analysis.get('type_respect_rate', 0),
                'comment': past_week_comment
            },
            'new_program': {
                'start_date': new_program['start_date'],
                'end_date': new_program['end_date'],
                'runs': len(new_program['runs']),
                'total_distance': new_program['summary']['total_distance']
            }
        }

        return f"""✅ Transition de semaine effectuée

📊 Analyse semaine {current_week_number}:
- Runs réalisés: {past_week_analysis['runs_completed']}/{past_week_analysis['total_programmed']} ({past_week_analysis['adherence_rate']}%)
- Types respectés: {past_week_analysis.get('types_respected', 0)}/{past_week_analysis['runs_completed']} ({past_week_analysis.get('type_respect_rate', 0)}%)
- Distance: {past_week_analysis['total_distance_realized']:.1f} km / {past_week_analysis['total_distance_programmed']} km

📅 Nouveau programme semaine {next_week_number}:
- Période: {new_program['start_date']} au {new_program['end_date']}
- {len(new_program['runs'])} runs planifiés
- {new_program['summary']['total_distance']} km total

Rechargez la page pour voir les changements.""", 200

    except Exception as e:
        print(f"❌ Erreur transition de semaine: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Erreur: {e}", 500


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
        # Charger et enrichir les activités
        activities = load_activities_from_drive()
        activities = enrich_activities(activities)  # 🆕 Enrichir TOUTES les activités d'abord

        # Trouver l'activité correspondante
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
            activity["type_sortie"] = detect_session_type(activity)
            print(f"🏃 Type de séance détecté: {activity['type_sortie']}")

        # ✅ VALIDATION : Vérifier que l'allure est valide après enrichissement
        allure = activity.get('allure')
        if not allure or allure == '-:--' or allure == '-' or allure == 'N/A':
            return jsonify({
                'error': '❌ Impossible de calculer l\'allure pour cette activité (données GPS insuffisantes)',
                'needs_pace': True
            }), 400

        # Charger le profil
        profile = load_profile()

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

        # Vérifier que le client Anthropic est disponible
        if not anthropic_client:
            return jsonify({'error': 'Service IA temporairement indisponible (API key manquante)'}), 503

        # Générer le commentaire IA
        print(f"🤖 Génération commentaire IA pour {activity_date}...")
        ai_comment = generate_segment_analysis(
            activity, feedback, profile, segments, patterns,
            segment_comparisons, cardiac_analysis, activities
        )
        print(f"✅ Commentaire généré: {len(ai_comment)} caractères")

        # 🆕 Sauvegarder le commentaire généré
        save_ai_comment(activity_date, ai_comment, len(segments), len(patterns))

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


@app.route('/regenerate_evolution_comments')
def regenerate_evolution_comments():
    """
    Route pour regénérer les commentaires IA d'évolution (k et drift).
    Force la regénération même si un cache existe.
    """
    try:
        activities = load_activities_from_drive()
        activities_sorted = sorted(activities, key=_date_key, reverse=True)

        # Calculer les objectifs personnalisés
        profile = load_profile()
        personalized_targets = calculate_personalized_targets(profile, activities)

        print("🔄 Regénération forcée des commentaires IA d'évolution...")
        k_comment = generate_k_evolution_comment(activities_sorted, personalized_targets, force_regenerate=True)
        drift_comment = generate_drift_evolution_comment(activities_sorted, personalized_targets, force_regenerate=True)
        
        return jsonify({
            'success': True,
            'k_comment': k_comment,
            'drift_comment': drift_comment,
            'message': 'Commentaires regénérés avec succès'
        })
    except Exception as e:
        print(f"❌ Erreur regénération commentaires: {e}")
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

    return jsonify({'success': True, 'message': 'Objectifs mis à jour'})


@app.route('/zones-entrainement', methods=['GET'])
def zones_entrainement():
    """Page de documentation des zones d'entraînement"""
    return render_template('zones_entrainement.html')


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

    return jsonify({
        'success': True,
        'message': f'{len(updated)} objectifs recalculés',
        'targets': updated
    })


@app.route('/generate_short_term_plan')
def generate_short_term_plan():
    profile = load_profile()
    activities = load_activities_from_drive()
    prompt_template = load_short_term_prompt_from_drive()

    # Exemple simple pour construire prompt
    prompt = prompt_template
    prompt += f"\nProfil: {profile}"
    prompt += f"\nActivités récentes: {len(activities)}"

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=1000
        )
        result_str = response.choices[0].message.content.strip()

        # Essayer de parser la réponse JSON (précise à OpenAI de répondre en JSON strict)
        short_term_objectives = json.loads(result_str)

        # Ajouter conversion allures au format décimal si besoin
        short_term_objectives = convert_short_term_allures(short_term_objectives)

        write_output_json('short_term_objectives.json', short_term_objectives)

        print("✅ Coaching court terme généré et sauvegardé.")

        return redirect('/')  # ou retourner un message / JSON si API

    except Exception as e:
        print("❌ Erreur génération coaching court terme:", e)
        return f"Erreur génération coaching: {e}", 500
        
@app.route("/recompute_session_types")
def recompute_session_types():
    """Recalcule le type_sortie de toutes les activités avec la règle par distance."""
    activities = load_activities_from_drive()
    print(f"♻️ Recalcul session_type pour {len(activities)} activités")

    for act in activities:
        # Toujours recalculer, même si déjà défini
        act["type_sortie"] = detect_session_type(act)

    save_activities_to_drive(activities)
    print("✅ activities.json mis à jour avec nouveaux session_type")
    return f"✅ Recalculé pour {len(activities)} activités"
    
@app.route("/recompute_fractionne_flags")
def recompute_fractionne_flags():
    activities = load_activities_from_drive()
    activities, changed = apply_fractionne_flags(activities)
    if changed:
        save_activities_to_drive(activities)
        msg = f"✅ Flags fractionné mis à jour ({len(activities)} activités)"
    else:
        msg = "ℹ️ Aucun changement sur les flags fractionné"
    print(msg)
    return msg
    
@app.route("/export_fractionne_excel")
def export_fractionne_excel():
    activities = load_activities_from_drive()
    rows = []
    for a in activities:
        aid = a.get("activity_id")
        label = a.get("is_fractionne_label", "")
        rows.append({"activity_id": aid, "fractionne_label": label})
    df = pd.DataFrame(rows)
    excel_path = "fractionne_labels.xlsx"
    df.to_excel(excel_path, index=False)
    return f"✅ Fichier exporté : {excel_path}"

@app.route("/import_fractionne_excel")
def import_fractionne_excel():
    import pandas as pd
    excel_path = "fractionne_labels.xlsx"
    df = pd.read_excel(excel_path)
    label_map = dict(zip(df["activity_id"], df["fractionne_label"]))

    activities = load_activities_from_drive()
    changed = 0
    for a in activities:
        aid = a.get("activity_id")
        if aid in label_map and pd.notna(label_map[aid]):
            new_val = bool(label_map[aid])
            if a.get("is_fractionne_label") != new_val:
                a["is_fractionne_label"] = new_val
                changed += 1

    if changed > 0:
        save_activities_to_drive(activities)

    return f"✅ {changed} activités mises à jour depuis Excel"
    
@app.route("/debug_autotrain_status")
def debug_autotrain_status():
    activities = load_activities_from_drive()

    # mêmes calculs que les helpers
    meta = _load_last_train_meta()
    last_cnt = meta.get("last_trained_count", 0)
    cur_cnt = len(activities)

    pos = neg = 0
    for a in activities:
        if "is_fractionne_label" in a:
            if bool(a["is_fractionne_label"]): pos += 1
            else: neg += 1

    eligible = (cur_cnt > last_cnt) and (pos >= 8 and neg >= 8)

    return (
        f"AUTO_RETRAIN_XGB={AUTO_RETRAIN_XGB}<br>"
        f"last_trained_count={last_cnt}<br>"
        f"current_activities={cur_cnt}<br>"
        f"new_activities={cur_cnt - last_cnt}<br>"
        f"labels_pos={pos}, labels_neg={neg} (min 8/8)<br>"
        f"eligible={eligible}"
    )
    
@app.route("/force_autotrain_xgb")
def force_autotrain_xgb():
    ok = _retrain_fractionne_model_and_reload()
    return "✅ Auto-train OK" if ok else "❌ Auto-train échoué", (200 if ok else 500)
    
@app.route("/recompute_denivele")
def recompute_denivele():
    activities = load_activities_from_drive()
    changed = 0
    for act in activities:
        pts = act.get("points", [])
        new_gain = _compute_denivele_pos(pts)
        if act.get("gain_alt") != new_gain:
            act["gain_alt"] = new_gain
            changed += 1
    if changed:
        save_activities_to_drive(activities)
        msg = f"✅ Dénivelé positif recalculé sur {changed} activité(s)"
    else:
        msg = "ℹ️ Aucun changement de dénivelé détecté"
    print(msg)
    return msg


@app.route("/sync_strava_deletions")
def sync_strava_deletions():
    """Synchronise avec Strava pour détecter les activités supprimées."""
    try:
        import subprocess
        result = subprocess.run(
            ["python3", "sync_strava.py"],
            cwd="/opt/app/Track2Train",
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            # Parser la sortie pour extraire le rapport
            output = result.stdout
            return f"<pre>{output}</pre>", 200
        else:
            return f"❌ Erreur sync:<br><pre>{result.stderr}</pre>", 500

    except subprocess.TimeoutExpired:
        return "❌ Timeout (>120s)", 500
    except Exception as e:
        return f"❌ Erreur: {e}", 500


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
