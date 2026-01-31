#!/usr/bin/env python3
"""
Script pour recalculer toutes les zones FC avec la méthode Karvonen/LTHR
"""

import json
import os
from pathlib import Path

# Charger le profil
profile_path = Path(__file__).parent / "outputs" / "profile.json"
with open(profile_path, 'r') as f:
    profile = json.load(f)

hr_rest = profile.get('hr_rest', 59)
hr_max = profile.get('hr_max', 170)
hr_reserve = hr_max - hr_rest  # Réserve cardiaque

print(f"📊 Paramètres Karvonen:")
print(f"  FC Repos: {hr_rest} bpm")
print(f"  FC Max: {hr_max} bpm")
print(f"  Réserve cardiaque: {hr_reserve} bpm")
print()

# Définir les zones selon Karvonen
# Zone 1: 50-60% (Récupération active)
# Zone 2: 60-70% (Endurance fondamentale)
# Zone 3: 70-80% (Tempo)
# Zone 4: 80-90% (Seuil/VO2max)
# Zone 5: 90-100% (Anaérobie)

zones_karvonen = {
    1: (0.50, 0.60),
    2: (0.60, 0.70),
    3: (0.70, 0.80),
    4: (0.80, 0.90),
    5: (0.90, 1.00)
}

print("🎯 Zones FC Karvonen calculées:")
for zone, (min_pct, max_pct) in zones_karvonen.items():
    min_hr = int((hr_reserve * min_pct) + hr_rest)
    max_hr = int((hr_reserve * max_pct) + hr_rest)
    print(f"  Zone {zone}: {min_hr}-{max_hr} bpm ({int(min_pct*100)}-{int(max_pct*100)}%)")

print()

# Fonction pour classifier une FC dans une zone
def get_zone_karvonen(hr, hr_rest, hr_max):
    """Retourne la zone (1-5) pour une FC donnée selon Karvonen"""
    if hr <= 0 or hr_max <= hr_rest:
        return None

    hr_reserve = hr_max - hr_rest
    intensity = (hr - hr_rest) / hr_reserve

    if intensity < 0.50:
        return 1
    elif intensity < 0.60:
        return 1
    elif intensity < 0.70:
        return 2
    elif intensity < 0.80:
        return 3
    elif intensity < 0.90:
        return 4
    else:
        return 5

# Charger les activités
activities_path = Path(__file__).parent / "activities.json"
if not activities_path.exists():
    activities_path = Path(__file__).parent / "outputs" / "activities.json"

with open(activities_path, 'r') as f:
    activities = json.load(f)

print(f"📁 {len(activities)} activités chargées")
print()

# Recalculer les zones pour chaque activité
activities_updated = 0
total_hr_values = []

for activity in activities:
    points = activity.get('points', [])
    if not points:
        continue

    # Récupérer toutes les FC
    hr_values = [p.get('heartrate', 0) for p in points if p.get('heartrate', 0) > 0]
    if not hr_values:
        continue

    total_hr_values.extend(hr_values)

    # Recalculer les zones en pourcentage de temps
    zone_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

    for hr in hr_values:
        zone = get_zone_karvonen(hr, hr_rest, hr_max)
        if zone:
            zone_counts[zone] += 1

    total_points = sum(zone_counts.values())
    if total_points == 0:
        continue

    # Calculer pourcentages
    zone_percentages = {
        zone: round((count / total_points) * 100, 1)
        for zone, count in zone_counts.items()
    }

    # Mettre à jour l'activité
    if 'cardiac_analysis' not in activity:
        activity['cardiac_analysis'] = {}

    if 'hr_zones' not in activity['cardiac_analysis']:
        activity['cardiac_analysis']['hr_zones'] = {}

    activity['cardiac_analysis']['hr_zones']['zone_percentages'] = zone_percentages
    activity['cardiac_analysis']['hr_zones']['method'] = 'karvonen'
    activity['cardiac_analysis']['hr_zones']['hr_rest'] = hr_rest
    activity['cardiac_analysis']['hr_zones']['hr_max'] = hr_max

    activities_updated += 1

print(f"✅ {activities_updated} activités mises à jour avec zones Karvonen")
print()

# Calculer LTHR (moyenne FC des 10 derniers runs tempo/endurance)
print("📈 Calcul du LTHR (Lactate Threshold Heart Rate)...")

# Filtrer les runs de type tempo/endurance/long_run (pas récupération)
tempo_runs = []
for activity in activities[::-1]:  # Du plus récent au plus ancien
    fc_moy = activity.get('fc_moy', 0)
    if fc_moy <= 0:
        continue

    # Classifier le run selon distance et allure
    dist_km = activity.get('distance_km', 0)
    if dist_km < 7:
        continue  # Exclure les runs courts (récupération/tempo court)

    tempo_runs.append(fc_moy)

    if len(tempo_runs) >= 10:
        break

if tempo_runs:
    lthr = int(sum(tempo_runs) / len(tempo_runs))
    lthr_percentage = ((lthr - hr_rest) / hr_reserve) * 100

    print(f"  ✅ LTHR calculé: {lthr} bpm (basé sur {len(tempo_runs)} runs)")
    print(f"  📊 LTHR = {lthr_percentage:.1f}% de la réserve cardiaque")
    print(f"  🎯 LTHR se situe en Zone {get_zone_karvonen(lthr, hr_rest, hr_max)}")

    # Sauvegarder le LTHR dans le profil
    profile['lthr'] = lthr
    profile['lthr_calculated_from'] = len(tempo_runs)

    with open(profile_path, 'w') as f:
        json.dump(profile, f, indent=2)

    print(f"  💾 LTHR sauvegardé dans le profil")
else:
    print("  ⚠️ Pas assez de données pour calculer le LTHR")

print()

# Sauvegarder les activités
with open(activities_path, 'w') as f:
    json.dump(activities, f, indent=2)

print(f"💾 Activités sauvegardées avec nouvelles zones Karvonen")
print()
print("🎉 Recalcul terminé!")
print()
print("📊 Statistiques globales:")
if total_hr_values:
    avg_hr = int(sum(total_hr_values) / len(total_hr_values))
    print(f"  FC moyenne sur toutes les activités: {avg_hr} bpm")
    print(f"  Zone moyenne: Zone {get_zone_karvonen(avg_hr, hr_rest, hr_max)}")
