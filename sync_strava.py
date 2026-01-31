from typing import Dict, Any
import requests

def get_activity_details(headers: dict, activity_id: int) -> Dict[str, Any]:
    """Récupère les détails d'une activité Strava par ID."""
    url = f"https://www.strava.com/api/v3/activities/{activity_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        a = resp.json()
        return {
            "activity_id": int(a.get("id")),
            "name": a.get("name"),
            "type": a.get("type") or a.get("sport_type"),
            "distance": a.get("distance"),
            "moving_time": a.get("moving_time"),
            "elapsed_time": a.get("elapsed_time"),
            "start_date": a.get("start_date"),
            "start_date_local": a.get("start_date_local"),
            "total_elevation_gain": a.get("total_elevation_gain"),
            "timezone": a.get("timezone"),
        }
    except requests.HTTPError as e:
        print(f"⚠️ Erreur HTTP pour l'activité {activity_id}: {e}")
    except Exception as e:
        print(f"⚠️ Erreur récupération activité {activity_id}: {e}")
    return {}


def sync_deletions() -> Dict[str, Any]:
    """
    Synchronise les suppressions depuis Strava et ajoute les nouvelles activités.
    Retourne un rapport : {"deleted": [...], "added": [...], "kept": int, "strava_count": int}
    """
    print("\n🔍 Synchronisation avec Strava (suppressions + nouvelles activités)...")

    # 1) Charger les tokens
    headers = load_tokens()

    # 2) Récupérer les IDs depuis Strava
    strava_ids = set(get_strava_activities(headers))
    print(f"📊 Strava: {len(strava_ids)} activités")

    # 3) Charger les activités locales
    local_activities = load_local_activities()
    local_ids = set(act.get("activity_id") for act in local_activities)
    print(f"📊 Local: {len(local_ids)} activités")

    report = {"deleted": [], "added": [], "kept": len(local_activities), "strava_count": len(strava_ids)}

    # 4) Détecter les suppressions
    deleted_ids = local_ids - strava_ids
    if deleted_ids:
        print(f"🗑️ {len(deleted_ids)} activité(s) supprimée(s) sur Strava:")
        for aid in sorted(deleted_ids):
            print(f"   - {aid}")
        # Filtrer les activités locales
        filtered = [act for act in local_activities if act.get("activity_id") not in deleted_ids]
        report["deleted"] = list(sorted(deleted_ids))
    else:
        print("✅ Aucune suppression détectée.")
        filtered = local_activities.copy()

    # 5) Détecter les nouvelles activités sur Strava
    new_ids = strava_ids - set(act.get("activity_id") for act in filtered)
    if new_ids:
        print(f"➕ {len(new_ids)} nouvelle(s) activité(s) trouvée(s) sur Strava:")
        added_acts = []
        for aid in sorted(new_ids):
            print(f"   - Récupération {aid}...")
            details = get_activity_details(headers, aid)
            if details:
                added_acts.append(details)
            time.sleep(0.5)  # Rate limiting entre requests individuelles
        if added_acts:
            filtered.extend(added_acts)
            report["added"] = [act["activity_id"] for act in added_acts]
            print(f"💾 {len(added_acts)} activité(s) ajoutée(s) à activities.json")
    else:
        print("✅ Aucune nouvelle activité détectée.")

    # 6) Sauvegarder le fichier local si changement
    if report["deleted"] or report["added"]:
        save_local_activities(filtered)
        print(f"💾 activities.json mis à jour: {len(filtered)} activités au total")
    else:
        print("📁 activities.json inchangé.")

    report["kept"] = len(filtered)
    return report


if __name__ == "__main__":
    try:
        report = sync_deletions()
        print("\n" + "="*60)
        print("📋 RAPPORT DE SYNCHRONISATION")
        print("="*60)
        print(f"Activités sur Strava : {report['strava_count']}")
        print(f"Activités conservées : {report['kept']}")
        print(f"Activités ajoutées : {len(report.get('added', []))}")
        print(f"Activités supprimées : {len(report.get('deleted', []))}")
        if report.get('deleted'):
            print(f"IDs supprimés : {report['deleted']}")
        if report.get('added'):
            print(f"IDs ajoutés : {report['added']}")
        print("="*60)
    except Exception as e:
        print(f"❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        exit(1)