from calculate_running_stats import calculate_stats_by_type, save_running_stats


def update_running_stats_after_webhook():
    """
    Met à jour les statistiques de running après un nouveau run
    À appeler dans la route /webhook après avoir traité le nouveau run
    """
    try:
        # Charger les activités
        activities = load_activities_from_drive()

        # Calculer les stats par type (15 dernières courses)
        stats_by_type = calculate_stats_by_type(activities, n_last=15)

        # Sauvegarder dans running_stats.json
        save_running_stats(stats_by_type, 'running_stats.json')

        print("✅ Running stats mises à jour après webhook")
        return stats_by_type

    except Exception as e:
        print(f"❌ Erreur mise à jour running stats: {e}")
        return None


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    # ... traitement du webhook ...

    # Sauvegarder activities
    save_activities_to_drive(activities)

    # 🆕 NOUVEAU : Mettre à jour les stats par type de run
    update_running_stats_after_webhook()

    return jsonify({"status": "ok"})


@app.route('/')
def index():
    # ... code existant ...

    # 🆕 NOUVEAU : Charger les running stats
    running_stats = {}
    if os.path.exists('running_stats.json'):
        with open('running_stats.json', 'r') as f:
            running_stats = json.load(f)

    return render_template(
        'index.html',
        activities_for_carousel=activities_for_carousel,
        dashboard=dashboard_data,
        running_stats=running_stats,  # 🆕 Passer au template
        # ... autres variables ...
    )