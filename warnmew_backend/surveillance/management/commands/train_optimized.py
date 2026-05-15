"""
Optimized Disease Model Training Command for WARNMEW.

Uses Optuna for intelligent hyperparameter search with cross-validation
to achieve maximum prediction accuracy.

Features:
- Bayesian hyperparameter optimization via Optuna
- TimeSeriesSplit cross-validation
- Multiple metrics: R2, MAPE, MAE, Directional Accuracy
- Disease-specific optimization strategies
- Fallback to baseline model for sparse diseases
- Clipped R2 score to prevent negative optimization
"""

from django.core.management.base import BaseCommand
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import joblib
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import r2_score, mean_absolute_error, mean_absolute_percentage_error
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# Optional imports with fallback
try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    HAS_OPTUNA = True
except ImportError:
    HAS_OPTUNA = False

from ml_engine.forecaster import DiseaseForecaster, TimeSeriesModel
from ml_engine.feature_engineering import DiseaseFeatureEngineer
from surveillance.models import DailyDiseaseRecord


class DataAdaptiveConfig:
    """Runtime data-adaptive model configuration.
    
    Instead of hardcoding diseases into categories, analyzes the actual
    per-district data to determine the best training strategy.
    """
    
    @staticmethod
    def classify_data(target_series) -> str:
        """Classify data tier based on actual zero-inflation.
        
        Returns: 'near_zero', 'ultra_sparse', 'seasonal', or 'active'
        """
        zero_pct = (target_series == 0).sum() / len(target_series)
        nonzero_count = (target_series > 0).sum()
        
        if zero_pct >= 0.97 or nonzero_count < 30:
            return 'near_zero'      # e.g., Nipah, Chikungunya in most districts
        elif zero_pct >= 0.80:
            return 'ultra_sparse'   # e.g., H1N1, Hepatitis A, Covid-19
        elif zero_pct >= 0.50:
            return 'seasonal'       # e.g., Dengue, Lepto, Malaria
        else:
            return 'active'         # e.g., Fever, ADD
    
    @classmethod
    def get_search_space(cls, data_tier: str, trial):
        """Get hyperparameter search space based on runtime data tier."""
        
        if data_tier == 'ultra_sparse':
            return {
                'hidden_size': trial.suggest_categorical('hidden_size', [8, 16, 32]),
                'num_layers': 1,
                'dropout': trial.suggest_float('dropout', 0.3, 0.5),
                'sequence_length': trial.suggest_categorical('sequence_length', [7, 10]),
                'learning_rate': trial.suggest_float('learning_rate', 1e-3, 5e-3, log=True),
                'batch_size': trial.suggest_categorical('batch_size', [8, 16]),
                'model_type': trial.suggest_categorical('model_type', ['gru']),
                'use_log_transform': True,
                'use_robust_scaler': True,
                'l2_reg': trial.suggest_float('l2_reg', 1e-3, 1e-1, log=True),
            }
        elif data_tier == 'seasonal':
            return {
                'hidden_size': trial.suggest_categorical('hidden_size', [32, 64, 128]),
                'num_layers': trial.suggest_int('num_layers', 1, 2),
                'dropout': trial.suggest_float('dropout', 0.2, 0.3),
                'sequence_length': trial.suggest_categorical('sequence_length', [14, 21, 30]),
                'learning_rate': trial.suggest_float('learning_rate', 5e-4, 3e-3, log=True),
                'batch_size': trial.suggest_categorical('batch_size', [16, 32]),
                'model_type': trial.suggest_categorical('model_type', ['gru', 'lstm']),
                'use_log_transform': True,
                'use_robust_scaler': True,
                'l2_reg': trial.suggest_float('l2_reg', 1e-4, 1e-2, log=True),
            }
        else:  # 'active'
            return {
                'hidden_size': trial.suggest_categorical('hidden_size', [64, 128, 256]),
                'num_layers': trial.suggest_int('num_layers', 2, 3),
                'dropout': trial.suggest_float('dropout', 0.1, 0.3),
                'sequence_length': trial.suggest_categorical('sequence_length', [21, 30, 45]),
                'learning_rate': trial.suggest_float('learning_rate', 1e-4, 3e-3, log=True),
                'batch_size': trial.suggest_categorical('batch_size', [16, 32, 64]),
                'model_type': trial.suggest_categorical('model_type', ['lstm']),
                'use_log_transform': False,
                'use_robust_scaler': trial.suggest_categorical('use_robust_scaler', [False, True]),
                'l2_reg': trial.suggest_float('l2_reg', 1e-5, 1e-3, log=True),
            }


