import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import RecurringPayment, PaymentHistory
from core.notifications import send_payment_reminder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Mark overdue recurring payments as missed and send reminders for upcoming ones. '
        'Designed to be run daily via cron or a task scheduler.'
    )

    def handle(self, *args, **kwargs):
        today = timezone.localdate()
        missed_count = 0
        reminder_count = 0

        active_payments = RecurringPayment.objects.filter(is_active=True).select_related('user')

        for payment in active_payments:

            # --- Missed payment detection ---
            # A payment is overdue if next_due_date is before today and no
            # PaymentHistory entry exists for that due date
            if payment.next_due_date < today:
                already_logged = PaymentHistory.objects.filter(
                    recurring_payment=payment,
                    paid_on=payment.next_due_date,
                ).exists()

                if not already_logged:
                    PaymentHistory.objects.create(
                        recurring_payment=payment,
                        paid_on=payment.next_due_date,
                        amount=payment.amount,
                        status='missed',
                    )
                    missed_count += 1
                    logger.warning(
                        f"Missed payment recorded: '{payment.title}' (id={payment.id}) "
                        f"due {payment.next_due_date} "
                        f"| user='{payment.user.username}' (id={payment.user.id})"
                    )
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [missed]   '{payment.title}' — due {payment.next_due_date} "
                            f"(user: {payment.user.username})"
                        )
                    )

                    # Advance next_due_date so this payment is not flagged again tomorrow
                    payment.next_due_date = payment._calculate_next_due(payment.next_due_date)
                    payment.save()

            # --- Reminder detection ---
            # Notify the user if next_due_date falls within reminder_days_before from today
            elif (payment.next_due_date - today).days <= payment.reminder_days_before:
                send_payment_reminder(payment.user, payment)
                reminder_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  [reminder] '{payment.title}' — due {payment.next_due_date} "
                        f"in {(payment.next_due_date - today).days} day(s) "
                        f"(user: {payment.user.username})"
                    )
                )

        summary = (
            f"\nDone. {missed_count} missed payment(s) recorded, "
            f"{reminder_count} reminder(s) sent."
        )
        logger.info(
            f"mark_missed_payments complete — missed={missed_count}, reminders={reminder_count}"
        )
        self.stdout.write(self.style.SUCCESS(summary))
