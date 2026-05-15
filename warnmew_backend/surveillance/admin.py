from django.contrib import admin
from .models import DailyDiseaseRecord, UserProfile, Alert


@admin.register(DailyDiseaseRecord)
class DailyDiseaseRecordAdmin(admin.ModelAdmin):
    list_display = ('district', 'report_date', 'fever_op_cases', 'dengue_confirmed', 'covid19_cases')
    list_filter = ('district', 'report_date')
    search_fields = ('district',)
    ordering = ('-report_date',)
    
    fieldsets = (
        ('Location & Date', {
            'fields': ('district', 'report_date')
        }),
        ('Core Diseases', {
            'fields': (
                'fever_op_cases', 'fever_ip_cases', 'dengue_suspected', 'dengue_confirmed', 'dengue_deaths',
                'chikungunya_suspected', 'chikungunya_confirmed', 'chikungunya_deaths',
                'lepto_suspected', 'lepto_confirmed', 'lepto_deaths'
            )
        }),
        ('Other Diseases', {
            'fields': (
                'add_cases', 'chickenpox_cases', 'hepatitis_a_cases', 'hepatitis_b_cases',
                'cholera_suspected', 'cholera_confirmed', 'je_suspected', 'je_confirmed',
                'malaria_imported', 'malaria_indigenous', 'typhoid_cases', 'h1n1_cases',
                'measles_cases', 'scrub_typhus_cases', 'diphtheria_cases',
                'amebic_meningoencephalitis_cases', 'nipah_cases', 'shigella_cases',
                'west_nile_fever_cases', 'monkeypox_cases', 'covid19_cases', 'covid19_deaths',
                'rabies_cases', 'influenza_cases'
            ),
            'classes': ('collapse',)
        }),
        ('Environmental & Social', {
            'fields': (
                'climate_rainfall_mm', 'climate_avg_temp_c', 'climate_humidity_percent',
                'social_search_index_dengue', 'social_search_index_fever'
            ),
            'classes': ('collapse',)
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'organization', 'created_at')
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'organization')


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('disease_name', 'district', 'severity', 'title', 'is_read', 'created_at')
    list_filter = ('severity', 'is_read', 'disease_name')
    search_fields = ('disease_name', 'district', 'title')
    ordering = ('-created_at',)
