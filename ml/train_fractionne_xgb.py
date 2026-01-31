for a in activities:
    pts = a.get("points") or []
    if len(pts) < 10:
        continue
    # Focus: <= 11 km (on exclut les long runs)
    dist_km = pts[-1].get("distance", 0) / 1000.0
    if dist_km > 11:
        continue
    # Label requis: is_fractionne_label (posé via ton Excel)
    if "is_fractionne_label" not in a:
        continue

    raw_label = a["is_fractionne_label"]
    # Normalize label robustly (Excel imports can produce "0"/"1" strings, booleans, etc.)
    if isinstance(raw_label, bool):
        label = raw_label
    else:
        try:
            label = bool(int(raw_label))
        except Exception:
            s = str(raw_label).strip().lower()
            label = s in ("1", "true", "yes", "y", "t")

    X.append(features(a))
    y.append(int(label))

model = XGBClassifier(
    n_estimators=200,
    max_depth=3,
    learning_rate=0.1,
    subsample=0.9,
    colsample_bytree=0.9,
    reg_lambda=1.0,
    objective="binary:logistic",
    eval_metric="logloss",
    use_label_encoder=False,
    verbosity=0,
    random_state=42,
)