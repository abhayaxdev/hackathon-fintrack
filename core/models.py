from django.db import models
from users.models import User


class Currency(models.Model):
    code = models.CharField(max_length=10, unique=True)  # ISO 4217 e.g. "NRS", "USD"
    name = models.CharField(max_length=100, null=True)              # e.g. "Nepali Rupee"
    symbol = models.CharField(max_length=10, null=True)             # e.g. "₨"

    class Meta:
        verbose_name_plural = "Currencies"
        ordering = ['code']

    def __str__(self):
        return f"{self.code} ({self.symbol})"


class Category(models.Model):
    CATEGORY_TYPE = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPE, default='expense')

    # null user = system-wide default category; non-null = user-created custom category
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='categories')
    is_default = models.BooleanField(default=False)  # True for system-provided default categories

    # UI hints for the Flutter app
    icon = models.CharField(max_length=50, null=True, blank=True)   # icon identifier e.g. "food", "transport"
    color = models.CharField(max_length=7, null=True, blank=True)   # hex color e.g. "#FF5733"

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['category_type', 'name']

    def __str__(self):
        return f"{self.name} ({self.category_type})"


class Transaction(models.Model):
    TRANSACTION_TYPE = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE, default='expense')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    title = models.CharField(max_length=255)
    note = models.TextField(blank=True)

    date = models.DateField()
    attachment = models.ImageField(upload_to='receipts/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.amount}"


class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    amount_limit = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, blank=True, related_name='budgets')
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.user.username} - {self.amount_limit} ({self.start_date} to {self.end_date})"


class RecurringPayment(models.Model):
    FREQUENCY_CHOICES = (
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('yearly', 'Yearly'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recurring_payments')
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(Currency, on_delete=models.SET_NULL, null=True, blank=True, related_name='recurring_payments')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='recurring_payments')

    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    next_due_date = models.DateField(blank=True)

    reminder_days_before = models.IntegerField(default=2)

    # EMI fields — optional, only set for instalment-based payments
    total_installments = models.IntegerField(null=True, blank=True)
    completed_installments = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['next_due_date']

    def _calculate_next_due(self, from_date):
        """Return the next due date from a given date based on frequency."""
        from dateutil.relativedelta import relativedelta
        if self.frequency == 'weekly':
            return from_date + relativedelta(weeks=1)
        elif self.frequency == 'yearly':
            return from_date + relativedelta(years=1)
        else:  # monthly (default)
            return from_date + relativedelta(months=1)

    def save(self, *args, **kwargs):
        # Auto-set next_due_date on first creation if not explicitly provided
        if not self.pk and not self.next_due_date:
            self.next_due_date = self.start_date
        # Auto-deactivate completed EMIs
        if self.total_installments and self.completed_installments >= self.total_installments:
            self.is_active = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - {self.amount}"


class PaymentHistory(models.Model):
    STATUS_CHOICES = (
        ('paid', 'Paid'),
        ('missed', 'Missed'),
    )

    recurring_payment = models.ForeignKey(RecurringPayment, on_delete=models.CASCADE, related_name='history')
    paid_on = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    note = models.TextField(blank=True)  # e.g. reason for missed payment

    class Meta:
        ordering = ['-paid_on']
        verbose_name_plural = 'Payment Histories'

    def __str__(self):
        return f"{self.recurring_payment.title} - {self.status} on {self.paid_on}"
