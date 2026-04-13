from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager

class Country(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=128)
    def __str__(self):
        return f"{self.name} ({self.code})"
    

class CustomUserManager(UserManager):
    def create_superuser(self, username, email, password, **extra_fields):
        extra_fields.setdefault('role', 'admin')
        return super().create_superuser(username, email, password, **extra_fields)

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('member', 'Member')
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    country = models.ForeignKey(Country, null=True, blank=True, on_delete=models.SET_NULL)
    # optional OneToOne link to Address (created at registration)
    # address = models.OneToOneField('address.Address', null=True, blank=True, on_delete=models.SET_NULL)
    # Optional phone number for users. Make unique to avoid duplicate accounts
    # tied to the same phone number.
    phone = models.CharField(max_length=32, null=True, blank=True, unique=True)
    # Make email unique to prevent multiple accounts with same email.
    email = models.EmailField(blank=True, null=True, unique=True)
    
    objects = CustomUserManager()

