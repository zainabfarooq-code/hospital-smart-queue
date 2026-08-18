from pathlib import Path

import joblib
import pandas as pd

from app.core.config import settings


class PredictionService:
    FEATURES = [
        "queue_length",
        "patients_ahead",
        "appointment_hour",
        "day_of_week",
        "consultation_duration_minutes",
        "arrival_delay_minutes",
    ]

    def __init__(self) -> None:
        self.model = None
        self.model_version = None
        self._load_model()

    def _load_model(self) -> None:
        model_path = Path(settings.ml_model_path)

        if not model_path.exists():
            raise FileNotFoundError(
                f"ML model not found: {model_path}"
            )

        artifact = joblib.load(model_path)

        if not isinstance(artifact, dict):
            raise ValueError("Invalid ML model artifact.")

        model = artifact.get("model")
        features = artifact.get("features")
        version = artifact.get("model_version")

        if model is None:
            raise ValueError("ML model artifact is missing 'model'.")

        if features != self.FEATURES:
            raise ValueError(
                "ML model features do not match the prediction service."
            )

        self.model = model
        self.model_version = version or "unknown"

    def predict(
        self,
        *,
        queue_length: int,
        patients_ahead: int,
        appointment_hour: int,
        day_of_week: int,
        consultation_duration_minutes: int,
        arrival_delay_minutes: int,
    ) -> float:

        values = {
            "queue_length": queue_length,
            "patients_ahead": patients_ahead,
            "appointment_hour": appointment_hour,
            "day_of_week": day_of_week,
            "consultation_duration_minutes": (
                consultation_duration_minutes
            ),
            "arrival_delay_minutes": arrival_delay_minutes,
        }

        frame = pd.DataFrame([values], columns=self.FEATURES)

        prediction = float(self.model.predict(frame)[0])

        return max(0.0, round(prediction, 2))


prediction_service = PredictionService()
