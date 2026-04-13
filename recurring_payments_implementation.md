# Recurring Payments Implementation Notes

This document records the design decisions, patterns used, and reasoning behind
the recurring payments feature: `RecurringPayment`, `PaymentHistory`, their
serializers, viewsets, the `mark-paid` action, and the `mark_missed_payments`
management command.

---

## Models (`core/models.py`)

### `RecurringPayment`

```python
class RecurringPayment(models.Model):
    FREQUENCY_CHOICES = (
        ('monthly', 'Monthly'),
        ('weekly', 'Weekly'),
        ('yearly', 'Yearly'),
    )

    user = models.ForeignKey(User, ...)
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.ForeignKey(Currency, ...)
    category = models.ForeignKey(Category, ...)

    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    next_due_date = models.DateField(blank=True)

    reminder_days_before = models.IntegerField(default=2)

    # EMI / instalment fields
    total_installments = models.IntegerField(null=True, blank=True)
    completed_installments = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Why `next_due_date` is separate from `start_date`:**
`start_date` is immutable — it records when the payment was set up. `next_due_date`
is a rolling cursor that advances each time a payment is marked paid or missed.
The Flutter UI uses `next_due_date` to display "due in X days" without needing to
calculate it from `start_date` + frequency + payment count.

**Why `reminder_days_before` is per-record:** Different payments have different
urgency. A utility bill might need 3 days notice to process a bank transfer; a
streaming subscription can be reminded the day before. Storing this on the record
(defaulting to 2) lets users configure it per payment rather than applying one
global setting.

**Why separate EMI fields (`total_installments`, `completed_installments`):**
Many recurring payments in Nepal are instalment-based (EMIs for appliances, loans,
vehicles). A regular subscription has `total_installments=None` (infinite). An EMI
sets `total_installments=N` and the record auto-deactivates when
`completed_installments >= total_installments` (enforced in `save()`).

### `_calculate_next_due(from_date)`

```python
def _calculate_next_due(self, from_date):
    from dateutil.relativedelta import relativedelta
    if self.frequency == 'weekly':
        return from_date + relativedelta(weeks=1)
    elif self.frequency == 'yearly':
        return from_date + relativedelta(years=1)
    else:  # monthly
        return from_date + relativedelta(months=1)
```

**Why `relativedelta` instead of `timedelta`:**
`timedelta(days=30)` is wrong for monthly payments — months have 28–31 days.
`relativedelta(months=1)` correctly advances January 31 to February 28 (not
March 2 or 3), handling month-end edge cases that `timedelta` cannot.
`python-dateutil` was added to `requirements.txt` for this reason.

**Why a private method on the model:** Both the `mark_paid` viewset action and
the `mark_missed_payments` management command need to advance `next_due_date`.
Centralising the logic on the model prevents duplication and ensures both callers
always use the same date arithmetic.

### `save()` override

```python
def save(self, *args, **kwargs):
    if not self.pk and not self.next_due_date:
        self.next_due_date = self.start_date
    if self.total_installments and self.completed_installments >= self.total_installments:
        self.is_active = False
    super().save(*args, **kwargs)
```

**Why auto-set `next_due_date = start_date` on creation:**
The first due date is the start date. Requiring the client to send both
`start_date` and `next_due_date` with the same value on creation is redundant and
error-prone. The `save()` guard only triggers when creating a new record (`not
self.pk`) and only when `next_due_date` was not explicitly provided.

**Why auto-deactivate in `save()`:** The deactivation check runs every time the
record is saved, so it fires automatically when `mark_paid` increments
`completed_installments` and calls `payment.save()`. This removes the need for the
viewset action to manually check whether the EMI is complete — the model handles
its own state.

---

### `PaymentHistory`

```python
class PaymentHistory(models.Model):
    STATUS_CHOICES = (('paid', 'Paid'), ('missed', 'Missed'))

    recurring_payment = models.ForeignKey(RecurringPayment, on_delete=models.CASCADE, ...)
    paid_on = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    note = models.TextField(blank=True)
