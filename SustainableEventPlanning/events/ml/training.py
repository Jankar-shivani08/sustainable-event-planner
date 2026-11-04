import pandas as pd

from ..models import HistoricalEventRecord
from .pipeline import train_all_targets


def load_historical_records():
    records = HistoricalEventRecord.objects.all().values(
        'event_type', 'duration', 'expected_attendees', 'actual_attendees', 'catering_type',
        'food_quantity', 'plastic_quantity', 'paper_quantity', 'material_quantity',
        'actual_food_waste', 'actual_plastic_waste', 'actual_paper_waste',
        'actual_material_waste', 'total_actual_waste', 'sustainability_score',
    )
    return pd.DataFrame.from_records(records)


def train_from_database(output_dir):
    frame = load_historical_records()
    if frame.empty:
        raise ValueError('No historical event records are available for training.')
    return train_all_targets(frame, output_dir)