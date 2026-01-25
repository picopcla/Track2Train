"""
Calcul des statistiques de running par type de sortie
Appelé après chaque run pour mettre à jour les moyennes
"""
import json
import numpy as np
from datetime import datetime
from pathlib import Path


def get_segments_count(run_type):
    """
    Détermine le nombre de segments selon le type de run

    Args:
        run_type: Type de sortie (tempo_recup, tempo_rapide, endurance, long_run)

    Returns:
        int: Nombre de segments
    """
    # Nouveaux types
    if run_type == 'tempo_recup' or run_type == 'tempo_rapide':
        return 2
    elif run_type == 'endurance':
        return 3
    elif run_type == 'long_run':
        return 4
    # Anciens types pour compatibilité
    elif run_type == 'normal_5k':
        return 2
    elif run_type == 'normal_10k':
        return 3
    else:
        return 2  # Par défaut


def calculate_fc_by_segments(points, num_segments):
    """
    Calcule la FC moyenne par segments de distance

    Args:
        points: Liste des points GPS du run
        num_segments: Nombre de segments à découper

    Returns:
        list: FC moyenne de chaque segment (ou None si pas de données)
    """
    if not points:
        return None

    # Récupérer la distance totale
    distances = [p.get('distance') for p in points if p.get('distance') is not None]
    if not distances:
        return None

    total_distance = max(distances)
    if total_distance == 0:
        return None

    # Calculer les bornes de chaque segment
    segment_size = total_distance / num_segments
    fc_segments = []

    for i in range(num_segments):
        dist_min = i * segment_size
        dist_max = (i + 1) * segment_size

        # Filtrer les points dans ce segment
        hrs_in_segment = [
            p.get('hr')
            for p in points
            if p.get('distance') is not None
            and p.get('hr') is not None
            and dist_min <= p.get('distance') < dist_max
        ]

        # Calculer la moyenne FC de ce segment
        if hrs_in_segment:
            fc_segments.append(np.mean(hrs_in_segment))
        else:
            fc_segments.append(None)

    return fc_segments if any(fc_segments) else None


