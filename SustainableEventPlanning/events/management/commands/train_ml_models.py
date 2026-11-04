from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from events.ml.pipeline import train_all_targets
from events.ml.training import load_historical_records


class Command(BaseCommand):
    help = 'Train and save attendance and waste prediction models.'

    def add_arguments(self, parser):
        parser.add_argument('--csv', help='Optional CSV file instead of HistoricalEventRecord rows.')
        parser.add_argument('--output-dir', default=str(Path(settings.BASE_DIR) / 'ml_models'))

    def handle(self, *args, **options):
        try:
            frame = pd.read_csv(options['csv']) if options['csv'] else load_historical_records()
            if frame.empty:
                raise ValueError('No historical rows available.')
            results = train_all_targets(frame, options['output_dir'])
        except (OSError, ValueError, pd.errors.ParserError) as error:
            raise CommandError(str(error)) from error
        for result in results:
            self.stdout.write(self.style.SUCCESS(
                f'{result.target_name}: {result.selected_model} selected; '
                f'rows={result.rows_used}; artifact={result.artifact_path}'
            ))
            for model_name, metric_values in result.metrics.items():
                self.stdout.write(
                    f'  {model_name}: '
                    f'MAE={metric_values["mae"]:.4f}, '
                    f'RMSE={metric_values["rmse"]:.4f}, '
                    f'R2={metric_values["r2"]:.4f}'
                )