# Core Viewset Implementation Notes

This document records the design decisions, patterns used, and reasoning behind
the `core` app viewset implementation (`core/views.py`).

---

## Overview

Four viewsets were implemented in `core/views.py`:

| Viewset | Model | Auth |
|---|---|---|
| `CurrencyViewSet` | `Currency` | Public |
| `CategoryViewSet` | `Category` | JWT required |
| `TransactionViewSet` | `Transaction` | JWT required |
| `BudgetViewSet` | `Budget` | JWT required |

All authenticated viewsets scope their data to `request.user` — a user can only
read and modify their own records.

---

## `CurrencyViewSet`

```python
class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = (permissions.AllowAny,)
```

**Why `ReadOnlyModelViewSet`:** Currencies are reference data. No user should be
able to create, update, or delete currencies through the API — that is an admin
operation. `ReadOnlyModelViewSet` exposes only `list` and `retrieve`, blocking all
write operations at the router level.

**Why `AllowAny`:** The Flutter app needs to populate a currency picker before a
user is logged in (e.g. during registration). Making this endpoint public avoids a
chicken-and-egg problem where the user needs to be authenticated to see the data
needed to register.

---

## `CategoryViewSet`

### Queryset: System defaults + user-owned

```python
def get_queryset(self):
    if getattr(self, 'swagger_fake_view', False):
        return Category.objects.none()
    return Category.objects.filter(
        Q(user__isnull=True) | Q(user=self.request.user)
    )
```

**Why this filter:** Categories have two kinds of records:
- `user=None` — system-wide defaults seeded by the `seed_categories` management
  command (e.g. Food, Transport). These are shared across all users.
- `user=<id>` — custom categories created by a specific user.

A user should see both their own categories and the system defaults in a single
list, so the query uses an `OR` condition with `Q` objects. Without this, users
would only see their own custom categories and would need a separate endpoint for
defaults.

### `perform_create`: auto-assign owner

```python
def perform_create(self, serializer):
    category = serializer.save(user=self.request.user)
```

**Why:** The `user` field is not writable from the request body (it's
`read_only=True` in the serializer). Instead, it is injected server-side here.
This prevents a user from creating a category and assigning it to another user's
account by passing a different `user` id in the payload.

### `destroy`: block deletion of system defaults

```python
def destroy(self, request, *args, **kwargs):
    category = self.get_object()
    if category.is_default or category.user is None:
        # block + log warning
        return Response(..., status=HTTP_403_FORBIDDEN)
    if category.user != request.user:
        # block + log warning
        return Response(..., status=HTTP_403_FORBIDDEN)
    # log warning, proceed
    return super().destroy(...)
```

**Why two checks:**
1. `is_default or user is None` — catches system categories regardless of whether
   the `is_default` flag was set (defensive: a system category with `user=None` but
   `is_default=False` is still a system category).
2. `category.user != request.user` — catches the edge case where a user somehow
   retrieves another user's category id and attempts to delete it. The queryset
   filter should already prevent this, but this is a second layer of defence.

**Why `WARNING` log level on delete:** Deleting a category cascades to removing
the FK reference from all associated `Transaction` records (they become
`category=NULL`). This is a destructive operation worth flagging.

### `update`: force partial updates

```python
def update(self, request, *args, **kwargs):
    ...
    kwargs['partial'] = True
    return super().update(...)
```

**Why:** Forces all updates to behave as PATCH regardless of whether the client
sends PUT or PATCH. This is friendlier for mobile clients — they don't need to
send the full object to update a single field. Consistent behaviour avoids
confusion between PUT and PATCH semantics.

---

## `TransactionViewSet`

### Queryset: User-scoped with filters

```python
def get_queryset(self):
    if getattr(self, 'swagger_fake_view', False):
        return Transaction.objects.none()
    qs = Transaction.objects.filter(user=self.request.user).select_related(
        'category', 'currency'
    )
    params = self.request.query_params
    if date_from := params.get('date_from'):
        qs = qs.filter(date__gte=date_from)
    if date_to := params.get('date_to'):
        qs = qs.filter(date__lte=date_to)
    if transaction_type := params.get('transaction_type'):
        qs = qs.filter(transaction_type=transaction_type)
    if category_id := params.get('category'):
        qs = qs.filter(category_id=category_id)
    return qs
```

**Why `select_related`:** `TransactionSerializer` nests the full `category` and
`currency` objects in its response. Without `select_related`, each transaction in
a list response would trigger two additional SQL queries (one for category, one
for currency) — a classic N+1 problem. `select_related` collapses these into a
single JOIN query.

