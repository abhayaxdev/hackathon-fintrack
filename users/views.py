import logging

from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from drf_spectacular.utils import extend_schema, inline_serializer

from .serializers import RegisterSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)


class _LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(help_text='Refresh token to blacklist.')

logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — public endpoint to create a new account."""
    serializer_class = RegisterSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info(f"New user registered: '{user.username}' (id={user.id}, email={user.email})")
        return Response(
            {'detail': 'Account created successfully.', 'user': serializer.data},
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ — returns access + refresh JWT tokens."""
    permission_classes = (permissions.AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])
        except Exception:
            username = request.data.get('username', '<unknown>')
            logger.warning(f"Failed login attempt for username: '{username}' from IP: {_get_client_ip(request)}")
            raise

        username = request.data.get('username', '<unknown>')
        logger.info(f"User logged in: '{username}' from IP: {_get_client_ip(request)}")
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RefreshTokenView(TokenRefreshView):
    """POST /api/auth/token/refresh/ — rotate refresh token and return new access token."""

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            logger.warning(f"Token refresh failed: {e} from IP: {_get_client_ip(request)}")
            raise InvalidToken(e.args[0])

        logger.info(f"Token refreshed successfully from IP: {_get_client_ip(request)}")
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    """POST /api/auth/logout/ — blacklist the refresh token to invalidate the session."""
    permission_classes = (permissions.IsAuthenticated,)
    serializer_class = _LogoutRequestSerializer

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info(f"User logged out: '{request.user.username}' (id={request.user.id})")
            return Response({'detail': 'Successfully logged out.'}, status=status.HTTP_200_OK)
        except TokenError as e:
            logger.warning(
                f"Logout failed for user '{request.user.username}' — invalid/expired token: {e}"
            )
            return Response({'detail': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/auth/me/ — view and update own profile."""
    serializer_class = UserProfileSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        logger.info(f"Profile fetched for user: '{request.user.username}' (id={request.user.id})")
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        response = super().update(request, *args, **kwargs)
        logger.info(
            f"Profile updated for user: '{request.user.username}' (id={request.user.id}) "
            f"— fields: {list(request.data.keys())}"
        )
        return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')
