import logging

from django.db.models import Sum, Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Currency, Category, Transaction, Budget
from .serializers import (
    CurrencySerializer,
    CategorySerializer,
    TransactionSerializer,
    BudgetSerializer,
)

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
