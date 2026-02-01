from get_streams import activities, save_activities_local, fetch_open_meteo, get_weather_emoji
import time

def refresh_all_weather():
    print(f"🌦️ Vérification météo pour {len(activities)} activités...")
    count = 0
    
    for act in activities:
        # Si météo manquante ou emoji par défaut
        if act.get("weather_emoji") is None or act.get("weather_emoji") == "❓" or act.get("temperature") is None:
            points = act.get("points", [])
            if not points:
                continue
                
            # Trouver lat/lng
            lat = next((p["lat"] for p in points if p.get("lat")), None)
            lng = next((p["lng"] for p in points if p.get("lng")), None)
            
            if lat and lng:
                date_str = act.get("date")
                if not date_str:
                    continue
                    
                print(f"   update {act['activity_id']} ({date_str})...", end="", flush=True)
                
                # Petit délai pour ne pas spammer l'API (rate limit Open-Meteo généreux mais restons polis)
                time.sleep(0.1)
                
                w_temp, w_code = fetch_open_meteo(lat, lng, date_str)
                
                if w_code is not None:
                    act["weather_emoji"] = get_weather_emoji(w_code)
                    if act.get("temperature") is None and w_temp is not None:
                        act["temperature"] = w_temp
                    count += 1
                    print(" ✅")
                else:
                    print(" ❌")

    if count > 0:
        save_activities_local(activities)
        print(f"✅ Météo mise à jour pour {count} activités.")
    else:
        print("✅ Toutes les activités ont déjà la météo.")

if __name__ == "__main__":
    refresh_all_weather()
