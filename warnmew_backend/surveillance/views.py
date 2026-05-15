from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Avg
from .models import DailyDiseaseRecord, Alert
from ml_engine.forecaster import DiseaseForecaster
import json
import joblib
from pathlib import Path


DISEASE_MAPPING = {
    "Fever": {"confirmed": "fever_op_cases"},
    "Chikungunya": {"suspected": "chikungunya_suspected", "confirmed": "chikungunya_confirmed", "deaths": "chikungunya_deaths"},
    "Dengue": {"suspected": "dengue_suspected", "confirmed": "dengue_confirmed", "deaths": "dengue_deaths"},
    "Lepto": {"suspected": "lepto_suspected", "confirmed": "lepto_confirmed", "deaths": "lepto_deaths"},
    "Malaria": {"suspected": "malaria_imported", "confirmed": "malaria_indigenous", "deaths": None},
    "Acute Diarrhoeal Disease": {"confirmed": "add_cases"},
    "Chickenpox": {"confirmed": "chickenpox_cases"},
    "Hepatitis A": {"confirmed": "hepatitis_a_cases"},
    "Hepatitis B": {"confirmed": "hepatitis_b_cases"},
    "Cholera": {"suspected": "cholera_suspected", "confirmed": "cholera_confirmed"},
    "Japanese Encephalitis": {"suspected": "je_suspected", "confirmed": "je_confirmed"},
    "Typhoid": {"confirmed": "typhoid_cases"},
    "H1N1": {"confirmed": "h1n1_cases"},
    "Measles": {"confirmed": "measles_cases"},
    "Scrub Typhus": {"confirmed": "scrub_typhus_cases"},
    "Diphtheria": {"confirmed": "diphtheria_cases"},
    "Amebic Meningoencephalitis": {"confirmed": "amebic_meningoencephalitis_cases"},
    "Nipah": {"confirmed": "nipah_cases"},
    "Shigella": {"confirmed": "shigella_cases"},
    "West Nile Fever": {"confirmed": "west_nile_fever_cases"},
    "Monkeypox": {"confirmed": "monkeypox_cases"},
    "Covid-19": {"confirmed": "covid19_cases", "deaths": "covid19_deaths"},
    "Rabies": {"confirmed": "rabies_cases"},
    "Influenza": {"confirmed": "influenza_cases"},
}

@api_view(['GET'])
@permission_classes([AllowAny])
def get_diseases(request):
    """
    Return list of all available diseases.
    """
    return Response(list(DISEASE_MAPPING.keys()))


