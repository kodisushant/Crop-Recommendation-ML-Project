"""Step 2: train & compare 8 classifiers, pick the best by CV accuracy, save everything."""
import os, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import json, joblib, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import KNeighborsClassifier
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.naive_bayes import GaussianNB
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import (accuracy_score, precision_recall_fscore_support, f1_score,
                             classification_report, confusion_matrix, top_k_accuracy_score)
from .preprocessing import load_and_inspect, clean, get_split, FEATURES, RANDOM_STATE

BASE = Path(__file__).resolve().parents[2]

S = RANDOM_STATE
# Scaled models get a StandardScaler INSIDE the pipeline (fit on training folds only).
MODELS = {
    "KNN": Pipeline([("scale", StandardScaler()), ("m", KNeighborsClassifier(n_neighbors=5))]),
    "SVM": Pipeline([("scale", StandardScaler()), ("m", SVC(probability=True, random_state=S))]),
    "Logistic Regression": Pipeline([("scale", StandardScaler()), ("m", LogisticRegression(max_iter=2000))]),
    "Random Forest": Pipeline([("m", RandomForestClassifier(n_estimators=200, random_state=S))]),
    "Extra Trees": Pipeline([("m", ExtraTreesClassifier(n_estimators=200, random_state=S))]),
    "Gradient Boosting": Pipeline([("m", GradientBoostingClassifier(random_state=S))]),
    "Gaussian NB": Pipeline([("m", GaussianNB())]),
    "Decision Tree": Pipeline([("m", DecisionTreeClassifier(random_state=S))]),
}
GREEN, FRESH = "#174D32", "#4C956C"


