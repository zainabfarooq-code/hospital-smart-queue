from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = DATA_DIR / "waiting_time_training.csv"
MODEL_FILE = MODEL_DIR / "waiting_time_model.joblib"

RANDOM_STATE = 42
SAMPLES = 2000


def generate_dataset() -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_STATE)

    queue_length = rng.integers(1, 30, SAMPLES)
    patients_ahead = rng.integers(0, queue_length + 1)
    appointment_hour = rng.integers(8, 18, SAMPLES)
    day_of_week = rng.integers(0, 7, SAMPLES)
    consultation_duration_minutes = rng.integers(10, 31, SAMPLES)
    arrival_delay_minutes = rng.integers(0, 31, SAMPLES)

    base_wait = (
        patients_ahead * consultation_duration_minutes
        + queue_length * 1.5
        + arrival_delay_minutes * 0.5
    )

    peak_hour_effect = np.where(
        (appointment_hour >= 10) & (appointment_hour <= 13),
        8,
        0,
    )

    weekday_effect = np.where(day_of_week < 5, 3, -2)

    noise = rng.normal(0, 8, SAMPLES)

    predicted_wait_minutes = np.maximum(
        0,
        base_wait + peak_hour_effect + weekday_effect + noise,
    )

    return pd.DataFrame(
        {
            "queue_length": queue_length,
            "patients_ahead": patients_ahead,
            "appointment_hour": appointment_hour,
            "day_of_week": day_of_week,
            "consultation_duration_minutes": consultation_duration_minutes,
            "arrival_delay_minutes": arrival_delay_minutes,
            "predicted_wait_minutes": predicted_wait_minutes,
        }
    )


def train() -> None:
    df = generate_dataset()

    df.to_csv(DATA_FILE, index=False)

    features = [
        "queue_length",
        "patients_ahead",
        "appointment_hour",
        "day_of_week",
        "consultation_duration_minutes",
        "arrival_delay_minutes",
    ]

    X = df[features]
    y = df["predicted_wait_minutes"]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=RANDOM_STATE,
    )

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=2,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    r2 = r2_score(y_test, predictions)

    joblib.dump(
        {
            "model": model,
            "features": features,
            "model_version": "1.0.0",
        },
        MODEL_FILE,
    )

    print("===== MODEL TRAINING COMPLETE =====")
    print(f"Dataset: {DATA_FILE}")
    print(f"Model:   {MODEL_FILE}")
    print(f"Samples: {len(df)}")
    print(f"MAE:     {mae:.2f} minutes")
    print(f"R2:      {r2:.4f}")


if __name__ == "__main__":
    train()
