import logging

logger = logging.getLogger(__name__)


def send_payment_reminder(user, recurring_payment):
    """
    Send a push notification to the user reminding them of an upcoming payment.

    Args:
        user: The User instance to notify.
        recurring_payment: The RecurringPayment instance that is due soon.

    TODO: Integrate with Firebase Cloud Messaging (FCM).
          Steps to implement:
          1. Install `firebase-admin` via pip and add to requirements.txt
          2. Add FCM credentials (service account JSON) to settings via env var
          3. Store the user's FCM device token on the User model or a DeviceToken model
          4. Replace the stub log below with an actual FCM send call:

             import firebase_admin.messaging as fcm
             message = fcm.Message(
                 notification=fcm.Notification(
                     title='Payment Due Soon',
                     body=f"{recurring_payment.title} is due on {recurring_payment.next_due_date}",
                 ),
                 token=user.fcm_token,
             )
             fcm.send(message)
    """
    logger.info(
        f"[STUB] Payment reminder: '{recurring_payment.title}' "
        f"due {recurring_payment.next_due_date} "
        f"(amount={recurring_payment.amount}) "
        f"→ user '{user.username}' (id={user.id})"
    )
