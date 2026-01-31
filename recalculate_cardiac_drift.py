#!/usr/bin/env python3
"""
Script pour recalculer toutes les dérives cardiaques avec la nouvelle méthode:
- Exclure les 5 premières minutes
- Division temporelle en 2 moitiés
- Dérive (%) = ((R₂ - R₁) / R₁) × 100
"""

import json
import sys
from pathlib import Path

# Ajouter le répertoire courant au path pour imports
sys.path.insert(0, str(Path(__file__).parent))

from app import enrich_single_activity, get_fcmax_from_fractionnes, save_activities_to_drive, calculate_stats_by_type, save_running_stats

def recalculate_all_cardiac_drift():
    """Recalcule toutes les dérives cardiaques dans activities.json"""

    # Charger activities.json
    activities_path = Path("/opt/app/Track2Train-staging/activities.json")

    if not activities_path.exists():
        print(f"❌ Fichier non trouvé: {activities_path}")
        return False

    with open(activities_path, 'r') as f:
        activities = json.load(f)

    print(f"📊 Chargé {len(activities)} activités")

    # Calculer FC max fractionnée
    fc_max_fractionnes = get_fcmax_from_fractionnes(activities)
    print(f"💓 FC max fractionnée: {fc_max_fractionnes}")

    # Recalculer chaque activité
    updated_count = 0
    error_count = 0

    for idx, activity in enumerate(activities):
        try:
            # Garder l'ancienne valeur pour comparaison
            old_drift = activity.get('deriv_cardio', '-')

            # Recalculer avec la nouvelle méthode
            activity = enrich_single_activity(activity, fc_max_fractionnes)

            new_drift = activity.get('deriv_cardio', '-')

            # Afficher les changements significatifs
            if old_drift != '-' and new_drift != '-' and isinstance(old_drift, (int, float)) and isinstance(new_drift, (int, float)):
                diff = abs(new_drift - old_drift)
                if diff > 1.0:  # Différence > 1%
                    date = activity.get('date', 'N/A')[:10]
                    print(f"  📌 [{date}] Dérive: {old_drift:.1f}% → {new_drift:.1f}% (Δ {new_drift - old_drift:+.1f}%)")

            activities[idx] = activity
            updated_count += 1

        except Exception as e:
            error_count += 1
            print(f"  ❌ Erreur activité {idx}: {e}")

    print(f"\n✅ Recalcul terminé: {updated_count} activités mises à jour, {error_count} erreurs")

    # Sauvegarder activities.json
    print("\n💾 Sauvegarde de activities.json...")
    save_activities_to_drive(activities)
    print("✅ activities.json sauvegardé")

    # Recalculer les statistiques par type
    print("\n📊 Recalcul des statistiques par type de run...")
    stats_by_type = calculate_stats_by_type(activities)
    save_running_stats(stats_by_type)
    print("✅ running_stats.json sauvegardé")

    # Afficher un résumé des nouvelles stats
    print("\n📈 Résumé des dérives cardiaques par type:")
    for run_type, stats in stats_by_type.items():
        if 'deriv_cardio' in stats and 'nombre_courses' in stats:
            drift_stats = stats['deriv_cardio']
            print(f"  {run_type}:")
            print(f"    - Nombre: {stats['nombre_courses']} runs")
            print(f"    - Moyenne: {drift_stats.get('moyenne', '-'):.1f}%")
            print(f"    - Min: {drift_stats.get('min', '-'):.1f}%")
            print(f"    - Max: {drift_stats.get('max', '-'):.1f}%")

    return True

if __name__ == "__main__":
    print("🔄 RECALCUL DES DÉRIVES CARDIAQUES")
    print("=" * 60)
    print("Nouvelle méthode:")
    print("  1. Exclure les 5 premières minutes")
    print("  2. Division temporelle en 2 moitiés")
    print("  3. R = FC / V pour chaque moitié")
    print("  4. Dérive (%) = ((R₂ - R₁) / R₁) × 100")
    print("=" * 60)
    print()

    success = recalculate_all_cardiac_drift()

    if success:
        print("\n🎉 Recalcul terminé avec succès!")
        print("\nProchaines étapes:")
        print("  1. Vérifier les nouvelles valeurs dans activities.json")
        print("  2. Consulter running_stats.json pour les nouvelles moyennes")
        print("  3. Mettre à jour les objectifs dans profile.json si nécessaire")
    else:
        print("\n❌ Erreur lors du recalcul")
        sys.exit(1)
