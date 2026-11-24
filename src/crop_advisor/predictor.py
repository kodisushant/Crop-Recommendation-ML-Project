"""Prediction, confidence, out-of-range detection, stability check and explanations.
Works independently of train_model.py: it only loads the saved .pkl files."""
import json, joblib, numpy as np, pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]
HARD_LIMITS = {"N": (0, 300), "P": (0, 300), "K": (0, 400), "temperature": (-5, 55),
               "humidity": (0, 100), "ph": (0, 14), "rainfall": (0, 4000)}
RNG = np.random.default_rng(42)

model = joblib.load(BASE / "models/best_model.pkl")
ood = joblib.load(BASE / "models/ood_detector.pkl")
METRICS = json.load(open(BASE / "models/metrics.json"))
CLASSES = list(model.classes_)
DF = pd.read_csv(BASE / "data/Crop_recommendation.csv")
STD = DF[FEATURES].std().values
_TRAIN = ood["train_X"]


def validate(values: dict) -> dict:
    out = {}
    for f in FEATURES:
        if f not in values or values[f] is None:
            raise ValueError(f"Missing value for '{f}'")
        v = float(values[f])
        if not np.isfinite(v):
            raise ValueError(f"'{f}' must be a finite number")
        lo, hi = HARD_LIMITS[f]
        if not lo <= v <= hi:
            raise ValueError(f"'{f}' must be between {lo} and {hi} (got {v})")
        out[f] = v
    return out


def _proba(X):
    return model.predict_proba(pd.DataFrame(X, columns=FEATURES))


def probabilities(values: dict) -> np.ndarray:
    return _proba([[values[f] for f in FEATURES]])[0]


def top_k(p, k=3):
    idx = np.argsort(p)[::-1][:k]
    return [{"crop": CLASSES[i], "probability": round(float(p[i]), 4)} for i in idx]


def check_range(values: dict) -> dict:
    """Per-feature range check + combination check (Mahalanobis vs 99th percentile of training rows)."""
    feats = [{"feature": f, "value": values[f], "train_min": ood["min"][f], "train_max": ood["max"][f]}
             for f in FEATURES if not ood["min"][f] <= values[f] <= ood["max"][f]]
    x = np.array([values[f] for f in FEATURES]) - ood["mean"]
    dist = float(np.sqrt(x @ ood["inv_cov"] @ x))
    combo = dist > ood["threshold_99"]
    return {"unusual_features": feats, "combination_unusual": combo,
            "distance": round(dist, 3), "threshold": round(ood["threshold_99"], 3),
            "out_of_range": bool(feats) or combo}


def stability(values: dict, runs=40, noise=0.05):
    """Re-run the prediction 40 times with Gaussian noise (5% of each feature's std)."""
    base = np.array([values[f] for f in FEATURES])
    X = base + RNG.normal(0, noise, (runs, len(FEATURES))) * STD
    X = np.clip(X, [HARD_LIMITS[f][0] for f in FEATURES], [HARD_LIMITS[f][1] for f in FEATURES])
    pred = model.predict(pd.DataFrame(X, columns=FEATURES))
    top = CLASSES[int(np.argmax(probabilities(values)))]
    return float(np.mean(pred != top))


def explain(values: dict, crop: str, n_ref=40, top=5):
    """Model-agnostic occlusion: replace one feature with random training values and see how
    much the probability of `crop` falls. Positive = feature supports the crop."""
    ci = CLASSES.index(crop); base = probabilities(values)[ci]
    ref = _TRAIN[RNG.integers(0, len(_TRAIN), n_ref)]
    res = []
    for j, f in enumerate(FEATURES):
        X = np.tile([values[g] for g in FEATURES], (n_ref, 1)); X[:, j] = ref[:, j]
        res.append({"feature": f, "value": values[f], "effect": round(float(base - _proba(X)[:, ci].mean()), 4)})
    res.sort(key=lambda r: abs(r["effect"]), reverse=True)
    for r in res:
        r["direction"] = "supports" if r["effect"] > 0 else "works against"
    return res[:top]


def predict(values: dict) -> dict:
    v = validate(values)
    rng = check_range(v)
    p = probabilities(v)
    tk = top_k(p, 5)
    ent = float(-(p[p > 0] * np.log(p[p > 0])).sum() / np.log(len(p)))
    margin = tk[0]["probability"] - tk[1]["probability"]
    change = stability(v)
    reasons = []
    if tk[0]["probability"] < 0.50: reasons.append(f"Top probability is only {tk[0]['probability']:.0%} (below 50%).")
    if margin < 0.15: reasons.append(f"Top two crops are close (margin {margin:.0%}, below 15%).")
    if change > 0.30: reasons.append(f"Top crop changed in {change:.0%} of 40 noisy re-runs (above 30%).")
    if rng["out_of_range"]:
        status = "OUT_OF_RANGE"
        reasons = [f"{u['feature']} = {u['value']} is outside the training range "
                   f"({u['train_min']:.1f}–{u['train_max']:.1f})." for u in rng["unusual_features"]]
        if rng["combination_unusual"]:
            reasons.append("This combination of values is more unusual than 99% of training rows.")
    else:
        status = "LOW_CONFIDENCE" if reasons else "OK"
    conf = "High" if status == "OK" and tk[0]["probability"] >= 0.8 and margin >= 0.3 else \
        "Low" if status != "OK" else "Medium"
    out = {"status": status, "confidence_label": conf, "normalized_entropy": round(ent, 4),
           "margin": round(margin, 4), "stability_change_rate": round(change, 3), "stability_runs": 40,
           "reasons": reasons, "out_of_range_check": rng, "input": v,
           "note": "Probability is the model's score on this dataset, not a guarantee of agricultural success."}
    if status == "OUT_OF_RANGE":
        out.update(crop=None, top_k=[], explanation=[])
        return out
    out.update(crop=tk[0]["crop"], top_k=tk[:3], all_probabilities={c: round(float(x), 4) for c, x in zip(CLASSES, p)},
               explanation=explain(v, tk[0]["crop"]))
    return out


_cache = {}
def robustness():
    """Noise on all features / one feature / missing feature, measured on the training+test data."""
    if "rob" in _cache: return _cache["rob"]
    X = DF[FEATURES].values; base = model.predict(pd.DataFrame(X, columns=FEATURES)); res = {"all_features": {}, "single_feature": {}, "missing_feature": {}}
    for lv in (0.05, 0.10, 0.20):
        Xn = X + RNG.normal(0, lv, X.shape) * STD
        res["all_features"][f"{int(lv*100)}%"] = round(float(np.mean(model.predict(pd.DataFrame(Xn, columns=FEATURES)) != base)), 4)
    for j, f in enumerate(FEATURES):
        Xn = X.copy(); Xn[:, j] += RNG.normal(0, 0.2, len(X)) * STD[j]
        res["single_feature"][f] = round(float(np.mean(model.predict(pd.DataFrame(Xn, columns=FEATURES)) != base)), 4)
        Xm = X.copy(); Xm[:, j] = X[:, j].mean()
        res["missing_feature"][f] = round(float(np.mean(model.predict(pd.DataFrame(Xm, columns=FEATURES)) != base)), 4)
    res["note"] = "Share of predictions that change. Noise = fraction of each feature's std. Missing feature = replaced by its mean."
    _cache["rob"] = res
    return res
