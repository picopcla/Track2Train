# get_streams.py — ingestion uniquement (cadence brute)
import os, sys, json, time
from bisect import bisect_left

import requests
import numpy as np
from dotenv import load_dotenv

# Import pour mise à jour automatique des stats
from calculate_running_stats import calculate_stats_by_type, save_running_stats

# WMO Weather Codes mapping
def get_weather_emoji(code):
    if code is None: return "❓"
    if code == 0: return "☀️"
    if code in [1, 2, 3]: return "⛅"
    if code in [45, 48]: return "🌫️"
    if code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]: return "🌧️"
    if code in [71, 73, 75, 77, 85, 86]: return "❄️"
    if code in [95, 96, 99]: return "⛈️"
    return "csp"

def fetch_open_meteo(lat, lng, date_str):
    """
    Récupère la météo histo/forecast pour une date donnée.
    Retourne (temp_max, weather_code)
    """
    try:
        # Format date: YYYY-MM-DD
        day_str = date_str[:10]
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lng,
            "start_date": day_str,
            "end_date": day_str,
            "daily": "weather_code,temperature_2m_max",
            "timezone": "auto"
        }
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            d = r.json()
            if "daily" in d:
                wc = d["daily"]["weather_code"][0] if d["daily"].get("weather_code") else None
                tm = d["daily"]["temperature_2m_max"][0] if d["daily"].get("temperature_2m_max") else None
                return tm, wc
    except Exception as e:
        print(f"⚠️ Météo API erreur: {e}")
    return None, None


# ----------------------------
# ENV bootstrap (Strava tokens)
# ----------------------------
# Charge .env pour les tokens Strava si besoin
load_dotenv()


# ----------------------------
# Fichier local (pas de Drive)
# ----------------------------
ACTIVITIES_FILE = "activities.json"

