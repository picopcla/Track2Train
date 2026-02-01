import requests
import datetime

def test_weather():
    lat = 48.8566
    lng = 2.3522
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": "weather_code,temperature_2m_max",
        "timezone": "auto",
        "start_date": today,
        "end_date": today
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print(f"✅ Open-Meteo OK: {data}")
    except Exception as e:
        print(f"❌ Erreur Open-Meteo: {e}")

if __name__ == "__main__":
    test_weather()
