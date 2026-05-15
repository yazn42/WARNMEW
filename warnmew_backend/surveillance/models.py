from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver


class DailyDiseaseRecord(models.Model):
    """
    Model representing daily disease surveillance records.
    Based strictly on the 42-column wide schema from warnmew_training_dataset.csv
    """
    report_date = models.DateField(db_index=True)
    district = models.CharField(max_length=100, db_index=True)
    
    # Fever
    fever_op_cases = models.IntegerField(default=0)
    fever_ip_cases = models.IntegerField(default=0)
    
    # Chikungunya
    chikungunya_suspected = models.IntegerField(default=0)
    chikungunya_confirmed = models.IntegerField(default=0)
    chikungunya_deaths = models.IntegerField(default=0)
    
    # Dengue
    dengue_suspected = models.IntegerField(default=0)
    dengue_confirmed = models.IntegerField(default=0)
    dengue_deaths = models.IntegerField(default=0)
    
    # Lepto
    lepto_suspected = models.IntegerField(default=0)
    lepto_confirmed = models.IntegerField(default=0)
    lepto_deaths = models.IntegerField(default=0)
    
    # Others
    add_cases = models.IntegerField(default=0)
    chickenpox_cases = models.IntegerField(default=0)
    hepatitis_a_cases = models.IntegerField(default=0)
    hepatitis_b_cases = models.IntegerField(default=0)
    cholera_suspected = models.IntegerField(default=0)
    cholera_confirmed = models.IntegerField(default=0)
    je_suspected = models.IntegerField(default=0)
    je_confirmed = models.IntegerField(default=0)
    malaria_imported = models.IntegerField(default=0)
    malaria_indigenous = models.IntegerField(default=0)
    typhoid_cases = models.IntegerField(default=0)
    h1n1_cases = models.IntegerField(default=0)
    measles_cases = models.IntegerField(default=0)
    scrub_typhus_cases = models.IntegerField(default=0)
    diphtheria_cases = models.IntegerField(default=0)
    amebic_meningoencephalitis_cases = models.IntegerField(default=0)
    nipah_cases = models.IntegerField(default=0)
    shigella_cases = models.IntegerField(default=0)
    west_nile_fever_cases = models.IntegerField(default=0)
    monkeypox_cases = models.IntegerField(default=0)
    covid19_cases = models.IntegerField(default=0)
    covid19_deaths = models.IntegerField(default=0)
    rabies_cases = models.IntegerField(default=0)
    influenza_cases = models.IntegerField(default=0)
    
    # External Data
    climate_rainfall_mm = models.FloatField(null=True, blank=True)
    climate_avg_temp_c = models.FloatField(null=True, blank=True)
    climate_humidity_percent = models.FloatField(null=True, blank=True)
    social_search_index_dengue = models.FloatField(null=True, blank=True)
    social_search_index_fever = models.FloatField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-report_date', 'district']
        verbose_name = 'Daily Disease Record'
        verbose_name_plural = 'Daily Disease Records'
        constraints = [
            models.UniqueConstraint(
                fields=['report_date', 'district'],
                name='unique_daily_district_record'
            )
        ]
        indexes = [
            models.Index(fields=['report_date', 'district']),
        ]
    
    def __str__(self):
        return f"{self.district} - {self.report_date}"


class UserProfile(models.Model):
    """
    Extends Django User with role-based access control.
    Roles: admin, researcher, health_authority
    """
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('researcher', 'Researcher'),
        ('health_authority', 'Health Authority'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='researcher')
    organization = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create UserProfile when a User is created."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


class Alert(models.Model):
    """
    Epidemic alert/notification generated when forecasts exceed thresholds.
    """
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    disease_name = models.CharField(max_length=100, db_index=True)
    district = models.CharField(max_length=100, default='Kerala')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    title = models.CharField(max_length=300)
    message = models.TextField()
    forecast_value = models.FloatField(null=True, blank=True)
    threshold_value = models.FloatField(null=True, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Alert'
        verbose_name_plural = 'Alerts'
    
    def __str__(self):
        return f"[{self.severity.upper()}] {self.disease_name} - {self.title}"
