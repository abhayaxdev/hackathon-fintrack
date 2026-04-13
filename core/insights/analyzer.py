import logging
import calendar
from decimal import Decimal
from datetime import date

from dateutil.relativedelta import relativedelta
from django.db.models import Sum

from core.models import Transaction

logger = logging.getLogger(__name__)


class SpendingAnalyzer:
    """
    Compares a user's spending per category between two consecutive complete months:
      - subject_month  : the last complete calendar month
      - baseline_month : the month before the subject

    All aggregation is done at the database level using .values().annotate(Sum).
    No Transaction instances are loaded into memory.
    """

    def __init__(self, user, reference_date: date = None):
        self.user = user
        self.today = reference_date or date.today()

        # Subject month: last complete calendar month
        subject_first = date(self.today.year, self.today.month, 1) - relativedelta(months=1)
        subject_last_day = calendar.monthrange(subject_first.year, subject_first.month)[1]
        self.subject_start = subject_first
        self.subject_end = date(subject_first.year, subject_first.month, subject_last_day)

        # Baseline month: the month before subject
        baseline_first = self.subject_start - relativedelta(months=1)
        baseline_last_day = calendar.monthrange(baseline_first.year, baseline_first.month)[1]
        self.baseline_start = baseline_first
        self.baseline_end = date(baseline_first.year, baseline_first.month, baseline_last_day)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query_month(self, start: date, end: date) -> dict:
        """
        Returns {category_name: Decimal(total)} for expense transactions
        in [start, end] for self.user.
        Category name falls back to 'Uncategorised' when category is NULL.
        """
        rows = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='expense',
                date__gte=start,
                date__lte=end,
            )
            .values('category__name')
            .annotate(total=Sum('amount'))
        )
        return {
            (row['category__name'] or 'Uncategorised'): row['total']
            for row in rows
        }

    @staticmethod
    def _variance_pct(current: Decimal, baseline: Decimal) -> float | None:
        """
        Percentage change from baseline to current.
        Returns None when the baseline is zero (new category — no prior data).
        """
        if baseline == 0:
            return None
        return float(round((current - baseline) / baseline * 100, 2))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute both queries, compute per-category variances, and return
        a structured summary packet ready for the LLM connector and API response.
        """
        logger.info(
            f"SpendingAnalyzer.run — user='{self.user.username}' (id={self.user.id}) "
            f"| subject={self.subject_start}→{self.subject_end} "
            f"| baseline={self.baseline_start}→{self.baseline_end}"
        )

        subject_data  = self._query_month(self.subject_start,  self.subject_end)
        baseline_data = self._query_month(self.baseline_start, self.baseline_end)

        # Union of all category names across both months
        all_categories = set(subject_data.keys()) | set(baseline_data.keys())

        if not all_categories:
            logger.warning(
                f"SpendingAnalyzer: no transaction data found for user '{self.user.username}' "
                f"in subject or baseline month."
            )
            return self._empty_packet()

        category_rows = []
        for name in sorted(all_categories):
            this_month = subject_data.get(name, Decimal('0.00'))
            last_month = baseline_data.get(name, Decimal('0.00'))
            variance   = self._variance_pct(this_month, last_month)

            category_rows.append({
                'category':      name,
                'this_month':    float(this_month),
                'last_month':    float(last_month),
                'variance_pct':  variance,   # None means new category (no baseline)
            })

        # Overall totals
        total_this  = sum(subject_data.values(),  Decimal('0.00'))
        total_last  = sum(baseline_data.values(), Decimal('0.00'))
        total_var   = self._variance_pct(total_this, total_last)

        packet = {
            'subject_month':       self.subject_start.strftime('%Y-%m'),
            'baseline_month':      self.baseline_start.strftime('%Y-%m'),
            'total_this_month':    float(total_this),
            'total_last_month':    float(total_last),
            'total_variance_pct':  total_var,
            'categories':          category_rows,
        }

        logger.info(
            f"SpendingAnalyzer complete — {len(category_rows)} categories | "
            f"total_this={total_this} total_last={total_last} variance={total_var}%"
        )
        return packet

    def _empty_packet(self) -> dict:
        return {
            'subject_month':      self.subject_start.strftime('%Y-%m'),
            'baseline_month':     self.baseline_start.strftime('%Y-%m'),
            'total_this_month':   0.0,
            'total_last_month':   0.0,
            'total_variance_pct': None,
            'categories':         [],
        }