def calculate_stats_by_type(activities, n_last=15):
    """
    Calcule les statistiques des N dernières courses PAR TYPE de run

    Args:
        activities: Liste des activités
        n_last: Nombre de courses à considérer (défaut: 15)

    Returns:
        dict: Statistiques par type de run
    """
    # Trier par date (plus récentes en premier)
    activities_sorted = sorted(activities, key=lambda x: x.get('date', ''), reverse=True)

    # Grouper par type de run (session_category après reclassification)
    by_type = {}
    for act in activities_sorted:
        # Utiliser session_category en priorité, sinon type_sortie pour compatibilité
        run_type = act.get('session_category') or act.get('type_sortie', 'inconnue')
        if run_type not in by_type:
            by_type[run_type] = []
        by_type[run_type].append(act)

    # Calculer les stats pour chaque type
    stats_by_type = {}

    for run_type, runs in by_type.items():
        # Prendre les N dernières courses de ce type
        recent_runs = runs[:n_last]

        if not recent_runs:
            continue

        # Déterminer le nombre de segments pour ce type
        num_segments = get_segments_count(run_type)

        # Extraire les métriques
        fc_moyennes = []
        fc_max_values = []
        allures = []
        k_values = []
        deriv_values = []
        distances = []
        fc_segments_all_runs = []  # Liste de listes pour chaque run

        for run in recent_runs:
            points = run.get('points', [])
            if not points:
                continue

            # FC
            hrs = [p.get('hr') for p in points if p.get('hr') is not None]
            if hrs:
                fc_moyennes.append(np.mean(hrs))
                fc_max_values.append(max(hrs))

            # FC par segments
            fc_segs = calculate_fc_by_segments(points, num_segments)
            if fc_segs:
                fc_segments_all_runs.append(fc_segs)

            # Distance totale
            dists = [p.get('distance') for p in points if p.get('distance') is not None]
            if dists:
                total_dist_km = max(dists) / 1000
                distances.append(total_dist_km)
            else:
                continue

            # Temps total
            times = [p.get('time') for p in points if p.get('time') is not None]
            if times:
                total_time_min = max(times) / 60
            else:
                continue

            # Allure moyenne du run = temps total / distance totale
            if total_dist_km > 0:
                allure_moy = total_time_min / total_dist_km
                allures.append(allure_moy)

            # k_moy et dérive
            if run.get('k_moy') is not None:
                k_values.append(run.get('k_moy'))
            if run.get('deriv_cardio') is not None:
                deriv_values.append(run.get('deriv_cardio'))

        # Calculer la moyenne des FC par segments
        fc_segments_moyennes = None
        if fc_segments_all_runs:
            # Transposer pour avoir [segment1_valeurs, segment2_valeurs, ...]
            num_segs = len(fc_segments_all_runs[0])
            fc_segments_moyennes = []
            for i in range(num_segs):
                # Extraire les valeurs du segment i de tous les runs
                segment_values = [
                    run_segs[i]
                    for run_segs in fc_segments_all_runs
                    if i < len(run_segs) and run_segs[i] is not None
                ]
                if segment_values:
                    fc_segments_moyennes.append(round(np.mean(segment_values), 1))
                else:
                    fc_segments_moyennes.append(None)

        # Calculer les moyennes et ranges
        stats = {
            'type': run_type,
            'nombre_courses': len(recent_runs),
            'derniere_date': recent_runs[0].get('date', '')[:10] if recent_runs else None,
            'distance': {
                'moyenne': round(np.mean(distances), 2) if distances else None,
                'min': round(min(distances), 2) if distances else None,
                'max': round(max(distances), 2) if distances else None
            },
            'fc_moyenne': {
                'moyenne': round(np.mean(fc_moyennes), 1) if fc_moyennes else None,
                'min': round(min(fc_moyennes), 1) if fc_moyennes else None,
                'max': round(max(fc_moyennes), 1) if fc_moyennes else None
            },
            'fc_max': {
                'moyenne': round(np.mean(fc_max_values), 1) if fc_max_values else None,
                'min': round(min(fc_max_values), 1) if fc_max_values else None,
                'max': round(max(fc_max_values), 1) if fc_max_values else None
            },
            'fc_segments': fc_segments_moyennes,
            'allure': {
                'moyenne': round(np.mean(allures), 2) if allures else None,
                'min': round(min(allures), 2) if allures else None,
                'max': round(max(allures), 2) if allures else None
            },
            'k_moy': {
                'moyenne': round(np.mean(k_values), 2) if k_values else None,
                'min': round(min(k_values), 2) if k_values else None,
                'max': round(max(k_values), 2) if k_values else None,
                'tendance': 'hausse' if len(k_values) >= 3 and k_values[0] > np.mean(k_values[1:]) else 'baisse'
            },
            'deriv_cardio': {
                'moyenne': round(np.mean(deriv_values), 3) if deriv_values else None,
                'min': round(min(deriv_values), 3) if deriv_values else None,
                'max': round(max(deriv_values), 3) if deriv_values else None
            }
        }

        stats_by_type[run_type] = stats

    return stats_by_type


def save_running_stats(stats_by_type, output_file='running_stats.json'):
    """
    Sauvegarde les statistiques dans un fichier JSON

    Args:
        stats_by_type: Dictionnaire des stats par type
        output_file: Nom du fichier de sortie
    """
    output_path = Path(output_file)

    # Ajouter metadata
    output_data = {
        'generated_at': datetime.now().isoformat(),
        'stats_by_type': stats_by_type,
        'summary': {
            'types_disponibles': list(stats_by_type.keys()),
            'total_types': len(stats_by_type)
        }
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"✅ Stats sauvegardées dans {output_path}")
    return output_path




if __name__ == "__main__":
    # Test : charger activities.json et calculer les stats
    with open('activities.json', 'r') as f:
        activities = json.load(f)

    print(f"📂 Chargement de {len(activities)} activités")

    # Calculer les stats
    stats = calculate_stats_by_type(activities, n_last=15)

    # Sauvegarder
    save_running_stats(stats, 'running_stats.json')
