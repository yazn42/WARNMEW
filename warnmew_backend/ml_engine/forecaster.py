"""
Disease Forecaster using LSTM for WARNMEW Early Warning System.

Uses PyTorch LSTM to predict confirmed case counts based on:
- cases_lag_1d to cases_lag_14d (Past Health - 2 weeks context)
- month_sin, month_cos (Seasonality)
- temp_mean (Climate)
- rain_sum (Climate)
- search_interest (Social signals)
"""

import json
import os
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from sklearn.metrics import r2_score
import joblib

# Django setup - required before importing models
import os
import sys

# Add the project to the path
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'warnmew_backend.settings')

import django
django.setup()

from surveillance.models import DailyDiseaseRecord


class TimeSeriesModel(nn.Module):
    """LSTM or GRU Neural Network for time series forecasting."""
    
    def __init__(
        self, 
        input_size: int, 
        hidden_size: int = 64, 
        num_layers: int = 2, 
        output_size: int = 1,
        dropout: float = 0.2,
        model_type: str = 'lstm'  # 'lstm' or 'gru'
    ):
        super(TimeSeriesModel, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.model_type = model_type.lower()
        
        if self.model_type == 'gru':
            self.rnn = nn.GRU(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0
            )
        else:
            self.rnn = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0
            )
        
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, output_size)
        )
    
    def forward(self, x):
        # x shape: (batch, seq_len, input_size)
        if self.model_type == 'gru':
            out, _ = self.rnn(x)
        else:
            out, _ = self.rnn(x)
        
        # Take the last output
        out = self.fc(out[:, -1, :])
        return out


