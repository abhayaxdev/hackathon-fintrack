import logging
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from core.models import Transaction, Category, Currency

logger = logging.getLogger(__name__)

User = get_user_model()

# ---------------------------------------------------------------------------
# Seed data — February 2026 (baseline) and March 2026 (subject)
#
# Designed to give the Insight Engine a rich, varied packet:
#   - Food:           Feb  8,500  →  Mar 12,400   (+45.9%)  spike
#   - Transportation: Feb  3,200  →  Mar  2,100   (-34.4%)  win
#   - Entertainment:  Feb  2,000  →  Mar  3,800   (+90.0%)  spike
#   - Health:         Feb  1,500  →  Mar  1,600   ( +6.7%)  stable
#   - Shopping:       Feb  4,500  →  Mar  4,200   ( -6.7%)  stable
#   - Subscriptions:  Feb    800  →  Mar    800   (  0.0%)  flat
#   - Housing/Rent:   Feb 15,000  →  Mar 15,000   (  0.0%)  fixed cost
#   - Education:      Feb  2,500  →  Mar      0   (-100%)   disappeared
#   - Miscellaneous:  Feb      0  →  Mar  1,200   new       new category
# ---------------------------------------------------------------------------

TRANSACTIONS = [
    # ---- FEBRUARY 2026 (baseline month) ----

    # Food — 8,500 total
    {'title': 'Grocery run',          'amount': 2200, 'category': 'Food',            'date': date(2026, 2, 3)},
    {'title': 'Lunch at office',       'amount':  950, 'category': 'Food',            'date': date(2026, 2, 7)},
    {'title': 'Weekend dining out',    'amount': 1800, 'category': 'Food',            'date': date(2026, 2, 11)},
    {'title': 'Grocery run',          'amount': 1900, 'category': 'Food',            'date': date(2026, 2, 18)},
    {'title': 'Snacks & beverages',    'amount':  650, 'category': 'Food',            'date': date(2026, 2, 24)},
    {'title': 'Team lunch',            'amount': 1000, 'category': 'Food',            'date': date(2026, 2, 27)},

    # Transportation — 3,200 total
    {'title': 'Monthly bus pass',      'amount': 1200, 'category': 'Transportation',  'date': date(2026, 2, 1)},
    {'title': 'Taxi to airport',       'amount':  900, 'category': 'Transportation',  'date': date(2026, 2, 14)},
    {'title': 'Fuel',                  'amount':  700, 'category': 'Transportation',  'date': date(2026, 2, 20)},
    {'title': 'Ride share',            'amount':  400, 'category': 'Transportation',  'date': date(2026, 2, 26)},

    # Entertainment — 2,000 total
    {'title': 'Cinema tickets',        'amount':  600, 'category': 'Entertainment',   'date': date(2026, 2, 8)},
    {'title': 'Board game night',      'amount':  400, 'category': 'Entertainment',   'date': date(2026, 2, 15)},
    {'title': 'Concert tickets',       'amount': 1000, 'category': 'Entertainment',   'date': date(2026, 2, 22)},

    # Health & Fitness — 1,500 total
    {'title': 'Gym membership',        'amount':  900, 'category': 'Health & Fitness','date': date(2026, 2, 1)},
    {'title': 'Pharmacy',              'amount':  350, 'category': 'Health & Fitness','date': date(2026, 2, 12)},
    {'title': 'Yoga class',            'amount':  250, 'category': 'Health & Fitness','date': date(2026, 2, 19)},

    # Shopping — 4,500 total
    {'title': 'Clothing',              'amount': 2500, 'category': 'Shopping',        'date': date(2026, 2, 6)},
    {'title': 'Household supplies',    'amount': 1200, 'category': 'Shopping',        'date': date(2026, 2, 16)},
    {'title': 'Electronics accessory', 'amount':  800, 'category': 'Shopping',        'date': date(2026, 2, 23)},

    # Subscriptions — 800 total
    {'title': 'Netflix',               'amount':  350, 'category': 'Subscriptions',   'date': date(2026, 2, 5)},
    {'title': 'Spotify',               'amount':  200, 'category': 'Subscriptions',   'date': date(2026, 2, 5)},
    {'title': 'Cloud storage',         'amount':  250, 'category': 'Subscriptions',   'date': date(2026, 2, 5)},

    # Housing / Rent — 15,000 total
    {'title': 'Monthly rent',          'amount':13000, 'category': 'Housing / Rent',  'date': date(2026, 2, 1)},
    {'title': 'Electricity bill',      'amount': 1200, 'category': 'Housing / Rent',  'date': date(2026, 2, 10)},
    {'title': 'Water & internet',      'amount':  800, 'category': 'Housing / Rent',  'date': date(2026, 2, 10)},

    # Education — 2,500 total (disappears in March)
    {'title': 'Online course fee',     'amount': 1500, 'category': 'Education',       'date': date(2026, 2, 3)},
    {'title': 'Textbooks',             'amount':  700, 'category': 'Education',       'date': date(2026, 2, 10)},
    {'title': 'Workshop registration', 'amount':  300, 'category': 'Education',       'date': date(2026, 2, 17)},

    # ---- MARCH 2026 (subject month) ----

    # Food — 12,400 total (+45.9%)
    {'title': 'Grocery run',           'amount': 2800, 'category': 'Food',            'date': date(2026, 3, 2)},
    {'title': 'Holi celebration food', 'amount': 2500, 'category': 'Food',            'date': date(2026, 3, 8)},
    {'title': 'Lunch at office',       'amount': 1100, 'category': 'Food',            'date': date(2026, 3, 12)},
    {'title': 'Grocery run',           'amount': 2200, 'category': 'Food',            'date': date(2026, 3, 18)},
    {'title': 'Family dinner out',     'amount': 2400, 'category': 'Food',            'date': date(2026, 3, 23)},
    {'title': 'Snacks & beverages',    'amount':  700, 'category': 'Food',            'date': date(2026, 3, 28)},
    {'title': 'Late night snacks',     'amount':  700, 'category': 'Food',            'date': date(2026, 3, 30)},

    # Transportation — 2,100 total (-34.4%)
    {'title': 'Monthly bus pass',      'amount': 1200, 'category': 'Transportation',  'date': date(2026, 3, 1)},
    {'title': 'Fuel',                  'amount':  600, 'category': 'Transportation',  'date': date(2026, 3, 15)},
    {'title': 'Ride share',            'amount':  300, 'category': 'Transportation',  'date': date(2026, 3, 27)},

    # Entertainment — 3,800 total (+90.0%)
    {'title': 'Holi party expenses',   'amount': 1500, 'category': 'Entertainment',   'date': date(2026, 3, 7)},
    {'title': 'Cinema tickets',        'amount':  700, 'category': 'Entertainment',   'date': date(2026, 3, 14)},
    {'title': 'Live music event',      'amount': 1200, 'category': 'Entertainment',   'date': date(2026, 3, 21)},
    {'title': 'Bowling night',         'amount':  400, 'category': 'Entertainment',   'date': date(2026, 3, 28)},

    # Health & Fitness — 1,600 total (+6.7%)
    {'title': 'Gym membership',        'amount':  900, 'category': 'Health & Fitness','date': date(2026, 3, 1)},
    {'title': 'Pharmacy',              'amount':  450, 'category': 'Health & Fitness','date': date(2026, 3, 11)},
    {'title': 'Yoga class',            'amount':  250, 'category': 'Health & Fitness','date': date(2026, 3, 20)},

    # Shopping — 4,200 total (-6.7%)
    {'title': 'Clothing',              'amount': 2200, 'category': 'Shopping',        'date': date(2026, 3, 5)},
    {'title': 'Household supplies',    'amount': 1200, 'category': 'Shopping',        'date': date(2026, 3, 15)},
    {'title': 'Books',                 'amount':  800, 'category': 'Shopping',        'date': date(2026, 3, 25)},

    # Subscriptions — 800 total (flat)
    {'title': 'Netflix',               'amount':  350, 'category': 'Subscriptions',   'date': date(2026, 3, 5)},
    {'title': 'Spotify',               'amount':  200, 'category': 'Subscriptions',   'date': date(2026, 3, 5)},
    {'title': 'Cloud storage',         'amount':  250, 'category': 'Subscriptions',   'date': date(2026, 3, 5)},

    # Housing / Rent — 15,000 total (flat)
    {'title': 'Monthly rent',          'amount':13000, 'category': 'Housing / Rent',  'date': date(2026, 3, 1)},
    {'title': 'Electricity bill',      'amount': 1300, 'category': 'Housing / Rent',  'date': date(2026, 3, 10)},
    {'title': 'Water & internet',      'amount':  700, 'category': 'Housing / Rent',  'date': date(2026, 3, 10)},

    # Miscellaneous — 1,200 total (new in March, no baseline)
    {'title': 'Emergency car repair',  'amount':  800, 'category': 'Miscellaneous',   'date': date(2026, 3, 9)},
    {'title': 'Gift for friend',       'amount':  400, 'category': 'Miscellaneous',   'date': date(2026, 3, 22)},

    # Education — intentionally absent in March (disappears from subject month)
]


