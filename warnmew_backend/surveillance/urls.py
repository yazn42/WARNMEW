from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from . import auth_views

urlpatterns = [
    # Auth endpoints
    path('auth/register/', auth_views.register, name='register'),
    path('auth/login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/profile/', auth_views.user_profile, name='user_profile'),

    # Data endpoints
    path('diseases/', views.get_diseases, name='get_diseases'),
    path('districts/', auth_views.get_districts, name='get_districts'),
    path('history/<str:disease_name>/', views.get_history, name='get_history'),
    path('map/<str:disease_name>/', views.get_map_data, name='get_map_data'),
    path('forecast/<str:disease_name>/', views.get_forecast, name='get_forecast'),

    # Alert endpoints
    path('alerts/', views.get_alerts, name='get_alerts'),
    path('alerts/<int:alert_id>/read/', views.mark_alert_read, name='mark_alert_read'),
    path('alerts/summary/', views.get_alert_summary, name='alert_summary'),

    # Model comparison
    path('models/compare/<str:disease_name>/', views.get_model_comparison, name='model_comparison'),
]
