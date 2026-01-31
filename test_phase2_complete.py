activities = load_activities_from_drive()
if not activities:
    print("❌ Aucune activité trouvée. Fin du test.")
    sys.exit(1)
act = activities[0]  # Premier run

# Générer analyse
ai_comment = generate_segment_analysis(act, feedback, profile, segments, patterns) or ""