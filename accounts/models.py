from django.db import models
from django.contrib.auth.models import User


class StaffProfile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('teacher', 'Teacher'),
        ('accountant', 'Accountant'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='admin')
    school_id = models.IntegerField(default=5)

    def __str__(self):
        return f'{self.user.get_full_name()} ({self.get_role_display()})'