def main():
    df, report = load_and_inspect(); df, invalid = clean(df)
    Xtr, Xte, ytr, yte = get_split(df)
    cv = StratifiedKFold(5, shuffle=True, random_state=S)
    rows, fitted = [], {}
    for name, pipe in MODELS.items():
        cvs = cross_val_score(pipe, Xtr, ytr, cv=cv, scoring="accuracy")
        cvf = cross_val_score(pipe, Xtr, ytr, cv=cv, scoring="f1_macro")
        pipe.fit(Xtr, ytr); fitted[name] = pipe
        pred = pipe.predict(Xte)
        p, r, f, _ = precision_recall_fscore_support(yte, pred, average="weighted", zero_division=0)
        top3 = top_k_accuracy_score(yte, pipe.predict_proba(Xte), k=3, labels=pipe.classes_)
        rows.append({"Model": name, "CV Accuracy": cvs.mean(), "CV Std": cvs.std(), "CV Macro F1": cvf.mean(),
                     "Test Accuracy": accuracy_score(yte, pred), "Precision": p, "Recall": r,
                     "F1-score": f, "Macro F1": f1_score(yte, pred, average="macro"), "Top-3 Accuracy": top3})
        print(f"{name:20s} CV={cvs.mean():.4f}±{cvs.std():.4f} test={rows[-1]['Test Accuracy']:.4f}")
    res = pd.DataFrame(rows).sort_values("CV Accuracy", ascending=False).reset_index(drop=True)
    # Selection rule: highest CV accuracy; models within TIE (0.005, about one CV std) of the
    # top are treated as tied and ranked by CV macro-F1, then by lower CV std (stability).
    TIE = 0.005
    tied = res[res["CV Accuracy"] >= res["CV Accuracy"].max() - TIE]
    best_name = tied.sort_values(["CV Macro F1", "CV Std"], ascending=[False, True]).iloc[0]["Model"]
    tied_names = list(tied["Model"]); rule_pick = best_name
    # Production choice among the tied models: Random Forest gives better-behaved probabilities
    # than Gaussian NB (needed for confidence analysis). Override with PRODUCTION_MODEL env var.
    prod = os.environ.get("PRODUCTION_MODEL", "Random Forest")
    if prod in tied_names: best_name = prod
    best = fitted[best_name]
    print("\n", res.round(4).to_string(index=False), "\nTIED:", tied_names, "\nBEST:", best_name)

    pred = best.predict(Xte); classes = list(best.classes_)
    cr = classification_report(yte, pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(yte, pred, labels=classes)

    # ---- plots ----
    fig, ax = plt.subplots(figsize=(9, 5)); y = np.arange(len(res))
    ax.barh(y - .2, res["CV Accuracy"], .4, label="CV accuracy", color=GREEN)
    ax.barh(y + .2, res["Test Accuracy"], .4, label="Test accuracy", color=FRESH)
    ax.set_yticks(y); ax.set_yticklabels(res["Model"]); ax.invert_yaxis(); ax.set_xlim(.8, 1.01)
    ax.legend(loc="lower left"); ax.set_title("Model comparison (8 classifiers)"); fig.tight_layout()
    fig.savefig(BASE / "plots/model_comparison.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 8.5)); ax.imshow(cm, cmap="Greens")
    ax.set_xticks(range(len(classes))); ax.set_yticks(range(len(classes)))
    ax.set_xticklabels(classes, rotation=90); ax.set_yticklabels(classes)
    for i in range(len(classes)):
        for j in range(len(classes)):
            if cm[i, j]: ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=7, color="black")
    ax.set_xlabel("Predicted"); ax.set_ylabel("Actual"); ax.set_title(f"Confusion matrix – {best_name}")
    fig.tight_layout(); fig.savefig(BASE / "plots/confusion_matrix.png", dpi=130); plt.close(fig)
    fig, ax = plt.subplots(figsize=(12, 5)); x = np.arange(len(classes))
    for k, (m, c) in enumerate([("precision", GREEN), ("recall", FRESH), ("f1-score", "#DCECCB")]):
        ax.bar(x + (k - 1) * .27, [cr[c_][m] for c_ in classes], .27, label=m, color=c, edgecolor="#999", linewidth=.3)
    ax.set_xticks(x); ax.set_xticklabels(classes, rotation=60, ha="right"); ax.set_ylim(.8, 1.02)
    ax.legend(ncol=3); ax.set_title("Class-wise precision / recall / F1"); fig.tight_layout()
    fig.savefig(BASE / "plots/classwise_metrics.png", dpi=130); plt.close(fig)

    # ---- out-of-range detector (Mahalanobis distance, 99th percentile on training rows) ----
    Xall = pd.concat([Xtr, Xte]); Xtr_np = Xtr.values.astype(float)
    mu = Xtr_np.mean(0); cov = np.cov(Xtr_np, rowvar=False); icov = np.linalg.inv(cov)
    d = np.sqrt(np.einsum("ij,jk,ik->i", Xtr_np - mu, icov, Xtr_np - mu))
    ood = {"features": FEATURES, "mean": mu, "inv_cov": icov, "threshold_99": float(np.percentile(d, 99)),
           "min": Xtr.min().to_dict(), "max": Xtr.max().to_dict(),
           "p01": Xtr.quantile(.01).to_dict(), "p99": Xtr.quantile(.99).to_dict(),
           "std": Xtr.std().to_dict(), "train_X": Xtr_np}
    joblib.dump(ood, BASE / "models/ood_detector.pkl")
    joblib.dump(best, BASE / "models/best_model.pkl")
    joblib.dump({"features": FEATURES, "classes": classes, "mean": mu, "std": Xtr_np.std(0)}, BASE / "models/scaler.pkl")
    out = {"dataset": {"rows": report["rows"], "n_classes": report["n_classes"], "features": FEATURES,
                       "duplicates": report["duplicates"], "missing": report["missing"], "invalid": invalid,
                       "ranges": report["ranges"]},
           "best_model": best_name, "selected_by_rule": rule_pick, "tied_models": tied_names, "tie_tolerance": TIE, "comparison": res.round(4).to_dict("records"),
           "classwise": {c: {k: round(v, 4) for k, v in cr[c].items()} for c in classes},
           "classes": classes, "confusion_matrix": cm.tolist(),
           "test": {"accuracy": round(accuracy_score(yte, pred), 4), "macro_f1": round(f1_score(yte, pred, average="macro"), 4)},
           "ood_threshold": ood["threshold_99"]}
    json.dump(out, open(BASE / "models/metrics.json", "w"), indent=2)
    res.round(4).to_csv(BASE / "models/model_comparison.csv", index=False)


if __name__ == "__main__":
    main()