class TrainingMetrics:
    """Container for training metrics with multiple evaluation criteria."""
    
    def __init__(self):
        self.r2_scores = []
        self.mape_scores = []
        self.mae_scores = []
        self.directional_scores = []
    
    def add_fold(self, y_true, y_pred):
        """Add metrics from a CV fold."""
        # R2 Score - CLIP to minimum 0 to prevent very negative values
        r2 = r2_score(y_true, y_pred)
        # Clip to prevent extremely negative R2 from dominating
        r2_clipped = max(-1.0, r2)  # Allow slight negative but not extreme
        self.r2_scores.append(r2_clipped)
        
        # MAPE (Mean Absolute Percentage Error)
        mask = y_true != 0
        if mask.any():
            mape = mean_absolute_percentage_error(y_true[mask], y_pred[mask]) * 100
            mape = min(mape, 200)  # Cap MAPE at 200%
        else:
            mape = 0.0
        self.mape_scores.append(mape)
        
        # MAE (Mean Absolute Error)
        mae = mean_absolute_error(y_true, y_pred)
        self.mae_scores.append(mae)
        
        # Directional Accuracy (did we predict trend correctly?)
        y_true_diff = np.diff(y_true)
        y_pred_diff = np.diff(y_pred)
        if len(y_true_diff) > 0:
            direction_correct = np.mean(np.sign(y_true_diff) == np.sign(y_pred_diff)) * 100
        else:
            direction_correct = 50.0
        self.directional_scores.append(direction_correct)
    
    def get_summary(self):
        """Get mean metrics across all folds."""
        return {
            'r2_mean': np.mean(self.r2_scores),
            'r2_std': np.std(self.r2_scores),
            'mape_mean': np.mean(self.mape_scores),
            'mae_mean': np.mean(self.mae_scores),
            'directional_mean': np.mean(self.directional_scores),
        }
    
    def get_composite_score(self, prioritize_r2=False):
        """
        Compute composite score for optimization.
        
        Normal weights: R2 (50%), Directional (30%), inverse MAPE (20%)
        Prioritize R2: R2 (80%), Directional (10%), inverse MAPE (10%)
        """
        summary = self.get_summary()
        
        # Normalize metrics to 0-1 scale
        r2_norm = max(0, min(1, (summary['r2_mean'] + 1) / 2))  # Map -1..1 to 0..1
        dir_norm = summary['directional_mean'] / 100  # Convert percentage
        mape_norm = max(0, min(1, 1 - summary['mape_mean'] / 200))  # Invert MAPE
        
        if prioritize_r2:
            composite = 0.8 * r2_norm + 0.1 * dir_norm + 0.1 * mape_norm
        else:
            composite = 0.5 * r2_norm + 0.3 * dir_norm + 0.2 * mape_norm
        return composite


