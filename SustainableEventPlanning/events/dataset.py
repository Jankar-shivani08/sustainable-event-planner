from dataclasses import dataclass

import pandas as pd


REQUIRED_COLUMNS = [
    'event_type',
    'duration',
    'expected_attendees',
    'actual_attendees',
    'catering_type',
    'food_quantity',
    'plastic_quantity',
    'paper_quantity',
    'material_quantity',
    'actual_food_waste',
    'actual_plastic_waste',
    'actual_paper_waste',
    'actual_material_waste',
    'total_actual_waste',
    'sustainability_score',
]

INTEGER_COLUMNS = {'expected_attendees', 'actual_attendees'}
NUMERIC_COLUMNS = set(REQUIRED_COLUMNS) - {'event_type', 'catering_type'}


@dataclass
class DatasetImportResult:
    valid_rows: list[dict]
    invalid_rows: list[dict]
    missing_columns: list[str]


def process_historical_csv(file_object):
    frame = pd.read_csv(file_object)
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing_columns:
        return DatasetImportResult([], [], missing_columns)

    frame = frame[REQUIRED_COLUMNS].copy()
    invalid_rows = []
    valid_rows = []
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        cleaned = {column: row[column] for column in REQUIRED_COLUMNS}
        errors = []
        for column in ('event_type', 'catering_type'):
            value = cleaned[column]
            if pd.isna(value) or not str(value).strip():
                errors.append(f'{column} is missing')
            else:
                cleaned[column] = str(value).strip()

        for column in NUMERIC_COLUMNS:
            value = pd.to_numeric(cleaned[column], errors='coerce')
            if pd.isna(value):
                errors.append(f'{column} must be numeric and not missing')
            elif value < 0:
                errors.append(f'{column} cannot be negative')
            elif column in INTEGER_COLUMNS and float(value) != int(value):
                errors.append(f'{column} must be a whole number')
            else:
                cleaned[column] = int(value) if column in INTEGER_COLUMNS else float(value)

        if errors:
            invalid_rows.append({'row_number': row_number, 'errors': errors, 'values': cleaned})
        else:
            valid_rows.append(cleaned)

    return DatasetImportResult(valid_rows, invalid_rows, [])