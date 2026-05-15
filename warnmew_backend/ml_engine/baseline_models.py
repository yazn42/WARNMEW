"""
Traditional ML Baseline Models for WARNMEW.

Provides Random Forest, XGBoost, and SVR baselines for comparison
against the LSTM deep learning model and SARIMA statistical model.

All models use the same feature set as the LSTM forecaster for fair comparison.
"""

import warnings
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from datetime import timedelta
from typing import Dict, List, Optional

warnings.filterwarnings('ignore')

import os, sys
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'warnmew_backend.settings')

import django
django.setup()

from sklearn.ensemble import RandomForestRegressor
from sklearn.svm import SVR
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

from surveillance.models import DailyDiseaseRecord


# Feature columns (same as LSTM forecaster)
LAG_DAYS = 14
FEATURE_COLS = [f'cases_lag_{i}d' for i in range(1, LAG_DAYS + 1)] + [
    'month_sin', 'month_cos', 'temp_mean', 'rain_sum', 'search_interest'
]
TARGET = 'confirmed_case_count'

# Available models
MODEL_REGISTRY = {
    'random_forest': {
        'class': RandomForestRegressor,
        'params': {
            'n_estimators': 200,
            'max_depth': 12,
            'min_samples_split': 5,
            'min_samples_leaf': 3,
            'random_state': 42,
            'n_jobs': -1,
        },
        'name': 'Random Forest',
    },
    'svr': {
        'class': SVR,
        'params': {
            'kernel': 'rbf',
            'C': 10.0,
            'epsilon': 0.1,
            'gamma': 'scale',
        },
        'name': 'SVR',
    },
}

if HAS_XGBOOST:
    MODEL_REGISTRY['xgboost'] = {
        'class': XGBRegressor,
        'params': {
            'n_estimators': 200,
            'max_depth': 6,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': 42,
            'verbosity': 0,
        },
        'name': 'XGBoost',
    }


