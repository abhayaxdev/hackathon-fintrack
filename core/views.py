import logging

from django.db.models import Sum, Q
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Currency, Category, Transaction, Budget, RecurringPayment, PaymentHistory
from .serializers import (
    CurrencySerializer,
    CategorySerializer,
    TransactionSerializer,
    BudgetSerializer,
    RecurringPaymentSerializer,
    PaymentHistorySerializer,
)
from .insights.pipeline import run_insight_engine
# from .notifications import send_payment_reminder

logger = logging.getLogger(__name__)

# Common query params shared by transaction list and summary
_TRANSACTION_FILTERS = [
    OpenApiParameter('date_from', OpenApiTypes.DATE, description='Filter from date (YYYY-MM-DD)'),
    OpenApiParameter('date_to', OpenApiTypes.DATE, description='Filter to date (YYYY-MM-DD)'),
    OpenApiParameter('transaction_type', OpenApiTypes.STR, enum=['income', 'expense'], description='Filter by type'),
    OpenApiParameter('category', OpenApiTypes.INT, description='Filter by category ID'),
]


@extend_schema_view(
    list=extend_schema(summary='List all currencies'),
    retrieve=extend_schema(summary='Retrieve a currency'),
)


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    permission_classes = (permissions.AllowAny,)


@extend_schema_view(
    list=extend_schema(summary='List categories (system defaults + own)'),
    create=extend_schema(summary='Create a custom category'),
    retrieve=extend_schema(summary='Retrieve a category'),
    update=extend_schema(summary='Update own category'),
    partial_update=extend_schema(summary='Partially update own category'),
    destroy=extend_schema(summary='Delete own category'),
)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        # Guard for schema generation (no request context available)
        if getattr(self, 'swagger_fake_view', False):
            return Category.objects.none()
        # Return system-wide defaults (user=None) + categories owned by the current user
        return Category.objects.filter(
            Q(user__isnull=True) | Q(user=self.request.user)
        )

    def perform_create(self, serializer):
        category = serializer.save(user=self.request.user)
        logger.info(
            f"Category created: '{category.name}' ({category.category_type}) "
            f"by user '{self.request.user.username}' (id={self.request.user.id})"
        )

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.is_default or category.user is None:
            logger.warning(
                f"User '{request.user.username}' attempted to delete system default "
                f"category '{category.name}' (id={category.id})"
            )
            return Response(
                {'detail': 'System default categories cannot be deleted.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if category.user != request.user:
            logger.warning(
                f"User '{request.user.username}' attempted to delete category "
                f"'{category.name}' (id={category.id}) owned by another user."
            )
            return Response(
                {'detail': 'You do not have permission to delete this category.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        logger.warning(
            f"Category deleted: '{category.name}' (id={category.id}) "
            f"by user '{request.user.username}' (id={request.user.id})"
        )
        return super().destroy(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        category = self.get_object()
        if category.user != request.user:
            return Response(
                {'detail': 'You can only edit your own categories.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(summary='List own transactions', parameters=_TRANSACTION_FILTERS),
    create=extend_schema(summary='Create a transaction'),
    retrieve=extend_schema(summary='Retrieve a transaction'),
    update=extend_schema(summary='Update a transaction'),
    partial_update=extend_schema(summary='Partially update a transaction'),
    destroy=extend_schema(summary='Delete a transaction'),
)
class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Transaction.objects.none()
        qs = Transaction.objects.filter(user=self.request.user).select_related(
            'category', 'currency'
        )
        params = self.request.query_params

        date_from = params.get('date_from')
        date_to = params.get('date_to')
        transaction_type = params.get('transaction_type')
        category_id = params.get('category')

        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if transaction_type:
            qs = qs.filter(transaction_type=transaction_type)
        if category_id:
            qs = qs.filter(category_id=category_id)

        return qs

    def perform_create(self, serializer):
        transaction = serializer.save(user=self.request.user)
        logger.info(
            f"Transaction created: '{transaction.title}' | {transaction.transaction_type} "
            f"| amount={transaction.amount} | date={transaction.date} "
            f"| user='{self.request.user.username}' (id={self.request.user.id})"
        )

    @extend_schema(
        summary='Transaction summary — totals for income, expense and net',
        parameters=_TRANSACTION_FILTERS,
    )
    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        GET /api/transactions/summary/
        Returns total income, total expense, and net for the filtered period.
        Supports the same query params as the list endpoint.
        """
        qs = self.get_queryset()

        totals = qs.aggregate(
            total_income=Sum('amount', filter=Q(transaction_type='income')),
            total_expense=Sum('amount', filter=Q(transaction_type='expense')),
        )

        total_income = totals['total_income'] or 0
        total_expense = totals['total_expense'] or 0
        net = total_income - total_expense

        params = request.query_params
        logger.info(
            f"Transaction summary requested by '{request.user.username}' (id={request.user.id}) "
            f"| filters: date_from={params.get('date_from')} date_to={params.get('date_to')} "
            f"type={params.get('transaction_type')} category={params.get('category')}"
        )

        return Response({
            'total_income': str(total_income),
            'total_expense': str(total_expense),
            'net': str(net),
            'filters': {
                'date_from': params.get('date_from'),
                'date_to': params.get('date_to'),
                'transaction_type': params.get('transaction_type'),
                'category': params.get('category'),
            }
        })


@extend_schema_view(
    list=extend_schema(summary='List own budgets'),
    create=extend_schema(summary='Create a budget'),
    retrieve=extend_schema(summary='Retrieve a budget'),
    update=extend_schema(summary='Update a budget'),
    partial_update=extend_schema(summary='Partially update a budget'),
    destroy=extend_schema(summary='Delete a budget'),
)
class BudgetViewSet(viewsets.ModelViewSet):
    serializer_class = BudgetSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Budget.objects.none()
        return Budget.objects.filter(user=self.request.user).select_related('currency')

    def perform_create(self, serializer):
        budget = serializer.save(user=self.request.user)
        logger.info(
            f"Budget created: limit={budget.amount_limit} | "
            f"{budget.start_date} to {budget.end_date} | "
            f"user='{self.request.user.username}' (id={self.request.user.id})"
        )

    def perform_update(self, serializer):
        budget = serializer.save()
        logger.info(
            f"Budget updated: id={budget.id} | limit={budget.amount_limit} | "
            f"{budget.start_date} to {budget.end_date} | "
            f"user='{self.request.user.username}' (id={self.request.user.id})"
        )


@extend_schema_view(
    list=extend_schema(
        summary='List own recurring payments',
        parameters=[OpenApiParameter('is_active', OpenApiTypes.BOOL, description='Filter by active status')],
    ),
    create=extend_schema(summary='Create a recurring payment'),
    retrieve=extend_schema(summary='Retrieve a recurring payment'),
    update=extend_schema(summary='Update a recurring payment'),
    partial_update=extend_schema(summary='Partially update a recurring payment'),
    destroy=extend_schema(summary='Delete a recurring payment'),
)
class RecurringPaymentViewSet(viewsets.ModelViewSet):
    serializer_class = RecurringPaymentSerializer
    permission_classes = (permissions.IsAuthenticated,)

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

    def perform_create(self, serializer):
        payment = serializer.save(user=self.request.user)
        logger.info(
            f"RecurringPayment created: '{payment.title}' | frequency={payment.frequency} "
            f"| amount={payment.amount} | next_due={payment.next_due_date} "
            f"| user='{self.request.user.username}' (id={self.request.user.id})"
        )

    @extend_schema(
        summary='Mark a recurring payment as paid',
        request=None,
        responses={200: RecurringPaymentSerializer},
    )
    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        """
        POST /api/recurring-payments/{id}/mark-paid/

        - Creates a PaymentHistory entry with status='paid'
        - Increments completed_installments
        - Advances next_due_date by one frequency period
        - Auto-creates a Transaction record in the user's history
        - Triggers auto-deactivation if EMI is complete (via model save())
        """
        payment = self.get_object()

        if not payment.is_active:
            return Response(
                {'detail': 'This recurring payment is no longer active.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()

        # Create PaymentHistory entry
        PaymentHistory.objects.create(
            recurring_payment=payment,
            paid_on=today,
            amount=payment.amount,
            status='paid',
        )

        # Auto-create a Transaction so it appears in the user's transaction history
        Transaction.objects.create(
            user=request.user,
            title=payment.title,
            amount=payment.amount,
            transaction_type='expense',
            category=payment.category,
            currency=payment.currency,
            date=today,
            note=f'Auto-created from recurring payment: {payment.title}',
        )

        # Advance installment count and next due date
        payment.completed_installments += 1
        payment.next_due_date = payment._calculate_next_due(payment.next_due_date)
        payment.save()  # model save() handles auto-deactivation

        logger.info(
            f"RecurringPayment marked paid: '{payment.title}' (id={payment.id}) "
            f"| installment {payment.completed_installments}/{payment.total_installments or '∞'} "
            f"| next_due={payment.next_due_date} "
            f"| user='{request.user.username}' (id={request.user.id})"
        )

        serializer = self.get_serializer(payment)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        summary='List payment history for own recurring payments',
        parameters=[OpenApiParameter('recurring_payment', OpenApiTypes.INT, description='Filter by recurring payment ID')],
    ),
    retrieve=extend_schema(summary='Retrieve a payment history entry'),
)
class PaymentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentHistorySerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return PaymentHistory.objects.none()
        qs = PaymentHistory.objects.filter(
            recurring_payment__user=self.request.user
        ).select_related('recurring_payment')

        recurring_id = self.request.query_params.get('recurring_payment')
        if recurring_id:
            qs = qs.filter(recurring_payment_id=recurring_id)
        return qs


@extend_schema(
    summary='Monthly spending insight — LLM narrative + per-category analysis',
    responses={
        200: {
            'type': 'object',
            'properties': {
                'narrative':     {'type': 'string'},
                'analysis':      {'type': 'object'},
                'cached':        {'type': 'boolean'},
                'used_fallback': {'type': 'boolean'},
            },
        }
    },
)
class InsightView(APIView):
    """
    GET /api/insights/

    Runs the monthly Insight Engine for the authenticated user.

    Returns:
      - narrative      : LLM-generated (or fallback) conversational summary
      - analysis       : structured summary packet (subject/baseline month,
                         per-category spend + variance) for chart rendering
      - cached         : whether this response was served from the 24-hour cache
      - used_fallback  : whether the LLM was unavailable and the generic tip was used
    """
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        result = run_insight_engine(request.user)
        logger.info(
            f"InsightView: response served — user='{request.user.username}' (id={request.user.id}) "
            f"| cached={result['cached']} | used_fallback={result['used_fallback']}"
        )
        return Response(result, status=status.HTTP_200_OK)
