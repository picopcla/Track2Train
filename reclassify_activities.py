#!/usr/bin/env python3
"""
Script pour reclassifier toutes les activités selon la nouvelle typologie:
- tempo_recup: ≤ 6.5 km ET allure ≥ 5:00
- tempo_rapide: ≤ 6.5 km ET allure < 5:00
- endurance: 6.5-12 km
- long_run: > 12 km
"""

import json
import math
from datetime import datetime


def haversine(lat1, lon1, lat2, lon2):
    """Calcule la distance entre deux points GPS en km"""
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2) * math.sin(dlat/2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon/2) * math.sin(dlon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def calculate_distance_from_gps(points):
    """Calcule la distance totale depuis les points GPS"""
    if len(points) < 2:
        return 0.0

    total_dist = 0
    for i in range(1, len(points)):
        lat1 = points[i-1].get('lat')
        lon1 = points[i-1].get('lng')
        lat2 = points[i].get('lat')
        lon2 = points[i].get('lng')

        if all([lat1, lon1, lat2, lon2]):
            dist = haversine(lat1, lon1, lat2, lon2)
            total_dist += dist

    return total_dist


def calculate_allure_from_gps(points):
    """
    Calcule l'allure moyenne depuis les points GPS

    Returns:
        float: Allure en min/km (ex: 5.5 pour 5:30/km) ou None
    """
    if len(points) < 2:
        return None

    # Get total distance and time
    total_dist = 0
    total_time = 0

    for i in range(1, len(points)):
        lat1 = points[i-1].get('lat')
        lon1 = points[i-1].get('lng')
        lat2 = points[i].get('lat')
        lon2 = points[i].get('lng')
        time1 = points[i-1].get('time', 0)
        time2 = points[i].get('time', 0)

        if all([lat1, lon1, lat2, lon2]):
            dist = haversine(lat1, lon1, lat2, lon2)
            total_dist += dist
            total_time += (time2 - time1)

    if total_dist > 0 and total_time > 0:
        # time is in seconds, distance in km
        # allure = minutes per km
        allure = (total_time / 60) / total_dist
        return allure

    return None


def parse_allure(allure_str):
    """Convertit une allure '5:30' en décimal 5.5"""
    if not allure_str:
        return None
    try:
        parts = allure_str.split(':')
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60
    except:
        pass
    return None


def classify_activity(distance_km, allure_str):
    """
    Classifie une activité selon la nouvelle typologie

    Args:
        distance_km: Distance en kilomètres
        allure_str: Allure au format "5:30" ou None

    Returns:
        tuple: (type_sortie, session_category)
    """
    # Parse allure
    allure_dec = parse_allure(allure_str)

    # Classification
    if distance_km <= 6.5:
        # Tempo court: distinguer rapide vs récup
        if allure_dec and allure_dec < 5.0:  # < 5:00/km
            return 'tempo_rapide', 'tempo_rapide'
        else:
            return 'tempo_recup', 'tempo_recup'

    elif 6.5 < distance_km <= 12:
        return 'endurance', 'endurance'

    else:  # > 12 km
        return 'long_run', 'long_run'


def reclassify_all_activities(dry_run=True):
    """
    Reclassifie toutes les activités

    Args:
        dry_run: Si True, sauvegarde dans un fichier temporaire, sinon écrase activities.json
    """
    # Load activities
    with open('activities.json', 'r') as f:
        activities = json.load(f)

    print(f"📊 Traitement de {len(activities)} activités...\n")

    # Statistics
    stats = {
        'tempo_recup': 0,
        'tempo_rapide': 0,
        'endurance': 0,
        'long_run': 0,
        'no_distance': 0
    }

    changes = []

    for i, act in enumerate(activities):
        points = act.get('points', [])

        # Get or calculate distance
        distance_km = act.get('distance_km')

        if not distance_km:
            # Calculate from GPS
            if points:
                distance_km = calculate_distance_from_gps(points)
            else:
                stats['no_distance'] += 1
                continue

        # Get or calculate allure
        allure = act.get('allure')
        allure_calculated = False

        if not allure and points:
            # Calculate from GPS
            allure_dec = calculate_allure_from_gps(points)
            if allure_dec:
                # Convert to "5:30" format
                mins = int(allure_dec)
                secs = int((allure_dec - mins) * 60)
                allure = f"{mins}:{secs:02d}"
                allure_calculated = True

        # Classify
        old_type = act.get('type_sortie')
        old_category = act.get('session_category')

        new_type, new_category = classify_activity(distance_km, allure)

        # Update
        act['type_sortie'] = new_type
        act['session_category'] = new_category

        # Ensure distance_km is set
        if not act.get('distance_km'):
            act['distance_km'] = round(distance_km, 2)

        # Save calculated allure if computed
        if allure_calculated and not act.get('allure'):
            act['allure'] = allure

        # Stats
        stats[new_type] += 1

        # Track changes
        if old_type != new_type or old_category != new_category:
            changes.append({
                'date': act.get('date', 'N/A'),
                'distance': distance_km,
                'allure': allure,
                'old_type': old_type,
                'old_category': old_category,
                'new_type': new_type,
                'new_category': new_category
            })

    # Display results
    print("=" * 60)
    print("RÉSULTATS DE LA CLASSIFICATION")
    print("=" * 60)
    print(f"\ntempo_recup:  {stats['tempo_recup']:3d} activités")
    print(f"tempo_rapide: {stats['tempo_rapide']:3d} activités")
    print(f"endurance:    {stats['endurance']:3d} activités")
    print(f"long_run:     {stats['long_run']:3d} activités")
    print(f"Sans distance: {stats['no_distance']:3d} activités")
    print(f"\nTotal traité: {sum(stats.values()) - stats['no_distance']:3d} / {len(activities)}")

    print(f"\n\n📝 {len(changes)} activités reclassifiées")

    if changes and len(changes) <= 20:
        print("\nDétail des changements:")
        for ch in changes[:20]:
            print(f"\n  {ch['date'][:10]} - {ch['distance']:.2f}km - {ch['allure'] or 'N/A'}")
            print(f"    {ch['old_type']} → {ch['new_type']}")

    # Save
    if dry_run:
        output_file = '/tmp/activities_reclassified.json'
        print(f"\n\n💾 Mode DRY RUN: sauvegarde dans {output_file}")
    else:
        output_file = 'activities.json'
        print(f"\n\n💾 Sauvegarde dans {output_file}")

    with open(output_file, 'w') as f:
        json.dump(activities, f, indent=2, ensure_ascii=False)

    print(f"✅ Fichier sauvegardé: {output_file}")

    return stats, changes


if __name__ == '__main__':
    import sys

    # Check if --apply flag is provided
    dry_run = '--apply' not in sys.argv

    if dry_run:
        print("⚠️  MODE DRY RUN - Les modifications ne seront PAS appliquées à activities.json")
        print("    Utilisez --apply pour appliquer les changements\n")
    else:
        print("🔥 MODE APPLICATION - activities.json sera modifié !\n")
        response = input("Êtes-vous sûr ? (oui/non): ")
        if response.lower() != 'oui':
            print("❌ Annulé")
            sys.exit(0)

    stats, changes = reclassify_all_activities(dry_run=dry_run)