def load_activities_local():
    """Charge activities.json depuis le disque local."""
    if not os.path.exists(ACTIVITIES_FILE):
        print(f"ℹ️ {ACTIVITIES_FILE} inexistant, création d'un fichier vide")
        return []

    try:
        with open(ACTIVITIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            print(f"⚠️ {ACTIVITIES_FILE} n'est pas une liste, réinitialisation")
            return []
        return data
    except Exception as e:
        print(f"⚠️ Erreur lecture {ACTIVITIES_FILE}: {e}, réinitialisation")
        return []

def save_activities_local(activities):
    """Sauvegarde activities.json sur le disque local."""
    try:
        with open(ACTIVITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(activities, f, ensure_ascii=False, indent=2)
        print(f"💾 {ACTIVITIES_FILE} sauvegardé: {len(activities)} activités")
    except Exception as e:
        print(f"❌ Erreur écriture {ACTIVITIES_FILE}: {e}")


# ----------------------------
# Strava token (refresh si besoin)
# ----------------------------
with open("strava_tokens.json") as f:
    tokens = json.load(f)

access_token = tokens["access_token"]
refresh_token = tokens["refresh_token"]
expires_at = tokens["expires_at"]

time_remaining = expires_at - int(time.time())
if time_remaining < 300:
    print(f"🔄 Token expirant dans {time_remaining}s, on le renouvelle...")
    resp = requests.post(
        "https://www.strava.com/api/v3/oauth/token",
        data={
            "client_id": os.getenv("STRAVA_CLIENT_ID", "162245"),
            "client_secret": os.getenv("STRAVA_CLIENT_SECRET", "0552c0e87d83493d7f6667d0570de1e8ac9e9a68"),
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        },
        timeout=30
    )
    resp.raise_for_status()
    new_tokens = resp.json()
    tokens["access_token"] = new_tokens["access_token"]
    tokens["refresh_token"] = new_tokens["refresh_token"]
    tokens["expires_at"] = new_tokens["expires_at"]
    with open("strava_tokens.json", "w") as f:
        json.dump(tokens, f, indent=2)
    access_token = tokens["access_token"]
    print("✅ Token Strava rafraîchi.")
else:
    print(f"✅ Token encore valide pour {time_remaining}s.")

headers = {"Authorization": f"Bearer {access_token}"}


# ----------------------------
# Helpers: mapping série -> points existants
# ----------------------------
def _map_series_to_points_by_time(points, time_stream, series, field_name: str, tol_sec=5):
    """
    Remplit points[i][field_name] avec la valeur la plus proche temporellement (± tol_sec).
    N'écrase PAS une valeur déjà présente.
    """
    times = time_stream or []
    vals = series or []
    if not times or not vals or not points:
        return 0

    filled = 0
    for p in points:
        if p.get(field_name) is not None:
            continue
        t = p.get("time")
        if t is None:
            continue
        idx = bisect_left(times, t)
        cand = [j for j in (idx-1, idx, idx+1) if 0 <= j < len(times)]
        best = None; best_dt = None
        for j in cand:
            v = vals[j]
            if not isinstance(v, (int, float)):
                continue
            dt = abs(times[j] - t)
            if best is None or dt < best_dt:
                best, best_dt = v, dt
        if best is not None and (best_dt is None or best_dt <= tol_sec):
            p[field_name] = best
            filled += 1
    return filled


def _calculate_deriv_cardio(points):
    """
    Calcule deriv_cardio depuis les points (ratio FC/allure).
    Retourne un float arrondi à 3 décimales, ou None si pas assez de données.
    """
    if not points or len(points) < 10:
        return None

    # Extraire HR et velocity (gérer None)
    hrs = [p["hr"] for p in points if p.get("hr") is not None and p.get("hr") > 0]
    vels = [p["vel"] for p in points if p.get("vel") is not None and p.get("vel") > 0]

    if len(hrs) < 10 or len(vels) < 10:
        return None

    # Calculer allure (min/km) depuis velocity (m/s)
    allures = [16.6667 / v if v > 0 else 0 for v in vels]

    # Prendre la longueur minimum
    min_len = min(len(hrs), len(allures))
    hrs = hrs[:min_len]
    allures = allures[:min_len]

    # Calculer ratios FC/allure
    ratios = [hr / allure if allure > 0 else 0 for hr, allure in zip(hrs, allures)]
    ratios = [r for r in ratios if r > 0]

    if len(ratios) < 10:
        return None

    # Calculer deriv_cardio
    split = max(1, len(ratios) // 3)
    ratio_first = np.mean(ratios[:split])
    ratio_last = np.mean(ratios[-split:])

    if ratio_first > 0:
        deriv_cardio = ratio_last / ratio_first
        return round(deriv_cardio, 3)

    return None


# ----------------------------
# Charger activities.json depuis le fichier local
# ----------------------------
activities = load_activities_local()
print(f"✅ activities.json chargé ({len(activities)} activités).")


# ----------------------------
# Récupérer/mettre à jour une activité (cadence BRUTE)
# ----------------------------
def process_activity(activity_id: int):
    url_activity = f"https://www.strava.com/api/v3/activities/{activity_id}"
    ra = requests.get(url_activity, headers=headers, timeout=30)
    if ra.status_code != 200:
        print(f"❌ Erreur {ra.status_code} sur l'activité {activity_id}")
        return
    activity_data = ra.json()
    start_date = activity_data.get("start_date_local")

    # Streams
    url_streams = f"https://www.strava.com/api/v3/activities/{activity_id}/streams"
    params = {
        "keys": "time,distance,heartrate,cadence,velocity_smooth,altitude,temperature,moving,latlng",
        "key_by_type": "true"
    }
    rs = requests.get(url_streams, params=params, headers=headers, timeout=60)
    if rs.status_code != 200:
        print(f"❌ Erreur HTTP {rs.status_code} pour streams {activity_id}")
        return
    streams = rs.json()

    time_data   = (streams.get("time") or {}).get("data", []) or []
    distance    = (streams.get("distance") or {}).get("data", []) or []
    heartrate   = (streams.get("heartrate") or {}).get("data", []) or []
    velocity    = (streams.get("velocity_smooth") or {}).get("data", []) or []
    altitude    = (streams.get("altitude") or {}).get("data", []) or []
    latlng      = (streams.get("latlng") or {}).get("data", []) or []
    cadence_raw = (streams.get("cadence") or {}).get("data", []) or []
    temp_data   = (streams.get("temperature") or {}).get("data", []) or []

    # Calculer température moyenne depuis Strava (si dispo)
    avg_temp_strava = None
    if temp_data:
        valid_temps = [t for t in temp_data if isinstance(t, (int, float))]
        if valid_temps:
            avg_temp_strava = round(sum(valid_temps) / len(valid_temps), 1)

    if not time_data or not distance:
        print(f"⚠️ Pas de données time/distance pour {activity_id}, on ignore.")
        return

    # Si déjà présente: compléter uniquement 'cad_raw'
    act = next((a for a in activities if a.get("activity_id") == activity_id), None)
    if act is not None:
        print(f"👣 Activité {activity_id} déjà présente → MAJ cad_raw uniquement")
        pts = act.get("points") or []
        filled = _map_series_to_points_by_time(pts, time_data, cadence_raw, "cad_raw", tol_sec=5)
        print(f"   → cad_raw remplie sur {filled} points")
        act["points"] = pts
        
        # En profiter pour MAJ la météo si manquante
        if act.get("weather_emoji") is None or act.get("temperature") is None:
            # Récupérer lat/lng moyen
            alat = avg_lat if 'avg_lat' in locals() and avg_lat else None 
            # (Note: avg_lat n'est calculé que plus bas, on utilise celui du premier point si dispo)
            if not alat and pts and pts[0].get('lat'): alat = pts[0].get('lat')
            
            alng = avg_lng if 'avg_lng' in locals() and avg_lng else None
            if not alng and pts and pts[0].get('lng'): alng = pts[0].get('lng')

            if alat and alng:
                 w_temp, w_code = fetch_open_meteo(alat, alng, start_date)
                 act["weather_emoji"] = get_weather_emoji(w_code)
                 # Priorité température Strava, sinon météo
                 if avg_temp_strava is not None:
                     act["temperature"] = avg_temp_strava
                 elif w_temp is not None:
                     act["temperature"] = w_temp
                 print(f"   ☀️ Météo MAJ: {act.get('weather_emoji')} {act.get('temperature')}°C")

        return

    # Nouvelle activité → créer des points “fenêtres 10 échantillons”
    points = []
    window = 10
    n = len(time_data)
    for i in range(0, n, window):
        slice_range = range(i, min(i + window, n))
        point_time = time_data[slice_range[-1]]
        last_dist = distance[slice_range[-1]] if slice_range[-1] < len(distance) else None

        def _avg(series):
            vals = [series[j] for j in slice_range if j < len(series) and isinstance(series[j], (int, float))]
            return (sum(vals) / len(vals)) if vals else None

        avg_hr  = _avg(heartrate)
        avg_vel = _avg(velocity)
        avg_alt = _avg(altitude)

        lat_vals = [latlng[j][0] for j in slice_range if j < len(latlng) and latlng[j]]
        lng_vals = [latlng[j][1] for j in slice_range if j < len(latlng) and latlng[j]]
        avg_lat = (sum(lat_vals) / len(lat_vals)) if lat_vals else None
        avg_lng = (sum(lng_vals) / len(lng_vals)) if lng_vals else None

        cad_vals = [cadence_raw[j] for j in slice_range if j < len(cadence_raw) and isinstance(cadence_raw[j], (int, float))]
        cad_mean_raw = (sum(cad_vals) / len(cad_vals)) if cad_vals else None

        points.append({
            "time": point_time,
            "distance": last_dist,
            "hr": avg_hr,
            "vel": avg_vel,
            "alt": avg_alt,
            "lat": avg_lat,
            "lng": avg_lng,
            "cad_raw": cad_mean_raw,   # <-- BRUT uniquement, normalisé plus tard dans app.py
        })

    # Calculer deriv_cardio
    deriv_cardio = _calculate_deriv_cardio(points)

    new_activity = {
        "activity_id": activity_id,
        "date": start_date,
        "points": points
    }

    # Ajouter Météo
    final_temp = avg_temp_strava
    final_emoji = "❓"
    
    if avg_lat and avg_lng:
        w_temp, w_code = fetch_open_meteo(avg_lat, avg_lng, start_date)
        final_emoji = get_weather_emoji(w_code)
        if final_temp is None:
            final_temp = w_temp

    new_activity["temperature"] = final_temp
    new_activity["weather_emoji"] = final_emoji

    if deriv_cardio is not None:
        new_activity["deriv_cardio"] = deriv_cardio
        print(f"🚀 Activité {activity_id} ajoutée avec {len(points)} points, deriv_cardio={deriv_cardio}")
    else:
        print(f"🚀 Activité {activity_id} ajoutée avec {len(points)} points (pas de deriv_cardio)")

    activities.append(new_activity)


# ----------------------------
# Main
# ----------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_streams.py <ACTIVITY_ID>")
        sys.exit(1)

    activity_id_arg = int(sys.argv[1])

    # 1) Traiter l'ID demandé
    process_activity(activity_id_arg)

    # 2) Optionnel: rafraîchir les dernières activités (sans supprimer l'ancien)
    try:
        url = "https://www.strava.com/api/v3/athlete/activities"
        params = {"per_page": 30, "page": 1}
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        latest_activities = resp.json()
        if isinstance(latest_activities, list):
            for act in latest_activities:
                process_activity(int(act["id"]))
        else:
            print("⚠️ Réponse inattendue pour athlete/activities:", latest_activities)
    except Exception as e:
        print("ℹ️ Impossible de parcourir les dernières activités:", e)

    # 3) Sauvegarder local uniquement
    save_activities_local(activities)

    # 4) Mettre à jour les running stats automatiquement
    try:
        print("📊 Mise à jour des running stats...")
        stats = calculate_stats_by_type(activities, n_last=15)
        save_running_stats(stats, 'running_stats.json')
        print("✅ Running stats mis à jour automatiquement après webhook")
    except Exception as e:
        print(f"⚠️ Erreur lors de la mise à jour des stats: {e}")
