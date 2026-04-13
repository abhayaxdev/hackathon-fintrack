from django.urls import path
from .views import RegisterView, LoginView, RefreshTokenView, LogoutView, ProfileView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('token/refresh/', RefreshTokenView.as_view(), name='auth-token-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', ProfileView.as_view(), name='auth-me'),
]
