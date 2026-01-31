# --- Remplacement du bloc d'initialisation des activités/session ---
activities = load_activities_from_drive()
profile = load_profile()
if not activities:
    print("❗ Aucune activité trouvée. Fin du test.")
    sys.exit(1)
act = activities[0]

# --- Remplacement de l'affichage du commentaire IA (gestion None/empty) ---
ai_comment = generate_segment_analysis(act, feedback, profile, segments, patterns, segment_comparisons) or ""
print(f"✅ Commentaire IA généré ({len(ai_comment)} caractères)")
print(f"\n💬 Commentaire:")
print("-" * 80)
print(ai_comment if ai_comment else "(Aucun commentaire généré)")
print("-" * 80)

# --- Remplacement de l'affichage de la structure d'une comparaison (gardes si vide) ---
print(f"✅ {len(segment_comparisons)} comparaisons à sauvegarder")
print(f"\nStructure d'une comparaison:")
if segment_comparisons:
    print(json.dumps(segment_comparisons[0], indent=2))
else:
    print("(Aucune comparaison disponible)")