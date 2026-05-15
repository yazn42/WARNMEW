"""
Management command to generate statistical alerts based on forecast anomalies.

Detects epidemics by comparing AI forecasts against a moving baseline
(30-day historical mean + standard deviations).

Usage:
    python manage.py generate_alerts
    python manage.py generate_alerts --disease Dengue
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.utils import timezone
from surveillance.models import DailyDiseaseRecord, Alert
from surveillance.views import DISEASE_MAPPING
from ml_engine.forecaster import DiseaseForecaster
from datetime import datetime, timedelta
import numpy as np


class Command(BaseCommand):
    help = 'Generate alerts using statistical baseline deviation'

    def add_arguments(self, parser):
        parser.add_argument('--disease', type=str, help='Generate alerts for a specific disease only')
        parser.add_argument('--dry-run', action='store_true', help='Show alerts without saving')

    def _get_historical_baseline(self, disease_name, district):
        """
        Calculate the 30-day mean and standard deviation for a specific disease/district.
        """
        mapping_key = None
        for k in DISEASE_MAPPING:
            if k.lower() == disease_name.lower():
                mapping_key = k
                break
                
        if not mapping_key:
            return None, None
            
        confirmed_col = DISEASE_MAPPING[mapping_key].get('confirmed')
        if not confirmed_col:
            return None, None

        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        
        records = (
            DailyDiseaseRecord.objects
            .filter(district__iexact=district, report_date__gte=thirty_days_ago)
            .values('report_date')
            .annotate(cases=Sum(confirmed_col))
            .order_by('report_date')
        )
        
        cases = [r['cases'] or 0 for r in records]
        
        if len(cases) < 7:  # Need at least a week of data for a meaningful baseline
            return None, None
            
        mean = np.mean(cases)
        std = np.std(cases)
        
        # Prevent 0 std dev from causing division by zero later
        if std == 0:
            std = max(1, mean * 0.1) 
            
        return mean, std

    def handle(self, *args, **options):
        target_disease = options.get('disease')
        dry_run = options.get('dry_run', False)
        
        forecaster = DiseaseForecaster()
        
        if target_disease:
            diseases = [target_disease]
        else:
            diseases = list(DISEASE_MAPPING.keys())

        KERALA_DISTRICTS = [
            'Thiruvananthapuram', 'Kollam', 'Pathanamthitta', 'Alappuzha',
            'Kottayam', 'Idukki', 'Ernakulam', 'Thrissur', 'Palakkad',
            'Malappuram', 'Kozhikode', 'Wayanad', 'Kannur', 'Kasaragod'
        ]

        self.stdout.write(f"Analyzing {len(diseases)} diseases for statistical anomalies...")
        
        # Clear old alerts before generating fresh ones
        if not dry_run:
            old_count = Alert.objects.all().count()
            Alert.objects.all().delete()
            self.stdout.write(f"Cleared {old_count} old alert(s).")
        
        alerts_created = 0

        for disease in diseases:
            for district in KERALA_DISTRICTS:
                # 1. Calculate historical baseline
                mean, std = self._get_historical_baseline(disease, district)
                if mean is None or std is None:
                    continue
                    
                # Epidemic thresholds (Z-scores)
                # Medium: > Mean + 1.5 StdDev
                # High: > Mean + 2.5 StdDev 
                # Critical: > Mean + 3.5 StdDev AND at least double the mean
                t_medium = mean + (1.5 * std)
                t_high = mean + (2.5 * std)
                t_critical = max(mean + (3.5 * std), mean * 2)

                # Ignore pure noise (e.g. going from 0 to 2 cases shouldn't trigger an alert)
                if t_medium < 5:
                    t_medium = 5
                if t_high < 10:
                    t_high = 10
                if t_critical < 15:
                    t_critical = 15

                try:
                    forecast = forecaster.predict_next_7_days(disease, district=district, return_json=True)
                except Exception as e:
                    continue

                if not forecast or 'predictions' not in forecast:
                    continue

                for day_forecast in forecast['predictions']:
                    predicted = day_forecast.get('predicted_cases', 0)
                    date_str = day_forecast.get('date', '')

                    # Determine severity based on statistical deviation
                    severity = None
                    threshold_val = 0
                    
                    if predicted >= t_critical:
                        severity = 'critical'
                        threshold_val = t_critical
                    elif predicted >= t_high:
                        severity = 'high'
                        threshold_val = t_high
                    elif predicted >= t_medium:
                        severity = 'medium'
                        threshold_val = t_medium

                    if severity:
                        title = f"Epidemic Alert: {disease} spike in {district} ({severity.upper()})"
                        
                        # Calculate percentage increase over baseline
                        percent_inc = int(((predicted - mean) / mean) * 100) if mean > 0 else 100
                        
                        message = (
                            f"AI forecast predicts {int(predicted)} cases on {date_str}. "
                            f"This is a {percent_inc}% increase over the recent 30-day baseline "
                            f"(avg: {int(mean)} cases/day). Statistical anomaly detected, "
                            f"indicating a potential outbreak."
                        )

                        if dry_run:
                            self.stdout.write(self.style.WARNING(f"  [DRY RUN] {title} | Pred: {int(predicted)} | Mean: {int(mean)}"))
                        else:
                            Alert.objects.create(
                                disease_name=disease,
                                district=district,
                                severity=severity,
                                title=title,
                                message=message,
                                forecast_value=predicted,
                                threshold_value=threshold_val
                            )
                            alerts_created += 1
                            self.stdout.write(self.style.SUCCESS(f"  Created: {title}"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. {alerts_created} statistical alert(s) created."))
