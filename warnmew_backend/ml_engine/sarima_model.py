"""
SARIMA (Seasonal ARIMA) Baseline Model for WARNMEW.

Provides statistical time-series forecasting as a baseline comparison
against the deep learning (LSTM/GRU) approach.

Uses statsmodels SARIMAX with automatic parameter selection.
"""

import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import timedelta
from typing import Optional, Dict, List

warnings.filterwarnings('ignore')

import os, sys
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'warnmew_backend.settings')

import django
django.setup()

from surveillance.models import DailyDiseaseRecord


class SARIMAForecaster:
    """
    SARIMA-based disease forecaster.
    
    Uses Seasonal ARIMA (SARIMAX) for time-series prediction of disease cases.
    Acts as a statistical baseline for comparison with deep learning models.
    """

    def __init__(self, models_dir: str = None):
        if models_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.models_dir = base_dir / 'models' / 'sarima'
        else:
            self.models_dir = Path(models_dir) / 'sarima'
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def _get_model_path(self, disease_name: str) -> Path:
        safe_name = disease_name.replace(' ', '_').lower()
        return self.models_dir / f'{safe_name}_sarima.pkl'

    def _get_metrics_path(self, disease_name: str) -> Path:
        safe_name = disease_name.replace(' ', '_').lower()
        return self.models_dir / f'{safe_name}_metrics.pkl'

    def _fetch_data(self, disease_name: str) -> pd.DataFrame:
        """Fetch and aggregate daily case data for a disease."""
        from django.db.models import Sum
        from surveillance.views import DISEASE_MAPPING

        # Look up disease name case-insensitively
        mapping_key = None
        for k in DISEASE_MAPPING:
            if k.lower() == disease_name.lower():
                mapping_key = k
                break
        if not mapping_key:
            raise ValueError(f"Unknown disease: {disease_name}")

        mapping = DISEASE_MAPPING[mapping_key]
        confirmed_col = mapping.get('confirmed')
        if not confirmed_col:
            raise ValueError(f"No confirmed case column for disease: {disease_name}")

        # Aggregate daily cases across all districts
        records = (
            DailyDiseaseRecord.objects
            .values('report_date')
            .annotate(cases=Sum(confirmed_col))
            .order_by('report_date')
        )
        if not records:
            raise ValueError(f"No data found for disease: {disease_name}")

        df = pd.DataFrame(list(records))
        df = df.rename(columns={'report_date': 'date'})
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date').asfreq('D', fill_value=0)
        return df

    def _auto_select_params(self, data: pd.Series) -> dict:
        """
        Auto-select SARIMA parameters using AIC grid search.
        Tests a small grid of common configurations for speed.
        """
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        best_aic = float('inf')
        best_params = {'order': (1, 1, 1), 'seasonal_order': (1, 1, 1, 7)}

        # Test grid — focus on weekly seasonality (period=7)
        p_values = [0, 1, 2]
        d_values = [0, 1]
        q_values = [0, 1, 2]

        for p in p_values:
            for d in d_values:
                for q in q_values:
                    try:
                        model = SARIMAX(
                            data,
                            order=(p, d, q),
                            seasonal_order=(1, 1, 1, 7),
                            enforce_stationarity=False,
                            enforce_invertibility=False
                        )
                        result = model.fit(disp=False, maxiter=50)
                        if result.aic < best_aic:
                            best_aic = result.aic
                            best_params = {
                                'order': (p, d, q),
                                'seasonal_order': (1, 1, 1, 7)
                            }
                    except Exception:
                        continue

        return best_params

    def train(self, disease_name: str, auto_params: bool = True) -> dict:
        """
        Train a SARIMA model for a disease.
        
        Returns:
            Dictionary with model parameters and metrics (R², MAE, AIC).
        """
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        from sklearn.metrics import r2_score, mean_absolute_error

        df = self._fetch_data(disease_name)
        data = df['cases'].clip(lower=0).astype(float)

        if len(data) < 30:
            raise ValueError(f"Insufficient data for {disease_name}: need >=30 days, got {len(data)}")

        # Split: last 30 days for test
        train_size = len(data) - 30
        train_data = data[:train_size]
        test_data = data[train_size:]

        # Select parameters
        if auto_params:
            params = self._auto_select_params(train_data)
        else:
            params = {'order': (1, 1, 1), 'seasonal_order': (1, 1, 1, 7)}

        # Fit model
        model = SARIMAX(
            train_data,
            order=params['order'],
            seasonal_order=params['seasonal_order'],
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        result = model.fit(disp=False, maxiter=200)

        # Evaluate on test set
        forecast = result.forecast(steps=len(test_data))
        forecast = np.clip(forecast, 0, None)

        r2 = max(0, r2_score(test_data.values, forecast.values))
        mae = mean_absolute_error(test_data.values, forecast.values)

        # Refit on full data for deployment
        full_model = SARIMAX(
            data,
            order=params['order'],
            seasonal_order=params['seasonal_order'],
            enforce_stationarity=False,
            enforce_invertibility=False
        )
        full_result = full_model.fit(disp=False, maxiter=200)

        # Save
        model_path = self._get_model_path(disease_name)
        joblib.dump(full_result, model_path)

        metrics = {
            'disease': disease_name,
            'model': 'SARIMA',
            'params': params,
            'r2_score': round(r2, 4),
            'mae': round(mae, 4),
            'aic': round(full_result.aic, 2),
            'data_points': len(data),
            'train_size': train_size,
            'test_size': len(test_data),
        }
        joblib.dump(metrics, self._get_metrics_path(disease_name))

        return metrics

    def predict_next_7_days(self, disease_name: str, return_json: bool = True):
        """
        Predict the next 7 days using the saved SARIMA model.
        
        Returns format matching DiseaseForecaster for consistency.
        """
        model_path = self._get_model_path(disease_name)
        if not model_path.exists():
            raise FileNotFoundError(f"No SARIMA model found for {disease_name}. Train first.")

        result = joblib.load(model_path)
        forecast = result.forecast(steps=7)
        forecast = np.clip(forecast, 0, None)

        # Build prediction list
        last_date = result.data.dates[-1]
        if hasattr(last_date, 'date'):
            last_date = last_date
        else:
            last_date = pd.Timestamp(last_date)

        predictions = []
        for i, pred in enumerate(forecast):
            pred_date = last_date + timedelta(days=i + 1)
            predictions.append({
                'date': pred_date.strftime('%Y-%m-%d'),
                'predicted_cases': round(float(pred), 2),
                'model': 'SARIMA'
            })

        if return_json:
            return {'predictions': predictions, 'model': 'SARIMA', 'disease': disease_name}
        return predictions

    def get_trained_models(self) -> List[str]:
        """List diseases with trained SARIMA models."""
        models = list(self.models_dir.glob('*_sarima.pkl'))
        return [m.stem.replace('_sarima', '').replace('_', ' ').title() for m in models]