@api_view(['GET'])
@permission_classes([AllowAny])
def get_history(request, disease_name):
    """
    Return historical data aggregated at state level (sum of all districts), unpivoted dynamically.
    """
    mapping_key = None
    for k in DISEASE_MAPPING:
        if k.lower() == disease_name.lower():
            mapping_key = k
            break
            
    if not mapping_key:
        return Response(
            {"error": f"No data found for disease: {disease_name}"},
            status=status.HTTP_404_NOT_FOUND
        )

    qs = DailyDiseaseRecord.objects.all()

    district = request.query_params.get('district')
    if district and district != 'all':
        qs = qs.filter(district__iexact=district)

    date_from = request.query_params.get('date_from')
    date_to = request.query_params.get('date_to')
    if date_from:
        qs = qs.filter(report_date__gte=date_from)
    if date_to:
        qs = qs.filter(report_date__lte=date_to)

    mapping = DISEASE_MAPPING[mapping_key]
    
    annotate_kwargs = {
        'temp_mean': Avg('climate_avg_temp_c'),
        'rain_sum': Avg('climate_rainfall_mm'),
        'humidity_mean': Avg('climate_humidity_percent'),
        'search_dengue': Avg('social_search_index_dengue'),
        'search_fever': Avg('social_search_index_fever'),
    }
    
    if mapping.get('confirmed'):
        annotate_kwargs['confirmed_case_count'] = Sum(mapping['confirmed'])
    if mapping.get('suspected'):
        annotate_kwargs['suspected_case_count'] = Sum(mapping['suspected'])
    if mapping.get('deaths'):
        annotate_kwargs['confirmed_death_count'] = Sum(mapping['deaths'])

    records = qs.values('report_date').annotate(**annotate_kwargs).order_by('report_date')
    
    result = []
    for r in records:
        # Combine search indices into a single value (average of available indices)
        search_vals = [v for v in [r.get('search_dengue'), r.get('search_fever')] if v is not None]
        search_interest = round(sum(search_vals) / len(search_vals), 1) if search_vals else 0

        item = {
            'date': r['report_date'],
            'temp_mean': r.get('temp_mean'),
            'rain_sum': r.get('rain_sum'),
            'humidity_mean': r.get('humidity_mean'),
            'search_interest': search_interest,
            'confirmed_case_count': r.get('confirmed_case_count', 0) if mapping.get('confirmed') else 0,
            'suspected_case_count': r.get('suspected_case_count', 0) if mapping.get('suspected') else 0,
            'confirmed_death_count': r.get('confirmed_death_count', 0) if mapping.get('deaths') else 0,
            'suspected_death_count': 0
        }
        result.append(item)

    return Response(result)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_map_data(request, disease_name):
    """
    Return district-wise data for a specific date (or latest available).
    """
    mapping_key = None
    for k in DISEASE_MAPPING:
        if k.lower() == disease_name.lower():
            mapping_key = k
            break
            
    if not mapping_key:
        return Response([])

    date_str = request.query_params.get('date')
    qs = DailyDiseaseRecord.objects.all()

    if date_str:
        qs = qs.filter(report_date=date_str)
    else:
        latest = qs.order_by('-report_date').first()
        if not latest:
            return Response([])
        qs = qs.filter(report_date=latest.report_date)

    mapping = DISEASE_MAPPING[mapping_key]
    
    values_list = ['district', 'report_date']
    if mapping.get('confirmed'):
        values_list.append(mapping['confirmed'])
    if mapping.get('deaths'):
        values_list.append(mapping['deaths'])
        
    qs_data = qs.values(*values_list)
    
    result = []
    for r in qs_data:
        item = {
            'district': r['district'],
            'date': r['report_date'],
            'confirmed_case_count': r.get(mapping.get('confirmed'), 0) if mapping.get('confirmed') else 0,
            'confirmed_death_count': r.get(mapping.get('deaths'), 0) if mapping.get('deaths') else 0,
        }
        result.append(item)
        
    return Response(result)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_forecast(request, disease_name):
    """
    Trigger forecast for the next 7 days.
    Optional query param: ?district=Ernakulam for per-district forecast.
    Returns predictions plus model_confidence (R² score).
    """
    district = request.query_params.get('district', None)
    forecaster = DiseaseForecaster()
    try:
        forecast = forecaster.predict_next_7_days(disease_name, district=district, return_json=True)
        
        # Add model confidence from saved config
        import joblib
        safe_name = forecaster._safe_name(disease_name, district)
        config_path = forecaster.models_dir / f"{safe_name}_config.pkl"
        if config_path.exists():
            config = joblib.load(config_path)
            forecast['model_confidence'] = round(config.get('final_r2', 0) * 100, 1)
            forecast['model_type_label'] = 'Zero-Predictor' if config.get('zero_predictor') else config.get('model_type', 'lstm').upper()
        else:
            forecast['model_confidence'] = None
            forecast['model_type_label'] = 'Unknown'
        
        return Response(forecast)
    except FileNotFoundError:
        label = disease_name
        if district:
            label += f" / {district}"
        return Response(
            {"error": f"Model not found for {label}. Please train the model first."}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        return Response(
            {"error": str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# --- Alert Endpoints ---

@api_view(['GET'])
@permission_classes([AllowAny])
def get_alerts(request):
    """
    Return all alerts, optionally filtered by disease or severity.
    Query params: ?disease=Dengue&severity=high&unread_only=true
    """
    qs = Alert.objects.all()

    disease = request.query_params.get('disease')
    if disease:
        qs = qs.filter(disease_name__iexact=disease)

    severity = request.query_params.get('severity')
    if severity:
        qs = qs.filter(severity=severity)

    unread_only = request.query_params.get('unread_only')
    if unread_only == 'true':
        qs = qs.filter(is_read=False)

    alerts = qs.order_by('-created_at')[:50].values(
        'id', 'disease_name', 'district', 'severity', 'title',
        'message', 'forecast_value', 'threshold_value', 'is_read', 'created_at'
    )
    return Response(list(alerts))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_alert_read(request, alert_id):
    """
    Mark a specific alert as read.
    """
    try:
        alert = Alert.objects.get(id=alert_id)
        alert.is_read = True
        alert.save()
        return Response({"message": "Alert marked as read."})
    except Alert.DoesNotExist:
        return Response(
            {"error": "Alert not found."},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_alert_summary(request):
    """
    Return alert summary for the notification badge.
    """
    total = Alert.objects.count()
    unread = Alert.objects.filter(is_read=False).count()
    critical = Alert.objects.filter(severity='critical', is_read=False).count()
    high = Alert.objects.filter(severity='high', is_read=False).count()

    return Response({
        "total": total,
        "unread": unread,
        "critical": critical,
        "high": high
    })


# --- Model Comparison Endpoint ---

@api_view(['GET'])
@permission_classes([AllowAny])
def get_model_comparison(request, disease_name):
    """
    Return comparison metrics for all trained model types for a disease.
    Reads from saved model_comparison.json.
    """
    models_dir = Path(__file__).resolve().parent.parent / 'models'
    comparison_path = models_dir / 'model_comparison.json'

    if comparison_path.exists():
        with open(comparison_path, 'r') as f:
            all_results = json.load(f)
        
        # Try exact match first, then case-insensitive
        if disease_name in all_results:
            return Response(all_results[disease_name])
        
        for key, value in all_results.items():
            if key.lower() == disease_name.lower():
                return Response(value)

    # No saved comparison — try to load individual model metrics
    results = []

    # Check LSTM
    lstm_metrics_path = models_dir / f'{disease_name.replace(" ", "_").lower()}_metadata.json'
    if lstm_metrics_path.exists():
        with open(lstm_metrics_path, 'r') as f:
            meta = json.load(f)
        results.append({
            'model': 'LSTM',
            'r2_score': meta.get('best_r2', 0),
        })

    # Check SARIMA
    sarima_path = models_dir / 'sarima' / f'{disease_name.replace(" ", "_").lower()}_metrics.pkl'
    if sarima_path.exists():
        metrics = joblib.load(sarima_path)
        results.append({
            'model': 'SARIMA',
            'r2_score': metrics.get('r2_score', 0),
            'mae': metrics.get('mae', 0),
        })

    # Check baselines
    baselines_dir = models_dir / 'baselines'
    if baselines_dir.exists():
        for mpath in baselines_dir.glob(f'{disease_name.replace(" ", "_").lower()}_*_metrics.pkl'):
            metrics = joblib.load(mpath)
            results.append({
                'model': metrics.get('model', 'Unknown'),
                'r2_score': metrics.get('r2_score', 0),
                'mae': metrics.get('mae', 0),
            })

    if not results:
        return Response(
            {"error": f"No model comparison data found for {disease_name}. Run: python manage.py compare_models --disease '{disease_name}'"},
            status=status.HTTP_404_NOT_FOUND
        )

    # Sort by R² descending
    results.sort(key=lambda x: x.get('r2_score', 0), reverse=True)
    return Response(results)
