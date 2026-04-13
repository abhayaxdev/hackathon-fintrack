from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Country


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')
    ordering = ('name',)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'phone', 'role', 'country', 'is_active', 'is_staff')
    list_filter = ('role', 'is_active', 'is_staff', 'country')
    list_editable = ('role', 'is_active')
    search_fields = ('username', 'email', 'phone')
    ordering = ('username',)

    # Extend the default fieldsets to include custom fields
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Profile', {
            'fields': ('role', 'phone', 'country')
        }),
    )

    # Also include custom fields when creating a user via admin
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Profile', {
            'fields': ('role', 'phone', 'country')
        }),
    )
