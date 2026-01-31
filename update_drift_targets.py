#!/usr/bin/env python3
"""
Script pour recalculer les objectifs de dérive cardiaque (drift_target)
dans profile.json basé sur les nouvelles valeurs en pourcentage.

Méthode: P40 (percentile 40) = objectif ambitieux mais atteignable
"""

import json
import sys
from pathlib import Path
import numpy as np

def update_drift_targets():
    """Met à jour les drift_target dans profile.json"""

    # Charger running_stats.json
    stats_path = Path("/opt/app/Track2Train-staging/running_stats.json")
    with open(stats_path, 'r') as f:
        running_stats = json.load(f)

    # Charger activities.json pour calculer les percentiles
    activities_path = Path("/opt/app/Track2Train-staging/activities.json")
    with open(activities_path, 'r') as f:
        activities = json.load(f)

    # Charger profile.json
    profile_path = Path("/opt/app/Track2Train-staging/profile.json")
    with open(profile_path, 'r') as f:
        profile = json.load(f)

    print("📊 RECALCUL DES OBJECTIFS DE DÉRIVE CARDIAQUE")
    print("=" * 60)
    print("Méthode: P40 (percentile 40) = 40% de vos meilleures performances")
    print("Plus BAS = meilleur (moins de dérive = meilleure stabilité)")
    print("=" * 60)
    print()

    # Types de run à traiter
    run_types = ['tempo_recup', 'tempo_rapide', 'endurance', 'long_run']

    updated_targets = {}

    for run_type in run_types:
        # Récupérer toutes les dérives pour ce type
        drifts = []
        for act in activities:
            # Utiliser session_category ou type_sortie
            act_type = act.get('session_category') or act.get('type_sortie', '')

            if act_type == run_type:
                drift = act.get('deriv_cardio')
                if isinstance(drift, (int, float)) and drift != '-':
                    drifts.append(drift)

        if len(drifts) >= 5:  # Au moins 5 runs pour calculer un objectif
            drifts_sorted = sorted(drifts)

            # P40 = 40ème percentile (60% sont au-dessus, 40% en-dessous)
            # Pour la dérive: plus bas = meilleur, donc P40 est ambitieux
            p40 = np.percentile(drifts_sorted, 40)

            # Plancher physiologique: minimum 3.0% pour éviter objectifs irréalistes
            # (dérive < 3% est physiologiquement rare sauf conditions exceptionnelles)
            drift_target = max(3.0, p40)

            # Récupérer stats actuelles
            stats = running_stats['stats_by_type'].get(run_type, {})
            drift_stats = stats.get('deriv_cardio', {})

            print(f"📌 {run_type}:")
            print(f"   Nombre de runs: {len(drifts)}")
            print(f"   Moyenne actuelle: {drift_stats.get('moyenne', 'N/A'):.1f}%")
            print(f"   Min: {drift_stats.get('min', 'N/A'):.1f}%")
            print(f"   Max: {drift_stats.get('max', 'N/A'):.1f}%")
            print(f"   P40 calculé: {p40:.1f}%")
            print(f"   → Objectif (P40 avec plancher 3%): {drift_target:.1f}%")

            # Ancien objectif
            old_target = profile.get('personalized_targets', {}).get(run_type, {}).get('drift_target', 'N/A')
            if old_target != 'N/A':
                print(f"   (Ancien objectif: {old_target})")
            print()

            updated_targets[run_type] = round(drift_target, 1)
        else:
            print(f"⚠️  {run_type}: Pas assez de données ({len(drifts)} runs), objectif non modifié")
            print()

    # Mettre à jour profile.json
    if not profile.get('personalized_targets'):
        profile['personalized_targets'] = {}

    for run_type, new_drift_target in updated_targets.items():
        if run_type not in profile['personalized_targets']:
            profile['personalized_targets'][run_type] = {}

        profile['personalized_targets'][run_type]['drift_target'] = new_drift_target

    # Sauvegarder profile.json
    with open(profile_path, 'w') as f:
        json.dump(profile, f, indent=2)

    print("=" * 60)
    print(f"✅ Objectifs mis à jour dans profile.json")
    print()
    print("📋 RÉSUMÉ DES NOUVEAUX OBJECTIFS:")
    print("-" * 60)
    for run_type in run_types:
        if run_type in updated_targets:
            print(f"  {run_type}: {updated_targets[run_type]:.1f}%")
    print("=" * 60)

    return True

if __name__ == "__main__":
    success = update_drift_targets()

    if success:
        print("\n🎉 Objectifs de dérive cardiaque mis à jour!")
        print("\nInterprétation:")
        print("  - Dérive < objectif = Performance excellente ✅")
        print("  - Dérive ≈ objectif = Performance visée 🎯")
        print("  - Dérive > objectif = Marge de progression 📈")
        print("\nNB: Plus la dérive est BASSE, meilleure est la stabilité cardio-mécanique")
    else:
        print("\n❌ Erreur lors de la mise à jour")
        sys.exit(1)