**Why query param filtering in `get_queryset`:** The filters are applied in
`get_queryset` rather than in a separate `filter_backends` setup so that the same
filtered queryset is reused by the custom `summary` action. If filters were applied
only in `list`, the `summary` action would need to duplicate the filtering logic.
This approach keeps both actions consistent with a single source of truth.

### `summary` custom action

```python
@action(detail=False, methods=['get'], url_path='summary')
def summary(self, request):
    qs = self.get_queryset()  # reuses all filters
    totals = qs.aggregate(
        total_income=Sum('amount', filter=Q(transaction_type='income')),
        total_expense=Sum('amount', filter=Q(transaction_type='expense')),
    )
    ...
    return Response({
        'total_income': str(total_income),
        'total_expense': str(total_expense),
        'net': str(net),
        'filters': { ... }
    })
```

**Why a custom action instead of a separate view:** The summary is logically part
of the transaction resource and shares its auth, queryset, and filter logic. A
`@action` keeps everything co-located without needing a separate serializer,
URL entry, or view class.

**Why `detail=False`:** The summary applies to a *collection* of transactions
(aggregation), not a single transaction instance. `detail=False` routes it to
`/api/transactions/summary/` rather than `/api/transactions/{id}/summary/`.

**Why `str()` on decimal totals:** Django's `Sum` aggregation returns a `Decimal`
object. JSON serialisation of `Decimal` raises a `TypeError` in Python's standard
`json` module. Converting to `str` produces a lossless, exact decimal string
(e.g. `"4250.75"`) that the Flutter client can parse safely.

**Why echo filters in the response:** Including the active filters in the response
body lets the Flutter app confirm exactly which criteria the summary was computed
against, without having to track query params separately on the client side.

---

## `BudgetViewSet`

### Queryset: User-scoped

```python
def get_queryset(self):
    if getattr(self, 'swagger_fake_view', False):
        return Budget.objects.none()
    return Budget.objects.filter(user=self.request.user).select_related('currency')
```

**Why `select_related('currency')`:** Same reasoning as `TransactionViewSet` —
`BudgetSerializer` nests the full `currency` object, so pre-fetching avoids N+1
queries on list responses.

### `perform_update` logging

```python
def perform_update(self, serializer):
    budget = serializer.save()
    logger.info(f"Budget updated: id={budget.id} | ...")
```

**Why log updates on Budget but not on other models:** A budget represents a
financial commitment. Changes to the limit or date range affect all downstream
budget-vs-actual calculations. Logging updates creates an audit trail that is
useful for debugging discrepancies between what a user set and what the app
computed.

---

## Logging Strategy

All viewsets use a module-level logger:

```python
logger = logging.getLogger(__name__)
```

`__name__` resolves to `core.views`, which routes through the root logger
configured in `settings.py` (console at `INFO`, rotating file at `WARNING`).

### Log levels used

| Event | Level | Reason |
|---|---|---|
| Category created | `INFO` | Normal operation, useful for auditing |
| Transaction created | `INFO` | Normal operation, useful for auditing |
| Budget created / updated | `INFO` | Financial record, useful for auditing |
| Summary requested | `INFO` | Useful for usage analytics |
| Category delete attempt on system default | `WARNING` | Attempted policy violation |
| Category delete attempt on another user's record | `WARNING` | Attempted unauthorised access |
| Category deleted (own) | `WARNING` | Destructive operation — cascades to transactions |

Category deletion is `WARNING` even when legitimate because it is destructive
(it nullifies `category` on related transactions). This ensures it always
appears in the rotating log file (which captures `WARNING+`) regardless of
console verbosity settings.

---

## Serializer Cross-field Validation

`TransactionSerializer.validate()` enforces that the `transaction_type` of a
transaction matches the `category_type` of its assigned category:

```python
def validate(self, data):
    category = data.get('category') or (self.instance.category if self.instance else None)
    transaction_type = data.get('transaction_type') or (...)
    if category and transaction_type and category.category_type != transaction_type:
        raise serializers.ValidationError(...)
    return data
```

**Why this matters:** Without this check, a user could log an `income` transaction
under a `Food` (expense) category. This would produce incorrect summary totals
and confusing category-level reports on the Flutter dashboard.

**Why check `self.instance`:** On PATCH (partial update), the incoming `data` dict
only contains the fields being updated. If only `amount` is being changed, neither
`category` nor `transaction_type` will be in `data`. Falling back to
`self.instance` ensures the validation still runs against the existing values on
the record.
