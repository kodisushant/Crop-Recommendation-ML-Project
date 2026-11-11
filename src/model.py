import pandas as pd
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

# 1. Load data
df = pd.read_csv("data/Crop_recommendation.csv")
print("Shape:", df.shape)

# 2. Clean data
df["label"] = df["label"].str.strip().str.lower()   # tidy crop names
print("Missing values:", df.isnull().sum().sum())
df = df.dropna()
print("Duplicates:", df.duplicated().sum())
df = df.drop_duplicates()

# 3. Features / target, encode crop names as numbers
X = df.drop("label", axis=1)
le = LabelEncoder()
y = le.fit_transform(df["label"])

# 4. Split: 80% train, 20% test
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y)

# 5. Train Random Forest (best settings found by tuning; no scaling needed)
model = RandomForestClassifier(n_estimators=200, max_depth=None,
                               max_features="sqrt", random_state=42)
model.fit(X_train, y_train)

# 6. Predict on test data
y_pred = model.predict(X_test)

# 7. Evaluate
print("\nTest accuracy:", round(accuracy_score(y_test, y_pred), 4))
print("5-fold CV accuracy:", round(cross_val_score(model, X, y, cv=5).mean(), 4))
print("\n", classification_report(y_test, y_pred, target_names=le.classes_))

cm = confusion_matrix(y_test, y_pred)
plt.figure(figsize=(12, 10))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
            xticklabels=le.classes_, yticklabels=le.classes_)
plt.xlabel("Predicted"); plt.ylabel("Actual")
plt.title("Random Forest - Confusion Matrix")
plt.tight_layout()
plt.show()

# 8. Which features matter most
imp = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
print("Feature importance:\n", imp.round(3))
imp.plot(kind="bar", title="Feature importance"); plt.tight_layout(); plt.show()

# 9. Predict a new sample: N, P, K, temperature, humidity, ph, rainfall
new_data = pd.DataFrame([[90, 42, 43, 20.9, 82.0, 6.5, 203.0]], columns=X.columns)
print("\nRecommended crop:", le.inverse_transform(model.predict(new_data))[0])

# 10. Save the model for later use


joblib.dump(
    {"model": model, "label_encoder": le},
    "models/random_forest_crop.joblib"
)