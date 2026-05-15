"""
Advanced Feature Engineering for WARNMEW Disease Prediction Models.

This module provides enhanced feature extraction for time-series disease data,
designed to maximize prediction accuracy through:
- Rolling statistics (mean, std, max, min)
- Trend indicators (growth rates, momentum)
- Seasonality features (day of week, week of year, quarter)
- Outbreak detection flags
- Feature interactions
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional


class DiseaseFeatureEngineer:
    """
    Feature engineering class for disease prediction models.
    
    Extracts advanced features from raw disease surveillance data to improve
    model accuracy beyond basic lag features.
    """
    
    # Rolling window sizes
    ROLLING_WINDOWS = [3, 7, 14, 30]
    
    # Target column
    TARGET_COLUMN = 'confirmed_case_count'
    
    def __init__(self, include_interactions: bool = True, include_outbreak_flags: bool = True):
        """
        Initialize the feature engineer.
        
        Args:
            include_interactions: Whether to create feature interaction terms
            include_outbreak_flags: Whether to create outbreak detection flags
        """
        self.include_interactions = include_interactions
        self.include_outbreak_flags = include_outbreak_flags
        self._feature_names: List[str] = []
        
    def create_enhanced_features(self, df: pd.DataFrame, target_col: str = None) -> pd.DataFrame:
        """
        Create comprehensive feature set from raw disease data.
        
        Args:
            df: DataFrame with columns: date, confirmed_case_count, temp_mean, 
                rain_sum, humidity_mean, search_interest
            target_col: Target column name (default: confirmed_case_count)
                
        Returns:
            DataFrame with all engineered features
        """
        if target_col is None:
            target_col = self.TARGET_COLUMN
            
        df = df.copy()
        
        # Ensure date is datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
        
        # Fill NaNs in base columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].fillna(0)
        
        # 1. TEMPORAL FEATURES
        df = self._add_temporal_features(df)
        
        # 2. LAG FEATURES (1-14 days)
        df = self._add_lag_features(df, target_col, max_lag=14)
        
        # 3. ROLLING STATISTICS
        df = self._add_rolling_features(df, target_col)
        
        # 4. TREND FEATURES
        df = self._add_trend_features(df, target_col)
        
        # 5. CLIMATE FEATURES (if available)
        if 'temp_mean' in df.columns or 'rain_sum' in df.columns:
            df = self._add_climate_features(df)
        
        # 6. OUTBREAK FLAGS
        if self.include_outbreak_flags:
            df = self._add_outbreak_flags(df, target_col)
        
        # 7. FEATURE INTERACTIONS
        if self.include_interactions:
            df = self._add_interactions(df, target_col)
        
        # Drop rows with NaN from rolling/lag operations
        df = df.dropna().reset_index(drop=True)
        
        return df
    
    def _add_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add date-based temporal features."""
        if 'date' not in df.columns:
            return df
            
        date = df['date']
        
        # Day of week (0-6)
        df['day_of_week'] = date.dt.dayofweek
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        
        # Week of year (1-52)
        df['week_of_year'] = date.dt.isocalendar().week.astype(int)
        
        # Month and Quarter
        df['month'] = date.dt.month
        df['quarter'] = date.dt.quarter
        
        # Cyclic encoding for month (better than raw month number)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
        
        # Cyclic encoding for day of week
        df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        
        # Cyclic encoding for week of year
        df['week_sin'] = np.sin(2 * np.pi * df['week_of_year'] / 52)
        df['week_cos'] = np.cos(2 * np.pi * df['week_of_year'] / 52)
        
        # Year (for trend capture)
        df['year'] = date.dt.year
        df['days_since_start'] = (date - date.min()).dt.days
        
        return df
    
    def _add_lag_features(self, df: pd.DataFrame, target_col: str, max_lag: int = 14) -> pd.DataFrame:
        """Add lagged target features."""
        for lag in range(1, max_lag + 1):
            df[f'cases_lag_{lag}d'] = df[target_col].shift(lag)
        return df
    
    def _add_rolling_features(self, df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        """Add rolling window statistics."""
        for window in self.ROLLING_WINDOWS:
            # Rolling mean
            df[f'cases_rolling_mean_{window}d'] = df[target_col].rolling(
                window=window, min_periods=1
            ).mean()
            
            # Rolling standard deviation
            df[f'cases_rolling_std_{window}d'] = df[target_col].rolling(
                window=window, min_periods=1
            ).std().fillna(0)
            
            # Rolling max
            df[f'cases_rolling_max_{window}d'] = df[target_col].rolling(
                window=window, min_periods=1
            ).max()
            
            # Rolling min
            df[f'cases_rolling_min_{window}d'] = df[target_col].rolling(
                window=window, min_periods=1
            ).min()
            
            # Rolling sum
            df[f'cases_rolling_sum_{window}d'] = df[target_col].rolling(
                window=window, min_periods=1
            ).sum()
            
        # Exponential weighted moving average
        df['cases_ewma_7d'] = df[target_col].ewm(span=7, adjust=False).mean()
        df['cases_ewma_14d'] = df[target_col].ewm(span=14, adjust=False).mean()
        
        return df
    
    def _add_trend_features(self, df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        """Add trend and momentum features."""
        # Day-over-day change
        df['cases_diff_1d'] = df[target_col].diff(1).fillna(0)
        
        # Week-over-week change
        df['cases_diff_7d'] = df[target_col].diff(7).fillna(0)
        
        # Month-over-month change (approximated as 30 days)
        df['cases_diff_30d'] = df[target_col].diff(30).fillna(0)
        
        # Percentage change (with protection against division by zero)
        df['cases_pct_change_1d'] = df[target_col].pct_change(1).replace([np.inf, -np.inf], 0).fillna(0)
        df['cases_pct_change_7d'] = df[target_col].pct_change(7).replace([np.inf, -np.inf], 0).fillna(0)
        
        # Momentum (7-day vs 14-day average)
        rolling_7 = df[target_col].rolling(7, min_periods=1).mean()
        rolling_14 = df[target_col].rolling(14, min_periods=1).mean()
        df['cases_momentum'] = (rolling_7 - rolling_14).fillna(0)
        
        # Acceleration (change in momentum)
        df['cases_acceleration'] = df['cases_momentum'].diff(1).fillna(0)
        
        # Trend direction (1 = increasing, 0 = stable, -1 = decreasing)
        df['trend_direction'] = np.sign(df['cases_diff_7d'])
        
        return df
    
    def _add_climate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add climate-based features and lagged climate data."""
        climate_cols = ['temp_mean', 'rain_sum', 'humidity_mean']
        
        for col in climate_cols:
            if col not in df.columns:
                continue
                
            # Lagged climate features (diseases often respond to climate with delay)
            for lag in [7, 14, 21]:
                df[f'{col}_lag_{lag}d'] = df[col].shift(lag)
            
            # Rolling climate averages
            df[f'{col}_rolling_7d'] = df[col].rolling(7, min_periods=1).mean()
            df[f'{col}_rolling_14d'] = df[col].rolling(14, min_periods=1).mean()
        
        # Temperature anomaly (deviation from 30-day rolling mean)
        if 'temp_mean' in df.columns:
            temp_baseline = df['temp_mean'].rolling(30, min_periods=1).mean()
            df['temp_anomaly'] = df['temp_mean'] - temp_baseline
        
        # High rainfall indicator (for vector-borne diseases)
        if 'rain_sum' in df.columns:
            rain_90th = df['rain_sum'].quantile(0.9)
            df['high_rainfall'] = (df['rain_sum'] > rain_90th).astype(int)
        
        return df
    
    def _add_outbreak_flags(self, df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        """Add outbreak detection flags based on statistical thresholds."""
        # Calculate baseline statistics
        rolling_mean_30 = df[target_col].rolling(30, min_periods=1).mean()
        rolling_std_30 = df[target_col].rolling(30, min_periods=1).std().fillna(1)
        
        # Z-score relative to recent history
        df['cases_zscore'] = ((df[target_col] - rolling_mean_30) / rolling_std_30.replace(0, 1)).fillna(0)
        
        # Outbreak flag: cases > 2 standard deviations above mean
        df['outbreak_flag_2sigma'] = (df['cases_zscore'] > 2).astype(int)
        
        # Severe outbreak: cases > 3 standard deviations
        df['outbreak_flag_3sigma'] = (df['cases_zscore'] > 3).astype(int)
        
        # Consecutive outbreak days
        df['outbreak_consecutive'] = df['outbreak_flag_2sigma'].groupby(
            (df['outbreak_flag_2sigma'] != df['outbreak_flag_2sigma'].shift()).cumsum()
        ).cumsum()
        
        # Days since last outbreak
        outbreak_indices = df[df['outbreak_flag_2sigma'] == 1].index.tolist()
        df['days_since_outbreak'] = 0
        last_outbreak_idx = -1000
        for idx in df.index:
            if idx in outbreak_indices:
                last_outbreak_idx = idx
                df.loc[idx, 'days_since_outbreak'] = 0
            else:
                df.loc[idx, 'days_since_outbreak'] = idx - last_outbreak_idx
        
        return df
    
    def _add_interactions(self, df: pd.DataFrame, target_col: str) -> pd.DataFrame:
        """Add feature interaction terms."""
        # Cases × Climate interactions
        if 'temp_mean' in df.columns:
            df['cases_x_temp'] = df['cases_lag_1d'] * df['temp_mean']
        
        if 'rain_sum' in df.columns:
            df['cases_x_rain'] = df['cases_lag_1d'] * df['rain_sum']
            
        if 'humidity_mean' in df.columns:
            df['cases_x_humidity'] = df['cases_lag_1d'] * df['humidity_mean']
        
        # Climate × Climate interactions
        if 'temp_mean' in df.columns and 'humidity_mean' in df.columns:
            df['temp_x_humidity'] = df['temp_mean'] * df['humidity_mean']
        
        if 'temp_mean' in df.columns and 'rain_sum' in df.columns:
            df['temp_x_rain'] = df['temp_mean'] * df['rain_sum']
        
        # Seasonality × Cases
        if 'month_sin' in df.columns:
            df['cases_x_season'] = df['cases_lag_7d'] * df['month_sin']
        
        return df
    
    def get_feature_columns(self, df: pd.DataFrame, exclude_target: bool = True) -> List[str]:
        """
        Get list of feature column names (excludes date, target, and metadata).
        
        Args:
            df: DataFrame with all features
            exclude_target: Whether to exclude target column
            
        Returns:
            List of feature column names suitable for model training
        """
        exclude_cols = {'date', 'created_at', 'updated_at', 'id', 'disease_name'}
        if exclude_target:
            exclude_cols.add(self.TARGET_COLUMN)
            exclude_cols.add('suspected_case_count')
            exclude_cols.add('suspected_death_count')
            exclude_cols.add('confirmed_death_count')
        
        feature_cols = [col for col in df.columns if col not in exclude_cols 
                       and df[col].dtype in [np.float64, np.int64, np.int32, np.float32]]
        
        return feature_cols


def create_enhanced_features(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """
    Convenience function to create enhanced features.
    
    Args:
        df: Raw disease data DataFrame
        **kwargs: Arguments to pass to DiseaseFeatureEngineer
        
    Returns:
        DataFrame with enhanced features
    """
    engineer = DiseaseFeatureEngineer(**kwargs)
    return engineer.create_enhanced_features(df)


def get_feature_names(df: pd.DataFrame, engineer: DiseaseFeatureEngineer = None) -> List[str]:
    """
    Get feature column names from a processed DataFrame.
    
    Args:
        df: Processed DataFrame with features
        engineer: Optional feature engineer instance
        
    Returns:
        List of feature column names
    """
    if engineer is None:
        engineer = DiseaseFeatureEngineer()
    return engineer.get_feature_columns(df)
