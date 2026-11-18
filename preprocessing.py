"""Step 1: load, inspect, clean and split the Crop Recommendation dataset."""
import pandas as pd
from sklearn.model_selection import train_test_split

DATA_PATH = "data/Crop_recommendation.csv"
FEATURES = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]
TARGET = "label"
RANDOM_STATE = 42
# Plausible physical limits, used only to FLAG invalid rows (not to invent data)
VALID_LIMITS = {"N": (0, 300), "P": (0, 300), "K": (0, 400), "temperature": (-5, 55),
                "humidity": (0, 100), "ph": (0, 14), "rainfall": (0, 1000)}


def load_and_inspect(path=DATA_PATH, verbose=True):
    df = pd.read_csv(path)
    report = {
        "rows": len(df), "columns": list(df.columns),
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
        "missing": df.isna().sum().to_dict(),
        "duplicates": int(df.duplicated().sum()),
        "n_classes": int(df[TARGET].nunique()),
        "class_counts": df[TARGET].value_counts().to_dict(),
        "ranges": {c: [float(df[c].min()), float(df[c].max())] for c in FEATURES},
    }
    if verbose:
        print(f"Rows: {report['rows']}  Columns: {report['columns']}")
        print("Missing:", report["missing"], "| Duplicates:", report["duplicates"])
        print("Classes:", report["n_classes"], "| per class:", set(report["class_counts"].values()))
    return df, report


def clean(df):
    """Drop exact duplicates, coerce numerics, impute any missing with the median
    (none are missing in this file), and flag physically impossible values."""
    df = df.drop_duplicates().copy()
    for c in FEATURES:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df[c] = df[c].fillna(df[c].median())
    df[TARGET] = df[TARGET].astype(str).str.strip().str.lower()
    invalid = {c: int(((df[c] < lo) | (df[c] > hi)).sum()) for c, (lo, hi) in VALID_LIMITS.items()}
    return df, invalid


def get_split(df):
    """80/20 stratified split. Scaling happens INSIDE model pipelines (no leakage)."""
    X, y = df[FEATURES], df[TARGET]
    return train_test_split(X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE)


if __name__ == "__main__":
    d, rep = load_and_inspect()
    d, bad = clean(d)
    print("Invalid-value counts:", bad)
