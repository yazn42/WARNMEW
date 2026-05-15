"""
Django management command to bulk import disease data from the wide-format CSV file.

Usage:
    python manage.py ingest_data
    python manage.py ingest_data --file /path/to/warnmew_training_dataset.csv
"""

import pandas as pd
import numpy as np
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from surveillance.models import DailyDiseaseRecord

class Command(BaseCommand):
    help = 'Bulk import wide-format disease data from warnmew_training_dataset.csv'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Path to the warnmew_training_dataset.csv. Defaults to project root.'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Number of records to insert per batch (default: 1000)'
        )

    def handle(self, *args, **options):
        # Determine file path
        file_path = options['file']
        if file_path is None:
            # warnmew_backend/surveillance/management/commands/ingest_data.py
            # Go up 4 levels to reach project root
            base_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
            file_path = base_dir / 'warnmew_training_dataset.csv'
        else:
            file_path = Path(file_path)

        if not file_path.exists():
            raise CommandError(f"Dataset file does not exist: {file_path}")

        batch_size = options['batch_size']

        self.stdout.write(self.style.SUCCESS(f"\n{'='*60}"))
        self.stdout.write(self.style.SUCCESS("WARNMEW Data Ingestion (Wide Format)"))
        self.stdout.write(self.style.SUCCESS(f"{'='*60}"))
        self.stdout.write(f"Dataset: {file_path}")
        self.stdout.write(f"Batch size: {batch_size}")
        self.stdout.write(f"{'='*60}\n")

        self.stdout.write("Reading CSV with pandas...")
        try:
            df = pd.read_csv(file_path)
            # Replace NaNs with None for Django ORM
            df = df.replace({np.nan: None})
        except Exception as e:
            raise CommandError(f"Error reading CSV: {str(e)}")

        total_rows = len(df)
        self.stdout.write(f"Found {total_rows} rows. Beginning ingestion...")

        records_to_create = []
        total_created = 0
        existing_count = DailyDiseaseRecord.objects.count()

        with transaction.atomic():
            for index, row in df.iterrows():
                try:
                    record = DailyDiseaseRecord(
                        report_date=pd.to_datetime(row['report_date']).date(),
                        district=str(row['district']).strip(),
                        fever_op_cases=int(row.get('fever_op_cases', 0) or 0),
                        fever_ip_cases=int(row.get('fever_ip_cases', 0) or 0),
                        chikungunya_suspected=int(row.get('chikungunya_suspected', 0) or 0),
                        chikungunya_confirmed=int(row.get('chikungunya_confirmed', 0) or 0),
                        chikungunya_deaths=int(row.get('chikungunya_deaths', 0) or 0),
                        dengue_suspected=int(row.get('dengue_suspected', 0) or 0),
                        dengue_confirmed=int(row.get('dengue_confirmed', 0) or 0),
                        dengue_deaths=int(row.get('dengue_deaths', 0) or 0),
                        lepto_suspected=int(row.get('lepto_suspected', 0) or 0),
                        lepto_confirmed=int(row.get('lepto_confirmed', 0) or 0),
                        lepto_deaths=int(row.get('lepto_deaths', 0) or 0),
                        add_cases=int(row.get('add_cases', 0) or 0),
                        chickenpox_cases=int(row.get('chickenpox_cases', 0) or 0),
                        hepatitis_a_cases=int(row.get('hepatitis_a_cases', 0) or 0),
                        hepatitis_b_cases=int(row.get('hepatitis_b_cases', 0) or 0),
                        cholera_suspected=int(row.get('cholera_suspected', 0) or 0),
                        cholera_confirmed=int(row.get('cholera_confirmed', 0) or 0),
                        je_suspected=int(row.get('je_suspected', 0) or 0),
                        je_confirmed=int(row.get('je_confirmed', 0) or 0),
                        malaria_imported=int(row.get('malaria_imported', 0) or 0),
                        malaria_indigenous=int(row.get('malaria_indigenous', 0) or 0),
                        typhoid_cases=int(row.get('typhoid_cases', 0) or 0),
                        h1n1_cases=int(row.get('h1n1_cases', 0) or 0),
                        measles_cases=int(row.get('measles_cases', 0) or 0),
                        scrub_typhus_cases=int(row.get('scrub_typhus_cases', 0) or 0),
                        diphtheria_cases=int(row.get('diphtheria_cases', 0) or 0),
                        amebic_meningoencephalitis_cases=int(row.get('amebic_meningoencephalitis_cases', 0) or 0),
                        nipah_cases=int(row.get('nipah_cases', 0) or 0),
                        shigella_cases=int(row.get('shigella_cases', 0) or 0),
                        west_nile_fever_cases=int(row.get('west_nile_fever_cases', 0) or 0),
                        monkeypox_cases=int(row.get('monkeypox_cases', 0) or 0),
                        covid19_cases=int(row.get('covid19_cases', 0) or 0),
                        covid19_deaths=int(row.get('covid19_deaths', 0) or 0),
                        rabies_cases=int(row.get('rabies_cases', 0) or 0),
                        influenza_cases=int(row.get('influenza_cases', 0) or 0),
                        climate_rainfall_mm=self.parse_float(row.get('climate_rainfall_mm')),
                        climate_avg_temp_c=self.parse_float(row.get('climate_avg_temp_c')),
                        climate_humidity_percent=self.parse_float(row.get('climate_humidity_percent')),
                        social_search_index_dengue=self.parse_float(row.get('social_search_index_dengue')),
                        social_search_index_fever=self.parse_float(row.get('social_search_index_fever'))
                    )
                    records_to_create.append(record)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Skipping row {index}: {e}"))
                    continue

                if len(records_to_create) >= batch_size:
                    DailyDiseaseRecord.objects.bulk_create(records_to_create, ignore_conflicts=True)
                    records_to_create = []
                    
                    if index % 5000 == 0:
                        self.stdout.write(f"Processed {index}/{total_rows} rows...")

            # Insert remainder
            if records_to_create:
                DailyDiseaseRecord.objects.bulk_create(records_to_create, ignore_conflicts=True)
                
        new_count = DailyDiseaseRecord.objects.count()
        total_created = new_count - existing_count

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS("INGESTION COMPLETE"))
        self.stdout.write(f"{'='*60}")
        self.stdout.write(f"Total rows processed: {total_rows}")
        self.stdout.write(f"New records inserted: {total_created}")
        self.stdout.write(f"{'='*60}\n")

    def parse_float(self, val):
        if pd.isna(val) or val is None:
            return None
        return float(val)
