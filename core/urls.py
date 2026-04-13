from rest_framework.routers import DefaultRouter
from .views import CurrencyViewSet, CategoryViewSet, TransactionViewSet, BudgetViewSet

router = DefaultRouter()
router.register(r'currencies', CurrencyViewSet, basename='currency')
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'transactions', TransactionViewSet, basename='transaction')
router.register(r'budgets', BudgetViewSet, basename='budget')

urlpatterns = router.urls
