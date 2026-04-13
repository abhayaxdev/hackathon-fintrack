# Swagger / OpenAPI Implementation & Fixes

This document records every decision, fix, and reasoning behind the Swagger/OpenAPI
integration using `drf-spectacular`, as well as the schema-related fixes applied to
the `core` viewsets.

---

## Library Choice: `drf-spectacular` over `drf-yasg`

`drf-yasg` was considered but rejected for the following reasons:

| Concern | `drf-yasg` | `drf-spectacular` |
|---|---|---|
| OpenAPI version | 2.0 (Swagger 2) | 3.0 |
| Maintenance status | Largely unmaintained | Actively maintained |
| DRF 3.16 compatibility | Partial | Full |
| simplejwt support | Requires manual config | First-class, built-in |

`drf-spectacular 0.29.0` was installed and pinned in `requirements.txt`.

---

## Settings Changes (`project/settings.py`)

### 1. `DEFAULT_SCHEMA_CLASS`

```python
REST_FRAMEWORK = {
    ...
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}
```

**Why:** Without this, DRF uses its own basic schema class which does not produce
OpenAPI 3.0 output. This tells DRF to delegate all schema introspection to
`drf-spectacular`'s `AutoSchema`.

---

### 2. `SPECTACULAR_SETTINGS`

```python
SPECTACULAR_SETTINGS = {
    'TITLE': 'FinTrack API',
    'DESCRIPTION': '...',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'SECURITY': [{'BearerAuth': []}],
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
    'ENUM_NAME_OVERRIDES': {
        'TransactionTypeEnum': 'core.models.Transaction.TRANSACTION_TYPE',
    },
    'ENUM_GENERATE_CHOICE_DESCRIPTION': False,
}
```

**`SERVE_INCLUDE_SCHEMA: False`** — Prevents the raw schema endpoint
(`/api/schema/`) from listing itself recursively in the generated schema.

**`COMPONENT_SPLIT_REQUEST: True`** — Generates separate read and write schemas
for each serializer (e.g. `Transaction` for responses, `TransactionRequest` for
request bodies). This is important because many fields are read-only on response
but not on request (e.g. `created_at`, nested objects vs FK ids).

**`SECURITY: [{'BearerAuth': []}]`** — Enables the Authorize button in Swagger UI
with a JWT Bearer token input. Without this, the UI has no way to authenticate
requests against protected endpoints.

**`persistAuthorization: True`** — Keeps the entered Bearer token alive across
browser page refreshes in Swagger UI. Without this, the token has to be re-entered
every time the page is reloaded, which is disruptive during testing.

**`ENUM_NAME_OVERRIDES`** — See Fix #3 below.

---

## URL Routes (`project/urls.py`)

Three routes were added:

```python
path('api/schema/',         SpectacularAPIView.as_view(),       name='schema'),
path('api/schema/swagger/', SpectacularSwaggerView.as_view(...), name='swagger-ui'),
path('api/schema/redoc/',   SpectacularRedocView.as_view(...),   name='redoc'),
```

