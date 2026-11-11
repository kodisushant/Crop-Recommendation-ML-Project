
import pandas as pd
import numpy as np
import joblib

from pathlib import Path
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[1]

# 1. Load trained ML model
bundle = joblib.load(
    ROOT / "models" / "random_forest_crop.joblib"
)

model = bundle["model"]

# 2. Load dataset
df = pd.read_csv(ROOT / "data" / "Crop_recommendation.csv")

X = df.drop("label", axis=1)
y = bundle["label_encoder"].transform(df["label"])

# 3. Get test data
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42,
    stratify=y
)

# 4. Original predictions
original_predictions = model.predict(X_test)

# 5. Add small random noise
rng = np.random.default_rng(42)

noise = rng.normal(
    loc=0,
    scale=X_train.std().to_numpy() * 0.01,
    size=X_test.shape
)

X_noisy = X_test + noise

# 6. Predictions after noise
noisy_predictions = model.predict(X_noisy)

# 7. Compare predictions
agreement = np.mean(
    original_predictions == noisy_predictions
)

print("Original accuracy:",
      model.score(X_test, y_test))

print("Noisy data accuracy:",
      model.score(X_noisy, y_test))

print("Prediction agreement:",
      round(agreement * 100, 2), "%")
