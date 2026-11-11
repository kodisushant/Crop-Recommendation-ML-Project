
import pandas as pd
import joblib

from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.ensemble import IsolationForest

# Project paths
ROOT = Path(__file__).resolve().parents[1]

# 1. Load dataset
df = pd.read_csv(ROOT / "data" / "Crop_recommendation.csv")

X = df.drop("label", axis=1)
y = df["label"]

# 2. Split dataset
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# 3. Create OOD detector
detector = IsolationForest(
    n_estimators=100,
    contamination=0.05,
    random_state=42
)

# 4. Learn normal training data
detector.fit(X_train)

# 5. Save detector
joblib.dump(
    {
        "detector": detector,
        "features": list(X.columns)
    },
    ROOT / "models" / "ood_detector.joblib"
)

print("OOD detector trained successfully!")

# 6. Test one input
sample = X_test.iloc[[0]]

result = detector.predict(sample)

if result[0] == 1:
    print("Normal input")
else:
    print("Unusual input - OOD detected")