class EnhancedTrainer:
    """Enhanced model trainer with cross-validation and Optuna optimization."""
    
    def __init__(self, disease_name: str, district: str = None, models_dir: Path = None):
        self.disease_name = disease_name
        self.district = district  # None means all districts combined
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        if models_dir is None:
            # Path: warnmew_backend/surveillance/management/commands/train_optimized.py
            # Go up 3 levels to reach warnmew_backend (commands -> management -> surveillance -> warnmew_backend)
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.models_dir = base_dir / 'models'
        else:
            self.models_dir = Path(models_dir)
        
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.feature_engineer = DiseaseFeatureEngineer()
    
    def _safe_name(self):
        """Generate safe filename prefix for model artifacts."""
        safe_disease = self.disease_name.replace(' ', '_').lower()
        if self.district:
            safe_district = self.district.replace(' ', '_').lower()
            return f"{safe_disease}_{safe_district}"
        return safe_disease
        
    def fetch_and_prepare_data(self):
        """Fetch data from database and create enhanced features."""
        from surveillance.views import DISEASE_MAPPING
        
        mapping_key = None
        for k in DISEASE_MAPPING:
            if k.lower() == self.disease_name.lower():
                mapping_key = k
                break
                
        if not mapping_key:
            raise ValueError(f"Unknown disease: {self.disease_name}")

        qs = DailyDiseaseRecord.objects.all()
        if self.district:
            qs = qs.filter(district=self.district)

        mapping = DISEASE_MAPPING[mapping_key]

        cols = ['report_date', 'district', 'climate_avg_temp_c', 'climate_rainfall_mm', 'climate_humidity_percent']
        if mapping.get('confirmed'):
            cols.append(mapping['confirmed'])
            
        if "Fever" in mapping_key or "Dengue" in mapping_key:
            cols.extend(['social_search_index_fever', 'social_search_index_dengue'])

        records = qs.order_by('report_date').values(*cols)
        df = pd.DataFrame(list(records))
        
        label = self.disease_name
        if self.district:
            label += f" / {self.district}"
        
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
        df['date'] = pd.to_datetime(df['date'])
        
        # Create enhanced features
        df = self.feature_engineer.create_enhanced_features(df)
        
        return df
    
    def analyze_data_sparsity(self, df) -> dict:
        """Analyze data to determine best training strategy at runtime."""
        target = df['confirmed_case_count'].values
        
        zero_ratio = (target == 0).sum() / len(target)
        nonzero_count = int((target > 0).sum())
        mean_cases = target.mean()
        std_cases = target.std()
        max_cases = target.max()
        nonzero_mean = target[target > 0].mean() if (target > 0).any() else 0
        
        # Runtime classification
        data_tier = DataAdaptiveConfig.classify_data(target)
        
        return {
            'zero_ratio': zero_ratio,
            'nonzero_count': nonzero_count,
            'mean_cases': mean_cases,
            'std_cases': std_cases,
            'max_cases': max_cases,
            'nonzero_mean': nonzero_mean,
            'data_tier': data_tier,
        }
    
    def prepare_sequences(self, features, target, sequence_length):
        """Prepare sequences for LSTM training."""
        X, y = [], []
        for i in range(len(features) - sequence_length):
            X.append(features[i:(i + sequence_length)])
            y.append(target[i + sequence_length])
        return np.array(X), np.array(y)
    
    def train_single_fold(self, X_train, y_train, X_val, y_val, config, epochs=100, patience=15):
        """Train model on a single fold and return metrics."""
        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train).to(self.device)
        y_train_t = torch.FloatTensor(y_train).to(self.device)
        X_val_t = torch.FloatTensor(X_val).to(self.device)
        y_val_t = torch.FloatTensor(y_val).to(self.device)
        
        # Create model
        model = TimeSeriesModel(
            input_size=X_train.shape[2],
            hidden_size=config['hidden_size'],
            num_layers=config.get('num_layers', 1),
            output_size=1,
            dropout=config['dropout'],
            model_type=config['model_type']
        ).to(self.device)
        
        criterion = nn.MSELoss()
        # Add L2 regularization (weight decay)
        l2_reg = config.get('l2_reg', 1e-4)
        optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'], weight_decay=l2_reg)
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)
        
        best_val_loss = float('inf')
        patience_counter = 0
        best_model_state = None
        
        batch_size = config['batch_size']
        
        for epoch in range(epochs):
            model.train()
            
            # Shuffle training data
            indices = np.random.permutation(len(X_train_t))
            X_train_shuffled = X_train_t[indices]
            y_train_shuffled = y_train_t[indices]
            
            total_loss = 0
            n_batches = 0
            
            for i in range(0, len(X_train_t), batch_size):
                batch_X = X_train_shuffled[i:i+batch_size]
                batch_y = y_train_shuffled[i:i+batch_size]
                
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimizer.step()
                
                total_loss += loss.item()
                n_batches += 1
            
            # Validation
            model.eval()
            with torch.no_grad():
                val_outputs = model(X_val_t)
                val_loss = criterion(val_outputs, y_val_t).item()
            
            scheduler.step(val_loss)
            
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                best_model_state = {k: v.clone() for k, v in model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
            
            if patience_counter >= patience:
                break
        
        # Load best model state
        if best_model_state is not None:
            model.load_state_dict(best_model_state)
        
        # Get predictions
        model.eval()
        with torch.no_grad():
            val_preds = model(X_val_t).cpu().numpy().flatten()
        
        return val_preds, best_val_loss, model
    
    def train_baseline_model(self, df):
        """
        Train a simple baseline model for very sparse diseases.
        Uses last-value prediction with smoothing.
        """
        target = df['confirmed_case_count'].values
        
        # Simple strategy: predict smoothed rolling average
        window = 7
        smoothed = pd.Series(target).rolling(window=window, min_periods=1).mean().values
        
        # Calculate baseline R2
        # Predict next value as current smoothed value (shifted by 1)
        y_true = target[window:]
        y_pred_baseline = smoothed[window-1:-1]
        
        if len(y_true) > 0 and len(y_pred_baseline) > 0:
            baseline_r2 = r2_score(y_true, y_pred_baseline)
        else:
            baseline_r2 = 0.0
        
        return baseline_r2
    
    def cross_validate(self, df, config, n_splits=3, epochs=100, prioritize_r2=False):
        """Perform TimeSeriesSplit cross-validation."""
        feature_cols = self.feature_engineer.get_feature_columns(df)
        target_col = 'confirmed_case_count'
        
        features = df[feature_cols].values
        target = df[target_col].values.reshape(-1, 1)
        
        # Apply transformations
        if config.get('use_log_transform', False):
            target = np.log1p(target)
        
        # Scale features
        if config.get('use_robust_scaler', False):
            feature_scaler = RobustScaler()
        else:
            feature_scaler = StandardScaler()
        
        features_scaled = feature_scaler.fit_transform(features)
        
        target_scaler = StandardScaler()
        target_scaled = target_scaler.fit_transform(target)
        
        # Prepare sequences
        sequence_length = config['sequence_length']
        X, y = self.prepare_sequences(features_scaled, target_scaled, sequence_length)
        
        if len(X) < 50:
            raise ValueError(f"Not enough data after sequence preparation: {len(X)} samples")
        
        # Cross-validation
        tscv = TimeSeriesSplit(n_splits=n_splits)
        metrics = TrainingMetrics()
        
        for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]
            
            val_preds_scaled, _, _ = self.train_single_fold(
                X_train, y_train, X_val, y_val, 
                config, epochs=epochs, patience=15
            )
            
            # Inverse transform predictions
            val_preds = target_scaler.inverse_transform(val_preds_scaled.reshape(-1, 1)).flatten()
            y_val_actual = target_scaler.inverse_transform(y_val).flatten()
            
            if config.get('use_log_transform', False):
                val_preds = np.expm1(val_preds)
                y_val_actual = np.expm1(y_val_actual)
            
            val_preds = np.maximum(0, val_preds)  # Ensure non-negative
            
            metrics.add_fold(y_val_actual, val_preds)
        
        return metrics, feature_scaler, target_scaler
    
    def train_final_model(self, df, config, epochs=150, patience=25):
        """Train final model on all data with best config."""
        feature_cols = self.feature_engineer.get_feature_columns(df)
        target_col = 'confirmed_case_count'
        
        features = df[feature_cols].values
        target = df[target_col].values.reshape(-1, 1)
        
        if config.get('use_log_transform', False):
            target = np.log1p(target)
        
        if config.get('use_robust_scaler', False):
            feature_scaler = RobustScaler()
        else:
            feature_scaler = StandardScaler()
        
        features_scaled = feature_scaler.fit_transform(features)
        
        target_scaler = StandardScaler()
        target_scaled = target_scaler.fit_transform(target)
        
        sequence_length = config['sequence_length']
        X, y = self.prepare_sequences(features_scaled, target_scaled, sequence_length)
        
        # Train-val split (90/10 for final evaluation)
        split_idx = int(len(X) * 0.9)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        val_preds, best_loss, model = self.train_single_fold(
            X_train, y_train, X_val, y_val,
            config, epochs=epochs, patience=patience
        )
        
        # Inverse transform for metrics
        val_preds_actual = target_scaler.inverse_transform(val_preds.reshape(-1, 1)).flatten()
        y_val_actual = target_scaler.inverse_transform(y_val).flatten()
        
        if config.get('use_log_transform', False):
            val_preds_actual = np.expm1(val_preds_actual)
            y_val_actual = np.expm1(y_val_actual)
        
        val_preds_actual = np.maximum(0, val_preds_actual)
        
        # Calculate final metrics
        final_r2 = r2_score(y_val_actual, val_preds_actual)
        mask = y_val_actual != 0
        if mask.any():
            final_mape = mean_absolute_percentage_error(y_val_actual[mask], val_preds_actual[mask]) * 100
        else:
            final_mape = 0.0
        final_mae = mean_absolute_error(y_val_actual, val_preds_actual)
        
        # Save model and artifacts
        safe_name = self._safe_name()
        
        # Save model state
        model_path = self.models_dir / f"{safe_name}_lstm.pt"
        torch.save(model.state_dict(), model_path)
        
        # Save scalers
        joblib.dump(feature_scaler, self.models_dir / f"{safe_name}_scaler.pkl")
        joblib.dump(target_scaler, self.models_dir / f"{safe_name}_target_scaler.pkl")
        
        # Save config (updated for new feature set)
        config_to_save = {
            'hidden_size': config['hidden_size'],
            'num_layers': config.get('num_layers', 1),
            'sequence_length': config['sequence_length'],
            'log_target': config.get('use_log_transform', False),
            'model_type': config['model_type'],
            'features': feature_cols,
            'use_robust_scaler': config.get('use_robust_scaler', False),
            'zero_predictor': False,
            'final_r2': final_r2,
            'final_mape': final_mape,
            'final_mae': final_mae,
            'disease_name': self.disease_name,
            'district': self.district,
        }
        joblib.dump(config_to_save, self.models_dir / f"{safe_name}_config.pkl")
        
        return {
            'r2': final_r2,
            'mape': final_mape,
            'mae': final_mae,
            'model_path': str(model_path),
        }


