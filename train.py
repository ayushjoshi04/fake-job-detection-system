"""
Train Script — Fake vs Real Job Detection (Stable Unified Pipeline)
-------------------------------------------------------------------
Dataset must have columns:
['job_title', 'salary_range', 'company_profile', 'requirements', 'fraudulent']

Label: 0 = Real, 1 = Fake
"""

import os
import re
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler, FunctionTransformer
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, accuracy_score
from sklearn.ensemble import RandomForestClassifier
from imblearn.over_sampling import RandomOverSampler
import joblib
import numpy as np

# ---------------- PATHS ---------------- #
ROOT = os.path.dirname(__file__)
DATA_PATH = os.path.join(ROOT, "data", "dataset.csv")
MODELS_DIR = os.path.join(ROOT, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# ---------------- CLEAN SALARY ---------------- #
def clean_salary(s):
    if pd.isna(s) or str(s).strip() == "":
        return 0.0
    s = str(s)
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d+)?", s)]
    if not nums:
        return 0.0
    return sum(nums) / len(nums)

# ---------------- LOAD DATA ---------------- #
def load_data():
    df = pd.read_csv(DATA_PATH)
    expected_cols = {"job_title", "salary_range", "company_profile", "requirements", "fraudulent"}
    if not expected_cols.issubset(df.columns):
        raise ValueError(f"Dataset must have columns: {expected_cols}")

    df = df.fillna("")
    df["salary_range"] = df["salary_range"].apply(clean_salary)
    df["text"] = (
        df["job_title"].astype(str) + " " +
        df["company_profile"].astype(str) + " " +
        df["requirements"].astype(str)
    )

    X = df[["text", "salary_range"]]
    y = df["fraudulent"].astype(int)
    return X, y

# ---------------- MAIN ---------------- #
def main():
    print(f"📂 Loading dataset from: {DATA_PATH}")
    X, y = load_data()

    print("🔀 Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # ⚖️ Balance classes
    print("⚖️ Balancing classes...")
    ros = RandomOverSampler(random_state=42)
    X_bal, y_bal = ros.fit_resample(X_train, y_train)

    # ---------------- PIPELINE ---------------- #
    text_features = "text"
    numeric_features = ["salary_range"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=15000, stop_words="english", ngram_range=(1, 2)), text_features),
            ("num", Pipeline([
                ("scaler", StandardScaler(with_mean=False)),
            ]), numeric_features)
        ]
    )

    model = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    )

    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model", model)
    ])

    print("⚙️ Training model...")
    pipeline.fit(X_bal, y_bal)

    print("📊 Evaluating model...")
    preds = pipeline.predict(X_test)
    print(f"Accuracy: {accuracy_score(y_test, preds):.4f}")
    print(classification_report(y_test, preds))

    joblib.dump(pipeline, os.path.join(MODELS_DIR, "model.pkl"))
    print(f"✅ Model saved successfully at: {MODELS_DIR}\\model.pkl")
    print("🚀 Ready for Flask integration!")

if __name__ == "__main__":
    main()
