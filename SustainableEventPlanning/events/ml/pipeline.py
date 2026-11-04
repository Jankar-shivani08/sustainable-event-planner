from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeRegressor


FEATURE_COLUMNS = [
    'event_type',
    'duration',
    'expected_attendees',
    'catering_type',
    'food_quantity',
    'plastic_quantity',
    'paper_quantity',
    'material_quantity',
]

TARGET_COLUMNS = {
    'attendance': 'actual_attendees',
    'food_waste': 'actual_food_waste',
    'plastic_waste': 'actual_plastic_waste',
    'paper_waste': 'actual_paper_waste',
    'material_waste': 'actual_material_waste',
}

NUMERIC_FEATURES = [column for column in FEATURE_COLUMNS if column not in {'event_type', 'catering_type'}]
CATEGORICAL_FEATURES = ['event_type', 'catering_type']


@dataclass
class TrainingResult:
    target_name: str
    target_column: str
    selected_model: str
    metrics: dict[str, dict[str, float]]
    artifact_path: str
    rows_used: int


def clean_training_frame(frame):
    cleaned = frame.copy()
    for column in CATEGORICAL_FEATURES:
        cleaned[column] = cleaned[column].fillna('Unknown').astype(str).str.strip()
    for column in set(FEATURE_COLUMNS + list(TARGET_COLUMNS.values())) - set(CATEGORICAL_FEATURES):
        cleaned[column] = pd.to_numeric(cleaned[column], errors='coerce')
    return cleaned


def build_preprocessor():
    return ColumnTransformer([
        ('numeric', Pipeline([('imputer', SimpleImputer(strategy='median'))]), NUMERIC_FEATURES),
        ('categorical', Pipeline([
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('encoder', OneHotEncoder(handle_unknown='ignore')),
        ]), CATEGORICAL_FEATURES),
    ])


def candidate_models():
    return {
        'linear_regression': LinearRegression(),
        'decision_tree': DecisionTreeRegressor(max_depth=8, random_state=42),
        'random_forest': RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1),
    }


def train_target(frame, target_name, output_dir, test_size=0.2, random_state=42):
    if target_name not in TARGET_COLUMNS:
        raise ValueError(f'Unknown target: {target_name}')
    target_column = TARGET_COLUMNS[target_name]
    cleaned = clean_training_frame(frame)
    missing_columns = set(FEATURE_COLUMNS + [target_column]) - set(cleaned.columns)
    if missing_columns:
        raise ValueError(f'Missing training columns: {", ".join(sorted(missing_columns))}')
    cleaned = cleaned.dropna(subset=[target_column])
    if len(cleaned) < 10:
        raise ValueError(f'{target_name} requires at least 10 rows with a valid target; found {len(cleaned)}')
    if cleaned[target_column].nunique() < 2:
        raise ValueError(f'{target_name} requires at least two distinct target values')

    x_train, x_test, y_train, y_test = train_test_split(
        cleaned[FEATURE_COLUMNS], cleaned[target_column], test_size=test_size, random_state=random_state,
    )
    metrics = {}
    fitted_models = {}
    for model_name, estimator in candidate_models().items():
        pipeline = Pipeline([('preprocessor', build_preprocessor()), ('model', estimator)])
        pipeline.fit(x_train, y_train)
        predictions = pipeline.predict(x_test)
        metrics[model_name] = {
            'mae': float(mean_absolute_error(y_test, predictions)),
            'rmse': float(np.sqrt(mean_squared_error(y_test, predictions))),
            'r2': float(r2_score(y_test, predictions)),
        }
        fitted_models[model_name] = pipeline

    selected_model = min(metrics, key=lambda name: (metrics[name]['rmse'], -metrics[name]['r2']))
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    artifact_path = output_path / f'{target_name}.joblib'
    joblib.dump({
        'pipeline': fitted_models[selected_model],
        'target_name': target_name,
        'target_column': target_column,
        'feature_columns': FEATURE_COLUMNS,
        'selected_model': selected_model,
        'metrics': metrics,
        'rows_used': len(cleaned),
    }, artifact_path)
    return TrainingResult(target_name, target_column, selected_model, metrics, str(artifact_path), len(cleaned))


def train_all_targets(frame, output_dir):
    return [train_target(frame, target_name, output_dir) for target_name in TARGET_COLUMNS]