class Command(BaseCommand):
    help = (
        'Seed the transaction table with two months of realistic NRS expense data '
        '(February and March 2026) for the first superuser. '
        'Used to test the Insight Engine end-to-end.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Re-seed even if transactions already exist for the target user in the target months.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would be created without touching the database.',
        )

    def handle(self, *args, **options):
        force   = options['force']
        dry_run = options['dry_run']

        # --- Resolve target user ---
        user = User.objects.filter(is_superuser=True).order_by('id').first()
        if not user:
            raise CommandError(
                'No superuser found. Run "python manage.py createsuperuser" first.'
            )
        self.stdout.write(f"Target user: '{user.username}' (id={user.id})")

        # --- Resolve NRS currency ---
        currency = Currency.objects.filter(code='NRS').first()
        if not currency:
            self.stdout.write(self.style.WARNING(
                '  [warn] NRS currency not found — transactions will have currency=NULL. '
                'Run "python manage.py seed_currencies" to fix.'
            ))

        # --- Guard against double-seeding ---
        if not force:
            existing = Transaction.objects.filter(
                user=user,
                date__gte=date(2026, 2, 1),
                date__lte=date(2026, 3, 31),
            ).count()
            if existing:
                self.stdout.write(self.style.WARNING(
                    f'\n  [skip] {existing} transaction(s) already exist for this user in '
                    f'Feb–Mar 2026. Use --force to re-seed.\n'
                ))
                return

        # --- Build category lookup ---
        categories = {c.name: c for c in Category.objects.filter(user__isnull=True)}
        missing = {t['category'] for t in TRANSACTIONS} - set(categories.keys())
        if missing:
            raise CommandError(
                f'Missing categories in DB: {missing}. '
                f'Run "python manage.py seed_categories" first.'
            )

        # --- Dry run ---
        if dry_run:
            self.stdout.write(self.style.WARNING('\n[dry-run] No changes will be made.\n'))
            for t in TRANSACTIONS:
                self.stdout.write(f"  {t['date']}  {t['category']:<20}  {t['amount']:>8,}  {t['title']}")
            self.stdout.write(f'\n  Total: {len(TRANSACTIONS)} transactions')
            return

        # --- Delete existing if --force ---
        if force:
            deleted, _ = Transaction.objects.filter(
                user=user,
                date__gte=date(2026, 2, 1),
                date__lte=date(2026, 3, 31),
            ).delete()
            if deleted:
                self.stdout.write(self.style.WARNING(f'  [force] Deleted {deleted} existing transaction(s).'))

        # --- Create transactions ---
        created = 0
        for t in TRANSACTIONS:
            Transaction.objects.create(
                user=user,
                title=t['title'],
                amount=t['amount'],
                transaction_type='expense',
                category=categories[t['category']],
                currency=currency,
                date=t['date'],
            )
            created += 1

        # --- Summary table ---
        self.stdout.write(self.style.SUCCESS(f'\n  Created {created} transactions.\n'))
        self.stdout.write(f"  {'Category':<22} {'Feb 2026':>10} {'Mar 2026':>10} {'Variance':>10}")
        self.stdout.write(f"  {'-'*56}")

        feb_totals = {}
        mar_totals = {}
        for t in TRANSACTIONS:
            bucket = feb_totals if t['date'].month == 2 else mar_totals
            bucket[t['category']] = bucket.get(t['category'], 0) + t['amount']

        all_cats = sorted(set(feb_totals) | set(mar_totals))
        for cat in all_cats:
            feb = feb_totals.get(cat, 0)
            mar = mar_totals.get(cat, 0)
            if feb:
                var = f"{(mar - feb) / feb * 100:+.1f}%"
            else:
                var = 'new'
            self.stdout.write(f"  {cat:<22} {feb:>10,} {mar:>10,} {var:>10}")

        feb_total = sum(feb_totals.values())
        mar_total = sum(mar_totals.values())
        total_var = f"{(mar_total - feb_total) / feb_total * 100:+.1f}%"
        self.stdout.write(f"  {'-'*56}")
        self.stdout.write(f"  {'TOTAL':<22} {feb_total:>10,} {mar_total:>10,} {total_var:>10}")

        logger.info(
            f"seed_transactions complete — user='{user.username}' (id={user.id}) "
            f"| created={created} | feb_total={feb_total} | mar_total={mar_total}"
        )
