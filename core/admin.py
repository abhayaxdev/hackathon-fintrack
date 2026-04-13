from django.contrib import admin
from .models import Currency, Category, Transaction, Budget


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'symbol')
    search_fields = ('code', 'name')
    ordering = ('code',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'category_type', 'user', 'is_default', 'icon', 'color')
    list_filter = ('category_type', 'is_default')
    list_editable = ('is_default',)
    search_fields = ('name',)
    ordering = ('category_type', 'name')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'amount', 'currency', 'transaction_type', 'category', 'date', 'created_at')
    list_filter = ('transaction_type', 'category', 'currency', 'date')
    search_fields = ('title', 'note', 'user__username')
    date_hierarchy = 'date'
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Basic Info', {
            'fields': ('user', 'title', 'note', 'attachment')
        }),
        ('Amount & Type', {
            'fields': ('amount', 'currency', 'transaction_type', 'category')
        }),
        ('Date', {
            'fields': ('date', 'created_at')
        }),
    )


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount_limit', 'currency', 'start_date', 'end_date')
    list_filter = ('currency',)
    search_fields = ('user__username',)
    ordering = ('-start_date',)
