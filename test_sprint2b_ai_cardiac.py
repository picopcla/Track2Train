from datetime import date


    if fc_max_fractionnes == 0:
        birth_date = profile.get('birth_date', '1973-01-01')
        try:
            birth_year = int(birth_date.split('-')[0])
            age = date.today().year - birth_year
        except Exception:
            age = 52  # fallback if parsing fails
        fc_max_fractionnes = 220 - age
        print(f"   FC max théorique: {fc_max_fractionnes} bpm")
    else:
        print(f"   FC max observée: {fc_max_fractionnes} bpm")


# Vérifier mentions FC
if any(x in comment_lower for x in ['fréquence', 'cardiaque', 'fc', 'bpm', 'cœur', 'coeur']):
    checks['mentions_fc'] = True
    print("   ✅ Mentionne la fréquence cardiaque")
else:
    print("   ⚠️  Ne mentionne pas la FC")