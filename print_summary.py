fh.seek(0)
try:
    raw = fh.read()
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode('utf-8')
    data = json.loads(raw)
    print(f"✅ Chargé {len(data)} activités depuis activities.json")
except (UnicodeDecodeError, json.decoder.JSONDecodeError) as e:
    print("❌ Erreur JSON : activities.json est vide ou corrompu.", str(e))
    exit()