import math
from datetime import datetime, timedelta

def parse_time_str(time_str):
    """
    Convertit "HH:MM:SS" ou "MM:SS" en secondes.
    """
    if not time_str or time_str == "-":
        return 0
    try:
        parts = list(map(int, time_str.split(":")))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
    except:
        pass
    return 0

def format_time_str(total_seconds):
    """
    Convertit secondes en "H:MM:SS".
    """
    if not total_seconds:
        return "-"
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def get_best_performance(activities, target_dist_km, tolerance=0.5, window_days=90):
    """
    Trouve la meilleure performance sur une distance donnée dans la fenêtre de temps.
    Retourne: dict {time_sec, pace_sec, date, activities_id} ou None
    """
    best_perf = None
    cutoff_date = datetime.now() - timedelta(days=window_days)

    for act in activities:
        # Check date
        try:
            d_str = act.get("date", "")[:10]
            act_date = datetime.strptime(d_str, "%Y-%m-%d")
            if act_date < cutoff_date:
                continue
        except:
            continue

        # Check distance
        dist = act.get("distance_km", 0)
        # On cherche une activité qui est "proche" de la distance cible
        # Pour être validé comme "record 10k", il faut avoir couru au moins 10k (ou très proche)
        # Mais pas 20k. Donc : target - tolerance <= dist <= target + margin
        # Ex pour 10k: 9.8 <= dist <= 12.0 (on prendra le passage au 10k si possible, sinon l'allure moyenne)
        
        # Simplification V1: On prend l'allure moyenne de la sortie si la distance est suffisante
        if dist < target_dist_km * 0.95: # Trop court
            continue
        
        if dist > target_dist_km * 1.5: # Trop long (ex: un semi ne compte pas comme un record 10k direct avec cette logique simple)
            continue
            
        # Calcul temps théorique sur la distance cible à l'allure moyenne
        pace_min_km = act.get("pace_min_per_km")
        if not pace_min_km:
             # Fallback sur allure string
             p_sec = parse_time_str(act.get("allure", ""))
             if p_sec:
                 pace_min_km = p_sec / 60.0
        
        if not pace_min_km or pace_min_km == 0:
            continue

        projected_time = pace_min_km * target_dist_km * 60 # secondes
        
        if best_perf is None or projected_time < best_perf["time_sec"]:
            best_perf = {
                "time_sec": projected_time,
                "pace_sec": pace_min_km * 60,
                "date": d_str,
                "distance_run": dist,
                "act_id": act.get("id")
            }
            
    return best_perf

def predict_riegel(ref_time_sec, ref_dist_km, target_dist_km, fatigue_factor=1.06):
    """
    Formule de Riegel: T2 = T1 * (D2 / D1) ^ fatigue_factor
    """
    if ref_dist_km == 0: return 0
    t2 = ref_time_sec * math.pow((target_dist_km / ref_dist_km), fatigue_factor)
    return t2

def generate_predictions(activities):
    """
    Génère les prédictions pour 5k, 10k, Semi, Marathon basées sur la meilleure perf récente.
    """
    runs_of_interest = {
        "5k": 5.0,
        "10k": 10.0,
        "Semi": 21.1,
        "Marathon": 42.195
    }
    
    # 1. Trouver les meilleures perfs réelles récentes
    bests = {}
    for name, dist in runs_of_interest.items():
        perf = get_best_performance(activities, dist)
        if perf:
            bests[name] = perf
            
    # 2. Choisir la meilleure "référence" pour la prédiction
    # On préfère une référence longue (10k ou Semi) pour prédire Marathon
    # Hiérarchie de confiance pour référence: Semi > 10k > 5k
    ref_perf = None
    ref_name = None
    ref_dist = 0
    
    if "Semi" in bests:
        ref_perf = bests["Semi"]
        ref_name = "Semi"
        ref_dist = 21.1
    elif "10k" in bests:
        ref_perf = bests["10k"]
        ref_name = "10k"
        ref_dist = 10.0
    elif "5k" in bests:
        ref_perf = bests["5k"]
        ref_name = "5k"
        ref_dist = 5.0
        
    predictions = {}
    
    if ref_perf:
        for name, dist in runs_of_interest.items():
            pred_time = predict_riegel(ref_perf["time_sec"], ref_dist, dist)
            pace_sec = pred_time / dist
            
            predictions[name] = {
                "distance": dist,
                "time_predicted_sec": pred_time,
                "time_display": format_time_str(pred_time),
                "pace_sec": pace_sec,
                "pace_display": f"{int(pace_sec // 60)}:{int(pace_sec % 60):02d}",
                "based_on": f"Record {ref_name} du {ref_perf['date']}"
            }
            
            # Si on a un record réel MEILLEUR que la prédiction (cas où Riegel sous-estime), on garde le réel
            if name in bests and bests[name]["time_sec"] < pred_time:
                 real = bests[name]
                 predictions[name].update({
                     "time_predicted_sec": real["time_sec"],
                     "time_display": format_time_str(real["time_sec"]),
                     "pace_display": f"{int(real['pace_sec'] // 60)}:{int(real['pace_sec'] % 60):02d}",
                     "based_on": f"Réalisé le {real['date']}",
                     "is_real": True
                 })
    
    return {
        "reference_run": ref_name,
        "predictions": predictions,
        "bests": bests # Les records réels trouvés
    }
