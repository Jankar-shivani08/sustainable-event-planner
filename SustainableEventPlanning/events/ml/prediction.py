from pathlib import Path

import joblib
import pandas as pd
from django.conf import settings

from .pipeline import FEATURE_COLUMNS, TARGET_COLUMNS


MODEL_DIR = Path(settings.BASE_DIR) / 'ml_models'


def model_path(target_name):
    if target_name not in TARGET_COLUMNS:
        raise ValueError(f'Unknown target: {target_name}')
    return MODEL_DIR / f'{target_name}.joblib'


def load_model(target_name):
    path = model_path(target_name)
    if not path.exists():
        raise FileNotFoundError(f'Model for {target_name} is not trained. Run train_ml_models first.')
    return joblib.load(path)


def predict_target(target_name, event_features):
    artifact = load_model(target_name)
    missing = set(FEATURE_COLUMNS) - set(event_features)
    if missing:
        raise ValueError(f'Missing prediction features: {", ".join(sorted(missing))}')
    frame = pd.DataFrame([{column: event_features[column] for column in FEATURE_COLUMNS}])
    return max(0.0, float(artifact['pipeline'].predict(frame)[0]))


def predict_all(event_features):
    return {target_name: predict_target(target_name, event_features) for target_name in TARGET_COLUMNS}


def model_version_summary():
    versions = []
    for target_name in TARGET_COLUMNS:
        versions.append(f'{target_name}:{load_model(target_name)["selected_model"]}')
    return '; '.join(versions)


def waste_risk_level(total_predicted_waste, predicted_attendance, thresholds=None):
    from ..models import RiskThresholdConfig

    thresholds = thresholds or RiskThresholdConfig.active()
    waste_per_attendee = total_predicted_waste / predicted_attendance if predicted_attendance > 0 else float('inf')
    if (
        total_predicted_waste <= thresholds.low_max_total_waste
        and waste_per_attendee <= thresholds.low_max_waste_per_attendee
    ):
        return 'Low'
    if (
        total_predicted_waste > thresholds.medium_max_total_waste
        or waste_per_attendee > thresholds.medium_max_waste_per_attendee
    ):
        return 'High'
    return 'Medium'