class BaselineForecaster:
    """
    Traditional ML baseline forecaster supporting RF, XGBoost, and SVR.
    
    Uses the same features as the LSTM model for fair comparison.
    """

    def __init__(self, models_dir: str = None):
        if models_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.models_dir = base_dir / 'models' / 'baselines'
        else:
            self.models_dir = Path(models_dir) / 'baselines'
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def _get_model_path(self, disease_name: str, model_type: str) -> Path:
        safe_name = disease_name.replace(' ', '_').lower()
        return self.models_dir / f'{safe_name}_{model_type}.pkl'

    def _get_scaler_path(self, disease_name: str) -> Path:
        safe_name = disease_name.replace(' ', '_').lower()
        return self.models_dir / f'{safe_name}_scaler.pkl'

    def _get_metrics_path(self, disease_name: str, model_type: str) -> Path:
        safe_name = disease_name.replace(' ', '_').lower()
        return self.models_dir / f'{safe_name}_{model_type}_metrics.pkl'

    def _fetch_and_prepare_data(self, disease_name: str):
        """
        Fetch disease data from DB and prepare features.
        Returns (X, y, dates) with lag features, month encoding, and external data.
        """
        from django.db.models import Sum, Avg
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

        # Build annotation kwargs using actual DB column names
        annotate_kwargs = {
            'confirmed_case_count': Sum(confirmed_col),
            'temp_mean': Avg('climate_avg_temp_c'),
            'rain_sum': Avg('climate_rainfall_mm'),
            'search_dengue': Avg('social_search_index_dengue'),
            'search_fever': Avg('social_search_index_fever'),
        }

        records = (
            DailyDiseaseRecord.objects
            .values('report_date')
            .annotate(**annotate_kwargs)
            .order_by('report_date')
        )

        if not records:
            raise ValueError(f"No data found for disease: {disease_name}")

        df = pd.DataFrame(list(records))
        df = df.rename(columns={'report_date': 'date'})
        df['date'] = pd.to_datetime(df['date'])

        # Combine search indices into single feature
        search_vals = df[['search_dengue', 'search_fever']].mean(axis=1)
        df['search_interest'] = search_vals.fillna(0)
        df = df.drop(columns=['search_dengue', 'search_fever'], errors='ignore')

        # Fill missing values
        for col in ['temp_mean', 'rain_sum', 'search_interest']:
            if col in df.columns:
                df[col] = df[col].fillna(df[col].median() if df[col].notna().any() else 0)

        # Create lag features
        for lag in range(1, LAG_DAYS + 1):
            df[f'cases_lag_{lag}d'] = df['confirmed_case_count'].shift(lag).fillna(0)

        # Month encoding
        df['month_sin'] = np.sin(2 * np.pi * df['date'].dt.month / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['date'].dt.month / 12)

        # Drop initial rows without enough lag history
        df = df.dropna(subset=FEATURE_COLS).reset_index(drop=True)

        if len(df) < 30:
            raise ValueError(f"Insufficient data for {disease_name}: need >=30 rows, got {len(df)}")

        X = df[FEATURE_COLS].values.astype(float)
        y = df[TARGET].values.astype(float)
        dates = df['date'].values

        return X, y, dates

    def train(self, disease_name: str, model_type: str = 'random_forest') -> dict:
        """
        Train a specific baseline model for a disease.
        
        Args:
            disease_name: Disease to train for
            model_type: One of 'random_forest', 'xgboost', 'svr'
            
        Returns:
            Dictionary with model name, R², MAE, and training metadata.
        """
        if model_type not in MODEL_REGISTRY:
            raise ValueError(f"Unknown model type: {model_type}. Available: {list(MODEL_REGISTRY.keys())}")

        config = MODEL_REGISTRY[model_type]
        X, y, dates = self._fetch_and_prepare_data(disease_name)

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        joblib.dump(scaler, self._get_scaler_path(disease_name))

        # Train/test split (last 30 days for test)
        split = len(X) - 30
        X_train, X_test = X_scaled[:split], X_scaled[split:]
        y_train, y_test = y[:split], y[split:]

        # Train model
        model = config['class'](**config['params'])
        model.fit(X_train, y_train)

        # Evaluate
        y_pred = model.predict(X_test)
        y_pred = np.clip(y_pred, 0, None)

        r2 = max(0, r2_score(y_test, y_pred))
        mae = mean_absolute_error(y_test, y_pred)

        # Retrain on full data
        model_full = config['class'](**config['params'])
        model_full.fit(X_scaled, y)

        # Save model
        joblib.dump(model_full, self._get_model_path(disease_name, model_type))

        metrics = {
            'disease': disease_name,
            'model': config['name'],
            'model_type': model_type,
            'r2_score': round(r2, 4),
            'mae': round(mae, 4),
            'data_points': len(X),
            'train_size': split,
            'test_size': 30,
            'features_used': len(FEATURE_COLS),
        }
        joblib.dump(metrics, self._get_metrics_path(disease_name, model_type))

        return metrics

    def train_all(self, disease_name: str) -> List[dict]:
        """Train all available baseline models for a disease."""
        results = []
        for model_type in MODEL_REGISTRY:
            try:
                metrics = self.train(disease_name, model_type)
                results.append(metrics)
            except Exception as e:
                results.append({
                    'disease': disease_name,
                    'model': MODEL_REGISTRY[model_type]['name'],
                    'model_type': model_type,
                    'error': str(e),
                })
        return results

    def predict_next_7_days(self, disease_name: str, model_type: str = 'random_forest',
                            return_json: bool = True):
        """
        Predict next 7 days using a trained baseline model.
        
        Uses a rolling approach: predict day 1, use that as lag for day 2, etc.
        """
        model_path = self._get_model_path(disease_name, model_type)
        scaler_path = self._get_scaler_path(disease_name)

        if not model_path.exists():
            raise FileNotFoundError(f"No {model_type} model found for {disease_name}. Train first.")

        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)

        # Get recent data for lag features
        X, y, dates = self._fetch_and_prepare_data(disease_name)
        last_row = X[-1].copy()
        last_date = pd.Timestamp(dates[-1])

        predictions = []
        rolling_cases = list(y[-LAG_DAYS:])

        for i in range(7):
            # Build feature vector with updated lags
            feature_vec = last_row.copy()
            for lag in range(LAG_DAYS):
                if lag < len(rolling_cases):
                    feature_vec[lag] = rolling_cases[-(lag + 1)]

            # Update month encoding for the prediction day
            pred_date = last_date + timedelta(days=i + 1)
            feature_vec[LAG_DAYS] = np.sin(2 * np.pi * pred_date.month / 12)
            feature_vec[LAG_DAYS + 1] = np.cos(2 * np.pi * pred_date.month / 12)

            # Predict
            feature_scaled = scaler.transform(feature_vec.reshape(1, -1))
            pred = model.predict(feature_scaled)[0]
            pred = max(0, pred)

            predictions.append({
                'date': pred_date.strftime('%Y-%m-%d'),
                'predicted_cases': round(float(pred), 2),
                'model': MODEL_REGISTRY[model_type]['name'],
            })

            rolling_cases.append(pred)

        model_name = MODEL_REGISTRY[model_type]['name']
        if return_json:
            return {'predictions': predictions, 'model': model_name, 'disease': disease_name}
        return predictions

    def get_available_models(self) -> List[str]:
        """Return list of available model types."""
        return list(MODEL_REGISTRY.keys())
