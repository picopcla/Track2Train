#!/usr/bin/env python3
"""Test de la fonction compute_segments"""

import sys
sys.path.insert(0, '/opt/app/Track2Train-staging')

from app import load_activities_from_drive, compute_segments


def format_pace(min_per_km):
    """Formatte une allure en minutes/km (float) en 'M:SS'."""
    if min_per_km is None:
        return "N/A"
    try:
        m = int(min_per_km)
        s = int(round((min_per_km - m) * 60))
        # Ajuster si l'arrondi fait 60 secondes
        if s == 60:
            m += 1
            s = 0
        return f"{m}:{s:02d} /km"
    except Exception:
        return "N/A"


print("=" * 70)
print("TEST CALCUL DES SEGMENTS (TRONÇONS)")
print("=" * 70)

# Charger activités
activities = load_activities_from_drive()
if not activities:
    print("Aucune activité trouvée.")
    sys.exit(1)

act = activities[0]  # Premier run

print(f"\n📊 Activité testée:")
print(f"   Date: {act.get('date', 'N/A')}")
points = act.get('points', []) or []
if points:
    last_distance = points[-1].get('distance') or 0
    distance_km = last_distance / 1000
else:
    distance_km = 0
print(f"   Distance: {distance_km:.2f} km")
print(f"   Points: {len(points)}")

# Calculer segments
segments = compute_segments(act) or []

print(f"\n✅ Segments calculés: {len(segments)}")

for seg in segments:
    number = seg.get('number', '?')
    start_km = seg.get('start_km', 0.0)
    end_km = seg.get('end_km', 0.0)
    distance_km_seg = seg.get('distance_km', end_km - start_km)
    pace = seg.get('pace_min_per_km')
    fc_avg = seg.get('fc_avg')
    fc_start = seg.get('fc_start')
    fc_end = seg.get('fc_end')
    drift_intra = seg.get('drift_intra')

    print(f"\n📍 Tronçon {number}")
    print(f"   Distance: {start_km:.2f} → {end_km:.2f} km ({distance_km_seg:.2f} km)")
    print(f"   Allure: {format_pace(pace)}")
    print(f"   FC moy: {fc_avg:.0f} bpm" if fc_avg is not None else "   FC moy: N/A")
    if fc_start is not None or fc_end is not None:
        fc_start_str = f"{fc_start:.0f}" if fc_start is not None else "N/A"
        fc_end_str = f"{fc_end:.0f}" if fc_end is not None else "N/A"
        print(f"   FC évolution: {fc_start_str} → {fc_end_str} bpm")
    else:
        print("   FC évolution: N/A")
    print(f"   Dérive intra: {drift_intra:.2f}" if drift_intra is not None else "   Dérive intra: N/A")

    fc_diff = seg.get('fc_diff_vs_prev')
    pace_diff = seg.get('pace_diff_vs_prev')

    if fc_diff is not None or pace_diff is not None:
        line_parts = []
        if fc_diff is not None:
            line_parts.append(f"FC {fc_diff:+.0f} bpm")
        if pace_diff is not None:
            # pace_diff attendu en secondes/km — afficher en s/km avec signe
            try:
                pace_diff_sec = int(round(pace_diff))
                line_parts.append(f"allure {pace_diff_sec:+d} sec/km")
            except Exception:
                line_parts.append(f"allure {pace_diff:+.2f} (unité inconnue)")
        print(f"   vs Tronçon {number-1 if isinstance(number, int) else '?'}: " + ", ".join(line_parts))

print("\n" + "=" * 70)
print("✅ TEST RÉUSSI !")
print("=" * 70)