class DiseaseForecaster:
    """
    Disease forecasting engine using LSTM.
    
    Features used for prediction:
    - cases_lag_1d ... cases_lag_14d: Historical case counts (14-day lag)
    - month_sin, month_cos: Seasonality
    - temp_mean: Mean temperature
    - rain_sum: Total rainfall
    - search_interest: Google search interest
    
    Target: confirmed_case_count
    """
    
    # 14 Days of lags + Month sin/cos + 3 external
    LAG_DAYS = 14
    EXTERNAL_FEATURES = ['month_sin', 'month_cos', 'temp_mean', 'rain_sum', 'search_interest']
    TARGET = 'confirmed_case_count'
    
    @property
    def FEATURES(self):
        lags = [f'cases_lag_{i}d' for i in range(1, self.LAG_DAYS + 1)]
        return lags + self.EXTERNAL_FEATURES

    # Default sequence length, can be overridden during training
    DEFAULT_SEQUENCE_LENGTH = 30
    
    def __init__(self, models_dir: str = None):
        """
        Initialize the forecaster.
        
        Args:
            models_dir: Directory to save/load models. Defaults to 'models/' in project root.
        """
        if models_dir is None:
            base_dir = Path(__file__).resolve().parent.parent
            self.models_dir = base_dir / 'models'
        else:
            self.models_dir = Path(models_dir)
        
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
    def _safe_name(self, disease_name: str, district: str = None) -> str:
        """Generate safe filename prefix for model artifacts."""
        safe = disease_name.replace(' ', '_').lower()
        if district:
            safe += '_' + district.replace(' ', '_').lower()
        return safe
    
    def _get_model_path(self, disease_name: str, district: str = None) -> Path:
        """Get the model file path for a disease (and optionally a district)."""
        safe_name = self._safe_name(disease_name, district)
        return self.models_dir / f"{safe_name}_lstm.pt"
    
    def _get_scaler_path(self, disease_name: str, district: str = None) -> Path:
        """Get the scaler file path for a disease."""
        safe_name = self._safe_name(disease_name, district)
        return self.models_dir / f"{safe_name}_scaler.pkl"
    
    def _get_target_scaler_path(self, disease_name: str, district: str = None) -> Path:
        """Get the target scaler file path for a disease."""
        safe_name = self._safe_name(disease_name, district)
        return self.models_dir / f"{safe_name}_target_scaler.pkl"
    
    def _fetch_data(self, disease_name: str, district: str = None) -> pd.DataFrame:
        """
        Fetch data from database for a specific disease and optionally a district.
        """
        from surveillance.views import DISEASE_MAPPING
        
        mapping_key = None
        for k in DISEASE_MAPPING:
            if k.lower() == disease_name.lower():
                mapping_key = k
                break
                
        if not mapping_key:
            raise ValueError(f"Unknown disease: {disease_name}")

        qs = DailyDiseaseRecord.objects.all()
        if district:
            qs = qs.filter(district=district)
            
        mapping = DISEASE_MAPPING[mapping_key]

        cols = ['report_date', 'district', 'climate_avg_temp_c', 'climate_rainfall_mm', 'climate_humidity_percent']
        if mapping.get('confirmed'):
            cols.append(mapping['confirmed'])
            
        if "Fever" in mapping_key or "Dengue" in mapping_key:
            cols.extend(['social_search_index_fever', 'social_search_index_dengue'])

        records = qs.order_by('report_date').values(*cols)
        df = pd.DataFrame(list(records))
        
        label = disease_name
        if district:
            label += f" / {district}"
        
        if df.empty:
            raise ValueError(f"No data found for: {label}")
            
        rename_map = {
            'report_date': 'date',
            'climate_avg_temp_c': 'temp_mean',
            'climate_rainfall_mm': 'rain_sum',
            'climate_humidity_percent': 'humidity_mean'
        }
        if mapping.get('confirmed'):
            rename_map[mapping['confirmed']] = 'confirmed_case_count'
            
        if "Fever" in mapping_key and 'social_search_index_fever' in cols:
            rename_map['social_search_index_fever'] = 'search_interest'
        elif "Dengue" in mapping_key and 'social_search_index_dengue' in cols:
            rename_map['social_search_index_dengue'] = 'search_interest'
            
        df = df.rename(columns=rename_map)
        
        for req in ['confirmed_case_count', 'temp_mean', 'rain_sum', 'humidity_mean', 'search_interest']:
            if req not in df.columns:
                df[req] = 0.0

        df = df.fillna(0.0)
        
        # Ensure date is datetime
        df['date'] = pd.to_datetime(df['date'])
        
        # Create Month Sin/Cos Features
        df['month_sin'] = np.sin(2 * np.pi * df['date'].dt.month / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['date'].dt.month / 12)
        
        # Create cases_lag features (1 to 14 days)
        df = df.fillna(0)
        for i in range(1, self.LAG_DAYS + 1):
            df[f'cases_lag_{i}d'] = df['confirmed_case_count'].shift(i)
        df = df.fillna(0)  # Fill nan rows caused by shift
        
        return df
    
    def _prepare_sequences(
        self, 
        data: np.ndarray, 
        target: np.ndarray,
        sequence_length: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences for LSTM training.
        
        Args:
            data: Feature data (scaled)
            target: Target data (scaled)
            sequence_length: Length of sequences
            
        Returns:
            Tuple of (X sequences, y targets)
        """
        X, y = [], []
        
        for i in range(len(data) - sequence_length):
            X.append(data[i:(i + sequence_length)])
            y.append(target[i + sequence_length])
        
        return np.array(X), np.array(y)
    
    def train_model(
        self, 
        disease_name: str,
        epochs: int = 100,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        validation_split: float = 0.2,
        patience: int = 30,
        min_delta: float = 0.00001,
        verbose: bool = True,
        # Hyperparameters
        hidden_size: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
        sequence_length: int = 30,
        log_target: bool = False,
        model_type: str = 'lstm'
    ) -> Dict:
        """
        Train the LSTM model for a specific disease with customizable hyperparameters.
        """
        if verbose:
            print(f"\n{'='*60}")
            print(f"Training LSTM Model for: {disease_name}")
            print(f"{'='*60}")
        
        # Fetch data
        df = self._fetch_data(disease_name)
        if verbose:
            print(f"Loaded {len(df)} records")
            
        # Clean up old model file to ensure we don't load a mismatch if training fails to save
        model_path = self._get_model_path(disease_name)
        if model_path.exists():
            try:
                model_path.unlink()
            except PermissionError:
                pass # Might be open, ignore for now
                
        
        # Prepare features and target
        features = df[self.FEATURES].values
        target = df[self.TARGET].values.reshape(-1, 1)
        
        # Scale features
        # Note: Scaling Sin/Cos is fine, though they are already -1 to 1.
        feature_scaler = StandardScaler()
        features_scaled = feature_scaler.fit_transform(features)
        
        # Scale target
        # Optional: Log transform for sparse/skewed data (e.g. Hepatitis A, H1N1)
        if log_target:
            if verbose:
                print("Using Log1p Transformation on Target")
            target = np.log1p(target)
            
        target_scaler = StandardScaler()
        target_scaled = target_scaler.fit_transform(target)
        
        # Create sequences
        X, y = self._prepare_sequences(features_scaled, target_scaled, sequence_length)
        
        if len(X) < 10:
            raise ValueError(f"Not enough data for training. Need at least {sequence_length + 10} records.")
        
        # Split into train/validation
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        if verbose:
            print(f"Training samples: {len(X_train)}, Validation samples: {len(X_val)}")
        
        # Convert to tensors
        X_train = torch.FloatTensor(X_train).to(self.device)
        y_train = torch.FloatTensor(y_train).to(self.device)
        X_val = torch.FloatTensor(X_val).to(self.device)
        y_val = torch.FloatTensor(y_val).to(self.device)
        
        # Create model
        model = TimeSeriesModel(
            input_size=len(self.FEATURES),
            hidden_size=hidden_size,
            num_layers=num_layers,
            output_size=1,
            dropout=dropout,
            model_type=model_type
        ).to(self.device)
        
        # Loss and optimizer
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer, mode='min', factor=0.5, patience=10
        )
        
        # Training loop
        best_val_loss = float('inf')
        patience_counter = 0
        train_losses = []
        val_losses = []
        
        # Create indices for shuffling
        train_indices = np.arange(len(X_train))
        
        for epoch in range(epochs):
            model.train()
            
            # Shuffle training data
            np.random.shuffle(train_indices)
            X_train_shuffled = X_train[train_indices]
            y_train_shuffled = y_train[train_indices]
            
            # Mini-batch training
            total_loss = 0
            n_batches = 0
            
            for i in range(0, len(X_train), batch_size):
                batch_X = X_train_shuffled[i:i+batch_size]
                batch_y = y_train_shuffled[i:i+batch_size]
                
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                
                total_loss += loss.item()
                n_batches += 1
            
            train_loss = total_loss / n_batches
            train_losses.append(train_loss)
            
            # Validation
            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val)
                val_loss = criterion(val_outputs, y_val).item()
                val_losses.append(val_loss)
            
            # Update scheduler
            scheduler.step(val_loss)
            
            # Check for early stopping
            if val_loss < best_val_loss - min_delta:
                best_val_loss = val_loss
                torch.save(model.state_dict(), self._get_model_path(disease_name))
                patience_counter = 0
            else:
                patience_counter += 1
                
            if verbose and (epoch + 1) % 10 == 0:
                print(f"Epoch [{epoch+1}/{epochs}] Train Loss: {train_loss:.6f}, Val Loss: {val_loss:.6f}")
            
            if patience_counter >= patience:
                if verbose:
                    print(f"Early stopping triggered at epoch {epoch+1}")
                break
        
        # Calculate final metrics on validation set
        if self._get_model_path(disease_name).exists():
            try:
                model.load_state_dict(torch.load(self._get_model_path(disease_name), map_location=self.device))
            except Exception as e:
                if verbose:
                    print(f"Warning: Failed to load best model ({e}). Using last epoch weights.")
        else:
             if verbose:
                print("Warning: No best model saved (loss did not improve). Using last epoch weights.")

        model.eval()
        with torch.no_grad():
            val_outputs = model(X_val)
            val_preds = val_outputs.cpu().numpy()
            y_true = y_val.cpu().numpy()
            
            # Inverse transform to get actual values
            val_preds_actual = target_scaler.inverse_transform(val_preds)
            y_true_actual = target_scaler.inverse_transform(y_true)
            
            # Calculate R2 score (Accuracy)
            val_accuracy = r2_score(y_true_actual, val_preds_actual)
            
            # Calculate MAPE
            mask = y_true_actual != 0
            if mask.any():
                mape = np.mean(np.abs((y_true_actual[mask] - val_preds_actual[mask]) / y_true_actual[mask])) * 100
            else:
                mape = 0.0

        # Save params alongside model
        config = {
            'hidden_size': hidden_size,
            'num_layers': num_layers,
            'sequence_length': sequence_length,
            'log_target': log_target,
            'model_type': model_type,
            'features': self.FEATURES
        }
        joblib.dump(config, self.models_dir / f"{disease_name.replace(' ', '_').lower()}_config.pkl")
        
        # Save scalers
        joblib.dump(feature_scaler, self._get_scaler_path(disease_name))
        joblib.dump(target_scaler, self._get_target_scaler_path(disease_name))
        
        if verbose:
            print(f"\nTraining complete!")
            print(f"Model saved to: {self._get_model_path(disease_name)}")
            print(f"Best validation loss: {best_val_loss:.6f}")
            print(f"Validation Accuracy (R2 Score): {val_accuracy:.2%}")
            print(f"Validation MAPE: {mape:.2f}%")
        
        return {
            'disease_name': disease_name,
            'epochs_trained': epoch + 1,
            'best_val_loss': best_val_loss,
            'val_accuracy': val_accuracy,
            'val_mape': mape,
            'model_path': str(self._get_model_path(disease_name)),
            'config': config
        }
    
    def predict_next_7_days(
        self, 
        disease_name: str,
        district: str = None,
        return_json: bool = True
    ) -> Dict:
        """
        Predict the next 7 days of confirmed cases.
        
        Supports:
        - Zero-predictor models (for near-zero diseases)
        - Enhanced feature models (80+ features)
        - Legacy 19-feature models
        """
        safe_name = self._safe_name(disease_name, district)
        label = disease_name
        if district:
            label += f" / {district}"
        
        # Load config first to check for zero-predictor
        config_path = self.models_dir / f"{safe_name}_config.pkl"
        if config_path.exists():
            config = joblib.load(config_path)
        else:
            config = {}
        
        # =============================================
        # ZERO-PREDICTOR: Return 0 for all 7 days
        # =============================================
        if config.get('zero_predictor', False):
            last_date = datetime.now()
            predictions = []
            for day in range(7):
                pred_date = last_date + timedelta(days=day + 1)
                predictions.append({
                    'date': pred_date.strftime('%Y-%m-%d') if return_json else pred_date,
                    'day': day + 1,
                    'predicted_cases': 0
                })
            return {
                'disease_name': disease_name,
                'district': district or 'All',
                'last_known_date': last_date.strftime('%Y-%m-%d') if return_json else last_date,
                'forecast_generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'predictions': predictions,
                'total_predicted_cases': 0,
                'model_type': 'zero_predictor'
            }
        
        # =============================================
        # NEURAL NETWORK PREDICTION
        # =============================================
        model_path = self._get_model_path(disease_name, district)
        if not model_path.exists():
            raise FileNotFoundError(
                f"No trained model found for {label}. "
                f"Please train the model first."
            )
        
        hidden_size = config.get('hidden_size', 128)
        num_layers = config.get('num_layers', 2)
        sequence_length = config.get('sequence_length', 30)
        log_target = config.get('log_target', False)
        model_type = config.get('model_type', 'lstm')
        saved_features = config.get('features', None)
            
        # Load scalers
        feature_scaler = joblib.load(self._get_scaler_path(disease_name, district))
        target_scaler = joblib.load(self._get_target_scaler_path(disease_name, district))
        
        # Determine which features to use
        if saved_features and len(saved_features) > len(self.FEATURES):
            from ml_engine.feature_engineering import DiseaseFeatureEngineer
            engineer = DiseaseFeatureEngineer()
            features_to_use = saved_features
            use_enhanced = True
        else:
            features_to_use = self.FEATURES
            use_enhanced = False
        
        # Load model with correct input size
        model = TimeSeriesModel(
            input_size=len(features_to_use),
            hidden_size=hidden_size,
            num_layers=num_layers,
            output_size=1,
            model_type=model_type
        ).to(self.device)
        model.load_state_dict(torch.load(model_path, map_location=self.device, weights_only=True))
        model.eval()
        
        # Fetch recent data
        if use_enhanced:
            from surveillance.management.commands.train_optimized import EnhancedTrainer
            trainer = EnhancedTrainer(disease_name, district)
            df = trainer.fetch_and_prepare_data()
        else:
            df = self._fetch_data(disease_name, district)
        
        # Get last SEQUENCE_LENGTH days for initial prediction
        recent_features = df[features_to_use].values[-sequence_length:]
        recent_features_scaled = feature_scaler.transform(recent_features)
        
        # Get the last date
        last_date = df['date'].iloc[-1]
        
        # Dynamically find feature indices for iterative update
        lag_indices = []
        for i in range(1, self.LAG_DAYS + 1):
            fname = f'cases_lag_{i}d'
            if fname in features_to_use:
                lag_indices.append(features_to_use.index(fname))
        
        month_sin_idx = features_to_use.index('month_sin') if 'month_sin' in features_to_use else None
        month_cos_idx = features_to_use.index('month_cos') if 'month_cos' in features_to_use else None
        
        # Predict next 7 days iteratively
        predictions = []
        current_sequence = recent_features_scaled.copy()
        
        for day in range(7):
            # Prepare input
            X = torch.FloatTensor(current_sequence).unsqueeze(0).to(self.device)
            
            # Predict
            with torch.no_grad():
                pred_scaled = model(X).cpu().numpy()
            
            # Inverse transform prediction
            pred_raw_scale = target_scaler.inverse_transform(pred_scaled)[0, 0]
            
            # Inverse log transform if needed
            if log_target:
                pred = np.expm1(pred_raw_scale)
            else:
                pred = pred_raw_scale
                
            pred = max(0, int(round(pred)))  # Ensure non-negative integer
            
            # Calculate date
            pred_date = last_date + timedelta(days=day + 1)
            
            predictions.append({
                'date': pred_date.strftime('%Y-%m-%d') if return_json else pred_date,
                'day': day + 1,
                'predicted_cases': pred
            })
            
            # Update sequence for next prediction
            new_features = current_sequence[-1].copy()
            
            # 1. Update Lag features dynamically
            if len(lag_indices) > 1:
                for i in range(len(lag_indices) - 1, 0, -1):
                    new_features[lag_indices[i]] = new_features[lag_indices[i-1]]
            if lag_indices:
                new_features[lag_indices[0]] = pred_scaled[0, 0]
            
            # 2. Update Date Features (Month Sin/Cos)
            if month_sin_idx is not None and month_cos_idx is not None:
                raw_sin = np.sin(2 * np.pi * pred_date.month / 12)
                raw_cos = np.cos(2 * np.pi * pred_date.month / 12)
                
                if hasattr(feature_scaler, 'mean_'):
                    sin_center = feature_scaler.mean_[month_sin_idx]
                    cos_center = feature_scaler.mean_[month_cos_idx]
                elif hasattr(feature_scaler, 'center_'):
                    sin_center = feature_scaler.center_[month_sin_idx]
                    cos_center = feature_scaler.center_[month_cos_idx]
                else:
                    sin_center = 0
                    cos_center = 0
                
                sin_scale = feature_scaler.scale_[month_sin_idx]
                cos_scale = feature_scaler.scale_[month_cos_idx]
                
                new_features[month_sin_idx] = (raw_sin - sin_center) / sin_scale
                new_features[month_cos_idx] = (raw_cos - cos_center) / cos_scale
            
            current_sequence = np.vstack([current_sequence[1:], new_features])
        
        result = {
            'disease_name': disease_name,
            'district': district or 'All',
            'last_known_date': last_date.strftime('%Y-%m-%d') if return_json else last_date,
            'forecast_generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'predictions': predictions,
            'total_predicted_cases': sum(p['predicted_cases'] for p in predictions)
        }
        
        return result
    
    def get_available_diseases(self) -> List[str]:
        """Get list of diseases with available data."""
        diseases = DailyDiseaseRecord.objects.order_by().values_list(
            'disease_name', flat=True
        ).distinct()
        return sorted(list(diseases))
    
    def get_trained_models(self) -> List[Dict]:
        """Get list of trained models (disease + district combinations)."""
        trained = []
        for model_file in self.models_dir.glob('*_lstm.pt'):
            # Try to load config for accurate metadata
            config_path = model_file.with_name(
                model_file.stem.replace('_lstm', '_config') + '.pkl'
            )
            if config_path.exists():
                try:
                    config = joblib.load(config_path)
                    trained.append({
                        'disease_name': config.get('disease_name', model_file.stem),
                        'district': config.get('district', None),
                        'r2': config.get('final_r2', None),
                    })
                    continue
                except Exception:
                    pass
            # Fallback: parse from filename
            name = model_file.stem.replace('_lstm', '').replace('_', ' ').title()
            trained.append({'disease_name': name, 'district': None, 'r2': None})
        return sorted(trained, key=lambda x: (x['disease_name'], x.get('district') or ''))