- `/api/schema/` — serves the raw OpenAPI 3.0 JSON/YAML (useful for importing
  into Postman, Insomnia, or Flutter's code generators)
- `/api/schema/swagger/` — Swagger UI for interactive browser testing
- `/api/schema/redoc/` — ReDoc, a clean read-only reference documentation UI

---

## Fix 1: `LogoutView` Missing `serializer_class`

**Error:**
```
Error [LogoutView]: exception raised while getting serializer.
'LogoutView' should either include a `serializer_class` attribute,
or override the `get_serializer_class()` method.
```

**Root cause:** `drf-spectacular` introspects every view by calling
`get_serializer_class()`. `LogoutView` extends `GenericAPIView` and manually reads
`request.data.get('refresh')` without declaring a serializer. The schema generator
had no way to know what the request body shape was.

**Fix:** A dedicated `_LogoutRequestSerializer` was added to `users/views.py`:

```python
class _LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text='Refresh token to blacklist.')
```

This was then assigned as `serializer_class = _LogoutRequestSerializer` on
`LogoutView`. This gives `drf-spectacular` a concrete schema to document the
request body (`{ "refresh": "<token>" }`), and also serves as implicit validation
documentation for API consumers.

The `inline_serializer` approach was attempted first but rejected — it returns a
serializer *instance*, not a *class*, and `drf-spectacular` requires a class
reference on `serializer_class`.

---

## Fix 2: Untyped Path Parameter `id` Warnings

**Warning (×3, one per viewset):**
```
Warning [BudgetViewSet]: could not derive type of path parameter "id" because
it is untyped and obtaining queryset from the viewset failed.
Defaulting to "string".
```

**Root cause:** `drf-spectacular` infers the type of `{id}` path parameters by
inspecting the viewset's `get_queryset()`. If `get_queryset()` raises an exception
during schema generation (which it does because `request.user` is unavailable with
no real request context), the type inference falls back to `"string"` and emits a
warning.

**Fix:** A `swagger_fake_view` guard was added to every user-scoped `get_queryset`:

```python
def get_queryset(self):
    if getattr(self, 'swagger_fake_view', False):
        return SomeModel.objects.none()
    return SomeModel.objects.filter(user=self.request.user)...
```

`drf-spectacular` sets `swagger_fake_view = True` on the view instance during
schema generation. Checking for this flag and returning an empty queryset allows
the schema generator to complete type inference (it knows the primary key is an
integer from the model's `BigAutoField`) without actually executing a real query.
This is the officially recommended pattern by `drf-spectacular`.

Applied to: `CategoryViewSet`, `TransactionViewSet`, `BudgetViewSet`.

---

## Fix 3: Duplicate Enum Name Collision

**Warning:**
```
Warning: encountered multiple names for the same choice set (TransactionTypeEnum).
This may be unwanted even though the generated schema is technically correct.
Add an entry to ENUM_NAME_OVERRIDES to fix the naming.
```

**Root cause:** Both `Category.category_type` and `Transaction.transaction_type`
use an identical set of choices: `[('income', 'Income'), ('expense', 'Expense')]`.
`drf-spectacular` detected two identical enums and auto-named both
`TransactionTypeEnum`, causing a naming collision in the generated schema
components.

**Fix:** `ENUM_NAME_OVERRIDES` was added to `SPECTACULAR_SETTINGS`:

```python
'ENUM_NAME_OVERRIDES': {
    'TransactionTypeEnum': 'core.models.Transaction.TRANSACTION_TYPE',
},
```

This tells `drf-spectacular` to use one canonical enum named `TransactionTypeEnum`
sourced from `Transaction.TRANSACTION_TYPE`, and reuse it wherever the same choices
appear (including `Category.category_type`). The schema now has a single
`TransactionTypeEnum` component used by both serializers.

---

## Viewset Decorators (`core/views.py`)

`@extend_schema_view` and `@extend_schema` decorators were added to all viewsets.

### `@extend_schema_view`

```python
@extend_schema_view(
    list=extend_schema(summary='List own transactions', parameters=_TRANSACTION_FILTERS),
    create=extend_schema(summary='Create a transaction'),
    ...
)
class TransactionViewSet(viewsets.ModelViewSet):
```

**Why:** Without summaries, Swagger UI displays auto-generated `operationId` values
like `transactions_list` as the endpoint title, which is unhelpful. Explicit
summaries make the UI immediately readable.

### `_TRANSACTION_FILTERS` shared parameter list

```python
_TRANSACTION_FILTERS = [
    OpenApiParameter('date_from', OpenApiTypes.DATE, ...),
    OpenApiParameter('date_to',   OpenApiTypes.DATE, ...),
    OpenApiParameter('transaction_type', OpenApiTypes.STR, enum=['income', 'expense'], ...),
    OpenApiParameter('category',  OpenApiTypes.INT, ...),
]
```

**Why:** The `list` action and the custom `summary` action both accept the same
four query parameters. Defining them once as a shared constant and passing to both
`@extend_schema` decorators avoids duplication and keeps them in sync. Without this,
the filter parameters would be invisible in Swagger UI — they only exist in the
view logic, not in the serializer, so `AutoSchema` cannot detect them
automatically.

### `@extend_schema` on the `summary` action

```python
@extend_schema(
    summary='Transaction summary — totals for income, expense and net',
    parameters=_TRANSACTION_FILTERS,
)
@action(detail=False, methods=['get'], url_path='summary')
def summary(self, request):
```

**Why:** Custom `@action` methods are not standard CRUD operations, so
`drf-spectacular` cannot infer their behaviour. Without `@extend_schema`, the
summary action would appear in Swagger UI with no query parameters and a confusing
auto-generated response schema (`Transaction` object). The decorator gives it a
proper description and correct filter parameters.

---

## Final Validation

After all fixes were applied, schema generation was validated with:

```bash
python manage.py spectacular --validate --fail-on-warn
```

Result: **0 warnings, 0 errors.** Full OpenAPI 3.0 schema generated successfully.
