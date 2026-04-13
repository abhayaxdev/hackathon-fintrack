# FinTrack API

Django + DRF backend for the FinTrack hackathon expense tracker app.

- **Language / framework:** Python 3.12, Django 5.2, Django REST Framework
- **Auth:** JWT via `djangorestframework-simplejwt` (access 30 min, refresh 7 days, rotation + blacklist)
- **API docs:** `drf-spectacular` — Swagger UI and ReDoc
- **Timezone:** Asia/Kathmandu
- **Default currency:** NRS (Nepali Rupee)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd fintrack

python -m venv .env
source .env/bin/activate      # Windows: .env\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values. Minimum required for local development:

```env
DEBUG=True
DJANGO_SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=localhost,127.0.0.1
USE_SQLITE=True
CORS_ALLOW_ALL_ORIGINS=True
```

For PostgreSQL, set `USE_SQLITE=False` and fill in `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_HOST`, `DB_PORT`.

### 3. Run migrations

```bash
python manage.py migrate
```

This applies all migrations including `core`, `users`, and `token_blacklist`
(required for JWT refresh token rotation).

### 4. Create a superuser

```bash
python manage.py createsuperuser
```

The superuser account is used to access the Django admin at `/admin/`.

### 5. Seed default categories

```bash
python manage.py seed_categories
```

Seeds 11 system-wide default expense categories (Food, Transport, Health, etc.)
that are shared across all users. This command is idempotent — safe to run
multiple times.

### 6. Run the development server

```bash
python manage.py runserver
```

---

## API Documentation

| URL | Description |
|---|---|
| `/api/schema/swagger/` | Swagger UI — interactive API explorer |
| `/api/schema/redoc/` | ReDoc — readable reference docs |
| `/api/schema/` | Raw OpenAPI 3.0 schema (JSON) |

Click the **Authorize** button in Swagger UI and enter `Bearer <access_token>`
to authenticate all requests.

---

## API Endpoints

### Auth — `/api/auth/`

| Method | URL | Description |
|---|---|---|
| POST | `/api/auth/register/` | Register a new user |
| POST | `/api/auth/login/` | Login — returns access + refresh tokens |
| POST | `/api/auth/token/refresh/` | Refresh access token |
| POST | `/api/auth/logout/` | Logout — blacklists the refresh token |
| GET / PATCH | `/api/auth/me/` | Get or update the current user's profile |

### Core — `/api/` (JWT required except currencies)

| Method | URL | Description |
|---|---|---|
| GET | `/api/currencies/` | List all currencies (public) |
| GET/POST | `/api/categories/` | List categories (system + own) / create custom |
| GET/PUT/PATCH/DELETE | `/api/categories/{id}/` | Retrieve / update / delete own category |
| GET/POST | `/api/transactions/` | List own transactions (filterable) / create |
| GET | `/api/transactions/summary/` | Income / expense / net totals (same filters as list) |
| GET/PUT/PATCH/DELETE | `/api/transactions/{id}/` | Retrieve / update / delete a transaction |
| GET/POST | `/api/budgets/` | List own budgets / create |
| GET/PUT/PATCH/DELETE | `/api/budgets/{id}/` | Retrieve / update / delete a budget |
| GET/POST | `/api/recurring-payments/` | List own recurring payments / create |
| POST | `/api/recurring-payments/{id}/mark-paid/` | Mark a payment as paid (advances due date, logs history, creates transaction) |
| GET/PUT/PATCH/DELETE | `/api/recurring-payments/{id}/` | Retrieve / update / delete a recurring payment |
| GET | `/api/payment-history/` | List payment history (paid + missed) for own payments |
| GET | `/api/payment-history/{id}/` | Retrieve a single history entry |

### Transaction list filters

All apply to both `GET /api/transactions/` and `GET /api/transactions/summary/`:

| Param | Type | Example |
|---|---|---|
| `date_from` | date | `2025-01-01` |
| `date_to` | date | `2025-01-31` |
| `transaction_type` | string | `income` or `expense` |
| `category` | integer | `3` |

---

## Management Commands

### `seed_categories`

```bash
python manage.py seed_categories
```

Seeds 11 default system-wide categories. Idempotent.

### `mark_missed_payments`

```bash
python manage.py mark_missed_payments
```

Intended to run daily via cron or a task scheduler. For each active recurring
payment it:

- Records a `missed` `PaymentHistory` entry for any payment whose `next_due_date`
  has passed without being marked paid, then advances the due date
- Sends a push notification reminder (currently stubbed — see
  `core/notifications.py`) for payments due within `reminder_days_before` days

Example cron entry (runs daily at 08:00 NPT / 02:15 UTC):

```cron
15 2 * * * /path/to/.env/bin/python /path/to/fintrack/manage.py mark_missed_payments >> /path/to/logs/cron.log 2>&1
```

---

## Project Structure

```
fintrack/
├── .env                  # Environment variables (git-ignored)
├── .env.example          # Environment variable template
├── manage.py
├── requirements.txt
├── db.sqlite3            # SQLite DB (development only, git-ignored)
├── logs/                 # Rotating log files (git-ignored)
│   └── app_main.log      # WARNING+ events
├── project/
│   ├── settings.py       # JWT, CORS, logging, DB, Spectacular config
│   └── urls.py           # Root URL config
├── users/                # Auth app — User model, JWT views
│   ├── models.py         # User (AbstractUser), Country
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
└── core/                 # Main app — all financial models and APIs
    ├── models.py         # Currency, Category, Transaction, Budget, RecurringPayment, PaymentHistory
    ├── serializers.py
    ├── views.py
    ├── urls.py
    ├── admin.py
    ├── notifications.py  # Push notification stub (FCM TODO)
    ├── migrations/
    └── management/
        └── commands/
            ├── seed_categories.py
            └── mark_missed_payments.py
```

---

## Logging

| Handler | Level | Output |
|---|---|---|
| Console | `INFO+` | Terminal (development) |
| Rotating file | `WARNING+` | `logs/app_main.log` (max 2 MB × 5 backups) |

---

## Implementation Notes

- [`swagger_implementation_fixes.md`](swagger_implementation_fixes.md) — Swagger/drf-spectacular fixes
- [`core_viewset_implementation.md`](core_viewset_implementation.md) — Core viewset design decisions
- [`recurring_payments_implementation.md`](recurring_payments_implementation.md) — Recurring payments design decisions
