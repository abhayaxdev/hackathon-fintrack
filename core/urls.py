from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    CurrencyViewSet,
    CategoryViewSet,
    TransactionViewSet,
    BudgetViewSet,
    RecurringPaymentViewSet,
    PaymentHistoryViewSet,
    InsightView,
)

router = DefaultRouter()
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'budgets', BudgetViewSet, basename='budget')
router.register(r'recurring-payments', RecurringPaymentViewSet, basename='recurring-payment')
router.register(r'payment-history', PaymentHistoryViewSet, basename='payment-history')

urlpatterns = router.urls + [
    path('insights/', InsightView.as_view(), name='insights'),
]