```

**Why a separate model instead of storing history on the transaction:**
`PaymentHistory` captures both paid and **missed** payments. A missed payment has
no corresponding `Transaction` entry (the money was never moved), so it cannot live
on the `Transaction` model. Having a dedicated audit log also lets the Flutter app
show a compliance timeline: "paid on time", "missed", "paid late".

**Why `on_delete=CASCADE`:** If a user deletes a recurring payment, its history
becomes meaningless. There is no orphaned-history use case, so cascading is
appropriate.

---

## Serializers (`core/serializers.py`)

### `RecurringPaymentSerializer`

```python
read_only_fields = ('id', 'next_due_date', 'completed_installments', 'is_active', 'created_at')
```

**Why `next_due_date`, `completed_installments`, and `is_active` are read-only:**
These are system-managed state fields. They must only be updated through the
`mark-paid` action or the `mark_missed_payments` command — never by direct user
input. Making them read-only at the serializer level provides a hard API boundary:
no client can manipulate these fields by patching the record directly.

### Validation

```python
def validate_total_installments(self, value):
    if value is not None and value < 1:
        raise serializers.ValidationError('total_installments must be a positive integer.')
    return value

def validate_reminder_days_before(self, value):
    if value < 0:
        raise serializers.ValidationError('reminder_days_before cannot be negative.')
    return value
```

**Why validate `total_installments` here:** The field is nullable (for infinite
subscriptions), but if it is provided it must be at least 1. A value of 0 would
immediately trigger auto-deactivation on the first save, which is a meaningless
state.

### `PaymentHistorySerializer`

```python
read_only_fields = ('id', 'recurring_payment', 'recurring_payment_title', 'status')
```

**Why `status` is read-only:** `PaymentHistory` entries are created exclusively by
the `mark-paid` action (status=`paid`) or `mark_missed_payments` command
(status=`missed`). No client should be able to create or edit a history entry
directly — the viewset is `ReadOnlyModelViewSet` for this reason. Making `status`
read-only is belt-and-suspenders.

**Why expose `recurring_payment_title`:**
```python
recurring_payment_title = serializers.CharField(
    source='recurring_payment.title', read_only=True
)
```
The Flutter app renders a list of payment history entries. Without this, it would
need to either nest the full `RecurringPayment` object (expensive) or make a
second request to look up the title (N+1 calls). A single read-only string field
avoids both.

---

## Viewsets (`core/views.py`)

### `RecurringPaymentViewSet`

#### Queryset with `is_active` filter

```python
def get_queryset(self):
    if getattr(self, 'swagger_fake_view', False):
        return RecurringPayment.objects.none()
    qs = RecurringPayment.objects.filter(user=self.request.user).select_related(
        'category', 'currency'
    )
    is_active = self.request.query_params.get('is_active')
    if is_active is not None:
        qs = qs.filter(is_active=is_active.lower() == 'true')
    return qs
```

**Why expose `is_active` as a query param:** The Flutter home screen shows only
active upcoming payments. The history/archive screen shows all. Rather than having
two separate endpoints, a single optional filter covers both cases cleanly.

**Why `is_active.lower() == 'true'`:** Query params arrive as strings. `bool('false')`
in Python is `True` (non-empty string), so a naive cast would break filtering.
Explicit string comparison is the correct approach.

#### `mark_paid` custom action

```python
@action(detail=True, methods=['post'], url_path='mark-paid')
def mark_paid(self, request, pk=None):
```

**Why `detail=True`:** The action targets a specific recurring payment instance
(`/api/recurring-payments/{id}/mark-paid/`), not the collection.

**Why `methods=['post']`:** Marking a payment as paid has side effects (creates
`PaymentHistory`, creates `Transaction`, advances `next_due_date`). This is not
idempotent — calling it twice would record two payments. POST communicates this
intent correctly.

**What `mark_paid` does in sequence:**

1. **Guard:** Returns `400` if `payment.is_active` is `False`. A deactivated
   payment (completed EMI or manually deactivated) should not accept new payments.

2. **`PaymentHistory` entry:** Creates a record with `status='paid'` and today's
   date. This is the audit log entry.

3. **Auto-create `Transaction`:** Creates a `Transaction` record of type `expense`
   so the payment automatically appears in the user's transaction history and is
   included in budget calculations and summary totals. Without this, a user would
   need to manually log the payment as a transaction separately — error-prone and
   inconsistent.

4. **Advance state:** Increments `completed_installments` and advances
   `next_due_date` by one frequency period using `_calculate_next_due()`.

5. **`payment.save()`:** Triggers the model's `save()` override, which
   auto-deactivates the record if the EMI is now complete.

6. **Returns updated serializer data:** The response includes the updated
   `next_due_date` and `is_active` state so the Flutter app can update its UI
   immediately without a separate GET request.

**Why `timezone.localdate()` instead of `date.today()`:**
The project timezone is `Asia/Kathmandu` (UTC+5:45). `date.today()` uses the
server's OS timezone, which may be UTC. `timezone.localdate()` returns the current
date in the configured `TIME_ZONE`, ensuring "today" is correct for the user.

### `PaymentHistoryViewSet`

```python
class PaymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    ...
    def get_queryset(self):
        qs = PaymentHistory.objects.filter(
            recurring_payment__user=self.request.user
        ).select_related('recurring_payment')
        ...
