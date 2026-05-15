"""
Model Comparison Management Command for WARNMEW.

Trains and compares all model types (LSTM, SARIMA, RF, XGBoost, SVR)
for specified diseases, producing a comparison report.

Usage:
    python manage.py compare_models
    python manage.py compare_models --disease "Dengue Fever"
    python manage.py compare_models --dry-run
"""

from django.core.management.base import BaseCommand
from surveillance.models import DailyDiseaseRecord
from ml_engine.forecaster import DiseaseForecaster
from ml_engine.sarima_model import SARIMAForecaster
from ml_engine.baseline_models import BaselineForecaster
import json
from pathlib import Path


class Command(BaseCommand):
    help = 'Train and compare all model types for disease forecasting'

    def add_arguments(self, parser):
        parser.add_argument('--disease', type=str, help='Compare models for a specific disease')
        parser.add_argument('--dry-run', action='store_true', help='Only show which models would be trained')
        parser.add_argument('--skip-lstm', action='store_true', help='Skip LSTM training (slow)')

    def handle(self, *args, **options):
        target_disease = options.get('disease')
        dry_run = options.get('dry_run', False)
        skip_lstm = options.get('skip_lstm', False)

        # Get diseases
        if target_disease:
            diseases = [target_disease]
        else:
            from surveillance.views import DISEASE_MAPPING
            diseases = list(DISEASE_MAPPING.keys())

        self.stdout.write(f"Comparing models for {len(diseases)} diseases...\n")

        all_results = {}

        for disease in diseases:
            self.stdout.write(self.style.HTTP_INFO(f"\n{'='*60}"))
            self.stdout.write(self.style.HTTP_INFO(f"  {disease}"))
            self.stdout.write(self.style.HTTP_INFO(f"{'='*60}"))

            results = []

            # --- LSTM ---
            if not skip_lstm:
                self.stdout.write("  Training LSTM...")
                if not dry_run:
                    try:
                        forecaster = DiseaseForecaster()
                        metrics = forecaster.train_model(disease, epochs=50)
                        r2 = metrics.get('best_r2', metrics.get('r2_score', 0))
                        results.append({
                            'model': 'LSTM',
                            'r2_score': round(max(0, r2), 4),
                            'mae': metrics.get('mae', 'N/A'),
                        })
                        self.stdout.write(self.style.SUCCESS(f"    LSTM: R²={r2:.4f}"))
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"    LSTM failed: {e}"))
                        results.append({'model': 'LSTM', 'error': str(e)})

            # --- SARIMA ---
            self.stdout.write("  Training SARIMA...")
            if not dry_run:
                try:
                    sarima = SARIMAForecaster()
                    metrics = sarima.train(disease)
                    results.append({
                        'model': 'SARIMA',
                        'r2_score': metrics['r2_score'],
                        'mae': metrics['mae'],
                    })
                    self.stdout.write(self.style.SUCCESS(
                        f"    SARIMA: R²={metrics['r2_score']:.4f}, MAE={metrics['mae']:.4f}"
                    ))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    SARIMA failed: {e}"))
                    results.append({'model': 'SARIMA', 'error': str(e)})

            # --- Traditional ML Baselines ---
            baseline = BaselineForecaster()
            for model_type in baseline.get_available_models():
                model_name = model_type.replace('_', ' ').title()
                self.stdout.write(f"  Training {model_name}...")
                if not dry_run:
                    try:
                        metrics = baseline.train(disease, model_type)
                        results.append({
                            'model': metrics['model'],
                            'r2_score': metrics['r2_score'],
                            'mae': metrics['mae'],
                        })
                        self.stdout.write(self.style.SUCCESS(
                            f"    {metrics['model']}: R²={metrics['r2_score']:.4f}, MAE={metrics['mae']:.4f}"
                        ))
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"    {model_name} failed: {e}"))
                        results.append({'model': model_name, 'error': str(e)})

            # Sort by R² descending
            valid = [r for r in results if 'r2_score' in r]
            valid.sort(key=lambda x: x['r2_score'], reverse=True)

            if valid:
                best = valid[0]
                self.stdout.write(self.style.SUCCESS(
                    f"\n  🏆 Best model: {best['model']} (R²={best['r2_score']:.4f})"
                ))

            all_results[disease] = results

        # Save comparison results
        if not dry_run:
            output_dir = Path(__file__).resolve().parent.parent.parent / 'models'
            output_dir.mkdir(exist_ok=True)
            comparison_path = output_dir / 'model_comparison.json'
            with open(comparison_path, 'w') as f:
                json.dump(all_results, f, indent=2, default=str)
            self.stdout.write(self.style.SUCCESS(
                f"\nResults saved to {comparison_path}"
            ))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Compared {len(diseases)} disease(s)."))