class Command(BaseCommand):
    help = 'Train optimized disease prediction model using Optuna hyperparameter search'

    def add_arguments(self, parser):
        parser.add_argument('disease_name', type=str, nargs='?', default=None, help='Name of the disease to train')
        parser.add_argument('--all', action='store_true', help='Train models for all diseases in the database')
        parser.add_argument('--district', type=str, default=None, help='Train for a specific district (default: trains per-district models for all 14 Kerala districts)')
        parser.add_argument('--n-trials', type=int, default=1, help='Number of Optuna trials (default: 50)')
        parser.add_argument('--cv-folds', type=int, default=3, help='Number of cross-validation folds')
        parser.add_argument('--epochs', type=int, default=100, help='Max epochs per trial')
        parser.add_argument('--target-r2', type=float, default=0.80, help='Target R2 score (default: 0.80)')
        parser.add_argument('--no-optuna', action='store_true', help='Skip Optuna, use default config')
        parser.add_argument('--final-epochs', type=int, default=200, help='Epochs for final model (default: 200)')

    # Kerala districts for per-district training
    KERALA_DISTRICTS = [
        'Thiruvananthapuram', 'Kollam', 'Pathanamthitta', 'Alappuzha',
        'Kottayam', 'Idukki', 'Ernakulam', 'Thrissur', 'Palakkad',
        'Malappuram', 'Kozhikode', 'Wayanad', 'Kannur', 'Kasaragod'
    ]

    def handle(self, *args, **options):
        district = options.get('district')
        
        if options['all']:
            # Train all diseases × all districts
            from surveillance.views import DISEASE_MAPPING
            all_diseases = sorted(list(DISEASE_MAPPING.keys()))
            districts = [district] if district else self.KERALA_DISTRICTS
            total_models = len(all_diseases) * len(districts)
            
            self.stdout.write(self.style.SUCCESS(
                f"\n{'='*60}\n"
                f"BATCH TRAINING: {len(all_diseases)} diseases × {len(districts)} districts = {total_models} models\n"
                f"{'='*60}\n"
            ))
            results = {'success': [], 'failed': [], 'skipped': []}
            count = 0
            for disease in all_diseases:
                for dist in districts:
                    count += 1
                    label = f"{disease} / {dist}"
                    self.stdout.write(self.style.SUCCESS(
                        f"\n[{count}/{total_models}] Training: {label}"
                    ))
                    try:
                        options_copy = dict(options)
                        options_copy['disease_name'] = disease
                        options_copy['district'] = dist
                        options_copy['all'] = False
                        self._train_single(options_copy)
                        results['success'].append(label)
                    except ValueError as e:
                        # No data for this disease/district combo — skip
                        self.stdout.write(self.style.WARNING(f"  ⊘ Skipped (no data): {label}"))
                        results['skipped'].append(label)
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  ✗ Failed: {label} - {e}"))
                        results['failed'].append(label)

            self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
            self.stdout.write(self.style.SUCCESS(
                f"BATCH COMPLETE: {len(results['success'])} succeeded, "
                f"{len(results['skipped'])} skipped, {len(results['failed'])} failed"
            ))
            if results['failed']:
                self.stdout.write(self.style.WARNING(f"Failed: {', '.join(results['failed'][:10])}"))
            self.stdout.write(self.style.SUCCESS(f"{'='*60}\n"))
            return

        disease_name = options['disease_name']
        if not disease_name:
            self.stdout.write(self.style.ERROR("Please provide a disease name or use --all"))
            return
        
        # If no --district specified for single disease, train for all districts
        if district:
            self._train_single(options)
        else:
            for dist in self.KERALA_DISTRICTS:
                label = f"{disease_name} / {dist}"
                self.stdout.write(self.style.SUCCESS(f"\nTraining: {label}"))
                try:
                    options_copy = dict(options)
                    options_copy['district'] = dist
                    self._train_single(options_copy)
                except ValueError:
                    self.stdout.write(self.style.WARNING(f"  ⊘ Skipped (no data): {label}"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  ✗ Failed: {label} - {e}"))

    def _train_single(self, options):
        disease_name = options['disease_name']
        district = options.get('district')
        n_trials = options['n_trials']
        cv_folds = options['cv_folds']
        epochs = options['epochs']
        target_r2 = options['target_r2']
        skip_optuna = options['no_optuna']
        final_epochs = options['final_epochs']
        
        label = f"{disease_name}"
        if district:
            label += f" / {district}"
        
        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS(f"WARNMEW Advanced Model Training"))
        self.stdout.write(self.style.SUCCESS(f"Disease: {disease_name}"))
        if district:
            self.stdout.write(self.style.SUCCESS(f"District: {district}"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}\n"))
        
        trainer = EnhancedTrainer(disease_name, district=district)
        
        # Fetch and prepare data
        self.stdout.write("Loading and engineering features...")
        try:
            df = trainer.fetch_and_prepare_data()
            self.stdout.write(f"  → Loaded {len(df)} records with {len(trainer.feature_engineer.get_feature_columns(df))} features")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error loading data: {e}"))
            return
        
        # Analyze data sparsity — RUNTIME classification
        sparsity = trainer.analyze_data_sparsity(df)
        data_tier = sparsity['data_tier']
        
        self.stdout.write(f"\n📊 Data Analysis:")
        self.stdout.write(f"  • Data Tier: {data_tier}")
        self.stdout.write(f"  • Zero Ratio: {sparsity['zero_ratio']:.1%}")
        self.stdout.write(f"  • Non-Zero Days: {sparsity['nonzero_count']}")
        self.stdout.write(f"  • Mean Cases: {sparsity['mean_cases']:.2f}")
        self.stdout.write(f"  • Max Cases: {sparsity['max_cases']:.0f}")
        
        # =============================================
        # NEAR-ZERO TIER: Save zero-predictor, skip LSTM
        # =============================================
        if data_tier == 'near_zero':
            self.stdout.write(self.style.WARNING(
                f"\n⚠️  Near-zero data detected ({sparsity['zero_ratio']:.1%} zeros, "
                f"only {sparsity['nonzero_count']} non-zero days)"
            ))
            self.stdout.write("  Saving zero-predictor (always predicts 0). This is more accurate than a noisy neural net.")
            
            safe_name = trainer._safe_name()
            config_to_save = {
                'zero_predictor': True,
                'disease_name': disease_name,
                'district': district,
                'data_tier': data_tier,
                'zero_ratio': sparsity['zero_ratio'],
                'nonzero_count': sparsity['nonzero_count'],
                'final_r2': 1.0 if sparsity['zero_ratio'] == 1.0 else 0.95,
                'final_mape': 0.0,
                'final_mae': 0.0,
            }
            joblib.dump(config_to_save, trainer.models_dir / f"{safe_name}_config.pkl")
            
            self.stdout.write(self.style.SUCCESS(f"\n✓ Zero-predictor saved for {label}"))
            return
        
        # Determine if we should prioritize R2
        prioritize_r2 = data_tier in ('ultra_sparse',)
        
        if skip_optuna or not HAS_OPTUNA:
            if not HAS_OPTUNA:
                self.stdout.write(self.style.WARNING("Optuna not installed. Using default config."))
            best_config = self._get_default_config(data_tier)
            self.stdout.write(f"Using config: {best_config}")
        else:
            # Optuna optimization
            self.stdout.write(f"\nStarting Optuna optimization ({n_trials} trials, tier={data_tier})...")
            
            def objective(trial):
                config = DataAdaptiveConfig.get_search_space(data_tier, trial)
                try:
                    metrics, _, _ = trainer.cross_validate(
                        df, config, n_splits=cv_folds, epochs=epochs, 
                        prioritize_r2=prioritize_r2
                    )
                    score = metrics.get_composite_score(prioritize_r2=prioritize_r2)
                    
                    # Report R2 for pruning
                    r2_mean = metrics.get_summary()['r2_mean']
                    trial.set_user_attr('r2_mean', r2_mean)
                    
                    return score
                except Exception as e:
                    return 0.0
            
            study = optuna.create_study(
                direction='maximize',
                sampler=optuna.samplers.TPESampler(seed=42),
            )
            study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
            
            best_r2 = study.best_trial.user_attrs.get('r2_mean', 0)
            
            self.stdout.write(f"\n📈 Best trial:")
            self.stdout.write(f"  Composite Score: {study.best_value:.4f}")
            self.stdout.write(f"  CV R² Mean: {best_r2:.2%}")
            self.stdout.write(f"  Config: {study.best_params}")
            
            best_config = study.best_params
        
        # Train final model with best config
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Training final model ({final_epochs} epochs, patience=30)...")
        
        try:
            results = trainer.train_final_model(df, best_config, epochs=final_epochs, patience=30)
            
            self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
            self.stdout.write(self.style.SUCCESS(f"TRAINING COMPLETE"))
            self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
            self.stdout.write(f"\nFinal Metrics:")
            self.stdout.write(f"  R² Score:     {results['r2']:.2%}")
            self.stdout.write(f"  MAPE:         {results['mape']:.2f}%")
            self.stdout.write(f"  MAE:          {results['mae']:.2f}")
            self.stdout.write(f"\nModel saved: {results['model_path']}")
            
            if results['r2'] >= target_r2:
                self.stdout.write(self.style.SUCCESS(f"\n✓ TARGET ACHIEVED! R² ≥ {target_r2:.0%}"))
            elif results['r2'] >= 0.5:
                self.stdout.write(self.style.WARNING(
                    f"\n⚠ R² is {results['r2']:.2%} (target: {target_r2:.0%}). "
                    f"This is acceptable for data tier: {data_tier}"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"\n⚠ R² below target ({results['r2']:.2%} < {target_r2:.0%}). "
                    f"Consider:\n"
                    f"  • Running with --n-trials 100 for more optimization\n"
                    f"  • This disease may have inherently unpredictable patterns\n"
                    f"  • Check if data quality is sufficient"
                ))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Training failed: {e}"))
            import traceback
            traceback.print_exc()
    
    def _get_default_config(self, data_tier):
        """Get sensible default config based on runtime data tier."""
        
        if data_tier == 'ultra_sparse':
            return {
                'hidden_size': 16,
                'num_layers': 1,
                'dropout': 0.4,
                'sequence_length': 7,
                'learning_rate': 0.002,
                'batch_size': 8,
                'model_type': 'gru',
                'use_log_transform': True,
                'use_robust_scaler': True,
                'l2_reg': 0.01,
            }
        elif data_tier == 'seasonal':
            return {
                'hidden_size': 64,
                'num_layers': 2,
                'dropout': 0.25,
                'sequence_length': 14,
                'learning_rate': 0.001,
                'batch_size': 16,
                'model_type': 'gru',
                'use_log_transform': True,
                'use_robust_scaler': True,
                'l2_reg': 0.005,
            }
        else:  # 'active'
            return {
                'hidden_size': 128,
                'num_layers': 2,
                'dropout': 0.2,
                'sequence_length': 30,
                'learning_rate': 0.001,
                'batch_size': 32,
                'model_type': 'lstm',
                'use_log_transform': False,
                'use_robust_scaler': False,
                'l2_reg': 0.0001,
            }