```

**Why `ReadOnlyModelViewSet`:** History entries are immutable audit records. They
should never be created, edited, or deleted through the API — only via controlled
internal operations (`mark_paid`, `mark_missed_payments`). `ReadOnlyModelViewSet`
enforces this at the router level.

**Why filter by `recurring_payment__user`:** `PaymentHistory` has no direct `user`
FK — it belongs to a `RecurringPayment` which in turn belongs to a user. The
double-underscore traversal scopes the queryset to only the current user's history
entries.

**Why `select_related('recurring_payment')`:** `PaymentHistorySerializer` reads
`recurring_payment.title` via `recurring_payment_title`. Without `select_related`,
every entry in a list response would trigger an extra query to fetch the parent
`RecurringPayment`.

---

## Management Command: `mark_missed_payments`

Located at `core/management/commands/mark_missed_payments.py`. Designed to run
daily via cron or a task scheduler (e.g. Celery Beat, system cron).

### What it does

```
for each active RecurringPayment:
    if next_due_date < today:
        if no PaymentHistory entry exists for that due date:
            create PaymentHistory(status='missed')
            advance next_due_date by one period
    elif next_due_date is within reminder_days_before days:
        send_payment_reminder(user, payment)
```

**Why check for an existing `PaymentHistory` entry before creating a missed record:**
If the command runs multiple times in a day (or is re-run after a crash), it
should not create duplicate missed entries for the same due date. The existence
check makes the missed-recording logic idempotent.

**Why advance `next_due_date` after recording a missed payment:**
Without advancing the date, the same payment would be flagged as missed again the
next day (and the day after). Advancing by one period moves the cursor forward
so the next cycle is evaluated correctly.

**Why `WARNING` log level for missed payments:**
A missed payment is a financial event that warrants attention — it may indicate a
user has insufficient funds, a bank transfer failed, or a subscription lapsed.
`WARNING` ensures these events are captured in the rotating log file
(`logs/app_main.log`, which captures `WARNING+`) and are distinguishable from
normal informational noise.

**Why send reminders only for payments not yet overdue:**
The `elif` ensures reminders are only sent when `next_due_date >= today`. Once a
payment has passed its due date without being paid, it is logged as missed — there
is no value in also sending a "reminder" for a payment that is already overdue.

---

## Notification Stub (`core/notifications.py`)

```python
def send_payment_reminder(user, recurring_payment):
    logger.info(f"[STUB] Payment reminder: '{recurring_payment.title}' ...")
```

**Why a stub:** FCM (Firebase Cloud Messaging) integration requires:
- A service account credentials file
- FCM device tokens stored per user (requires a `DeviceToken` model or a field on `User`)
- The `firebase-admin` package

These are outside the hackathon MVP scope. The stub logs at `INFO` so the rest of
the reminder pipeline (detection, date comparison, looping) can be tested end-to-end
without FCM. The full integration steps are documented in comments inside
`notifications.py`.

**Why a standalone module instead of a method on the model or viewset:**
Notification sending is a cross-cutting concern. Keeping it in its own module
means the `mark_missed_payments` command, the `mark_paid` action (if reminders are
ever added there), and any future Celery tasks can all import it without circular
dependencies.

---

## Migration Notes

The original `core` migration (`0001_initial.py`) was generated and applied before
`RecurringPayment` and `PaymentHistory` were added to `core/models.py`. A new
migration must be generated:

```bash
python manage.py makemigrations core
python manage.py migrate
```

The `token_blacklist` app (from `djangorestframework-simplejwt`) also has 13
pending migrations that must be applied at the same time.

---

## Logging Summary

All logging uses `logger = logging.getLogger(__name__)` which resolves to
`core.views` and `core.management.commands.mark_missed_payments` respectively.

| Event | Level | Location |
|---|---|---|
| Recurring payment created | `INFO` | `RecurringPaymentViewSet.perform_create` |
| Payment marked paid | `INFO` | `RecurringPaymentViewSet.mark_paid` |
| Missed payment recorded | `WARNING` | `mark_missed_payments` command |
| Reminder sent (stub) | `INFO` | `notifications.send_payment_reminder` |
