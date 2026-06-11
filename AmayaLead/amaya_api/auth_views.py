from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
from django_q.tasks import async_task
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError


def _user_dict(user: User) -> dict:
    name = f"{user.first_name} {user.last_name}".strip() or user.username
    return {
        "id": user.id,
        "email": user.email,
        "name": name,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.is_active:
        return Response({"error": "Account is disabled"}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": _user_dict(user),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_token(request):
    token = request.data.get("refresh", "")
    try:
        refresh = RefreshToken(token)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        })
    except TokenError as e:
        return Response({"error": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(_user_dict(request.user))


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    old = request.data.get("old_password", "")
    new = request.data.get("new_password", "")

    if not user.check_password(old):
        return Response({"error": "Current password is incorrect"}, status=status.HTTP_400_BAD_REQUEST)

    if len(new) < 8:
        return Response({"error": "New password must be at least 8 characters"}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new)
    user.save()

    # Issue a fresh token pair so the user doesn't get logged out
    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    """Email a one-time password-reset link. Always answers with the same
    generic message so the endpoint can't be used to probe which emails have
    accounts."""
    email = request.data.get("email", "").strip().lower()
    generic = {"detail": "If an account with that email exists, a reset link has been sent."}
    if not email:
        return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email__iexact=email, is_active=True)
    except User.DoesNotExist:
        return Response(generic)

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    frontend = getattr(settings, "FRONTEND_URL", "https://remedylead.app").rstrip("/")
    link = f"{frontend}/reset-password?uid={uid}&token={token}"

    # Send in the background so response timing doesn't leak account existence
    async_task(
        'django.core.mail.send_mail',
        "Reset your RemedyLead password",
        (
            f"Hi {user.first_name or user.username},\n\n"
            f"Someone requested a password reset for your RemedyLead account.\n"
            f"Click the link below to choose a new password:\n\n{link}\n\n"
            f"If you didn't request this, you can safely ignore this email."
        ),
        None,  # DEFAULT_FROM_EMAIL
        [email],
        task_name=f"Password reset → {email}",
    )
    return Response(generic)


@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password(request):
    """Set a new password from a forgot-password link (uid + token)."""
    uid = request.data.get("uid", "")
    token = request.data.get("token", "")
    new = request.data.get("new_password", "")

    if not uid or not token or not new:
        return Response({"error": "uid, token and new_password are required"}, status=status.HTTP_400_BAD_REQUEST)
    if len(new) < 8:
        return Response({"error": "Password must be at least 8 characters"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)), is_active=True)
    except Exception:
        return Response({"error": "Invalid reset link"}, status=status.HTTP_400_BAD_REQUEST)

    if not default_token_generator.check_token(user, token):
        return Response({"error": "This reset link is invalid or has expired"}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new)
    user.save()
    return Response({"detail": "Password updated — you can now sign in."})


# ── User management (admin only) ──────────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAdminUser])
def users(request):
    if request.method == "GET":
        all_users = User.objects.all().order_by("-date_joined")
        return Response([_user_dict(u) for u in all_users])

    # POST — create user
    email = request.data.get("email", "").strip().lower()
    password = request.data.get("password", "")
    name = request.data.get("name", "")
    is_staff = bool(request.data.get("is_staff", False))

    if not email or not password:
        return Response({"error": "Email and password are required"}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email__iexact=email).exists():
        return Response({"error": "A user with this email already exists"}, status=status.HTTP_400_BAD_REQUEST)

    parts = name.split(" ", 1) if name else []
    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=parts[0] if parts else "",
        last_name=parts[1] if len(parts) > 1 else "",
        is_staff=is_staff,
    )
    return Response(_user_dict(user), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdminUser])
def user_detail(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH
    if "name" in request.data:
        parts = request.data["name"].split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
    if "is_staff" in request.data:
        user.is_staff = bool(request.data["is_staff"])
    if "is_active" in request.data:
        user.is_active = bool(request.data["is_active"])
    if "password" in request.data:
        user.set_password(request.data["password"])
    user.save()
    return Response(_user_dict(user))
