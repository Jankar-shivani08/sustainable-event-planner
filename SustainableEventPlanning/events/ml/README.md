# Event Planning ML Module

## Features and leakage prevention

Every target uses the same planning-time feature set:

- `event_type` and `catering_type` are categorical features. Missing values become `Unknown`, then `OneHotEncoder(handle_unknown='ignore')` encodes them.
- `duration`, `expected_attendees`, `food_quantity`, `plastic_quantity`, `paper_quantity`, and `material_quantity` are numeric features. Missing numeric values are filled with the training median inside the fitted pipeline.

The targets are trained separately:

- `attendance` -> `actual_attendees`
- `food_waste` -> `actual_food_waste`
- `plastic_waste` -> `actual_plastic_waste`
- `paper_waste` -> `actual_paper_waste`
- `material_waste` -> `actual_material_waste`

Post-event columns such as actual waste, total waste, sustainability score, and actual attendance are never included as input features. This prevents target leakage. Preprocessing is fitted only on the training split because it lives inside each scikit-learn `Pipeline`.

## Training

Use the sample file:

```powershell
D:\djangoapps\myenv_admin_panel\Scripts\python.exe D:\djangoapps\SustainableEventPlanning\manage.py train_ml_models --csv D:\djangoapps\SustainableEventPlanning\training_data\sample_historical_events.csv
```

To train from records uploaded through the Historical Dataset module, omit `--csv`:

```powershell
D:\djangoapps\myenv_admin_panel\Scripts\python.exe D:\djangoapps\SustainableEventPlanning\manage.py train_ml_models
```

The command compares Linear Regression, Decision Tree, and Random Forest for every target. It selects the lowest validation RMSE, using R2 as a tie-breaker, and reports MAE, RMSE, and R2 for all candidates. Artifacts are saved in `ml_models/` with Joblib.

## Waste risk classification

`RiskThresholdConfig` is a singleton configuration record available in Django admin under **Waste Risk Threshold Configuration**. The default limits are starting guardrails for the sample data scale, not hidden constants: low is at most 25 total waste units and 0.10 units per attendee; high begins above 75 total waste units or 0.20 units per attendee. Administrators should calibrate these values against their historical waste distribution and unit conventions.

Classification uses both measures:

- **LOW**: total waste and waste per attendee are both within their low limits.
- **HIGH**: either total waste or waste per attendee exceeds its medium limit.
- **MEDIUM**: all other combinations.

The normalized metric is `total_predicted_waste / predicted_attendance`. It prevents a large event from appearing safe merely because its absolute waste is distributed across many attendees, while the total-waste guardrail prevents a high-volume event from appearing safe only because its per-attendee ratio is low.

## Django prediction flow

`events/ml/prediction.py` loads `ml_models/<target>.joblib`, validates the eight required feature names, and calls the serialized pipeline. The admin prediction page at `/events/ml-predictions/` supplies those features and displays the five predictions. No prediction value is hard-coded; retraining replaces the artifacts used by Django.