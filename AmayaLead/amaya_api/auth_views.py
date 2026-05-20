from django.contrib.auth.models import User
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

    user.set_password(new)
    user.save()

    # Issue a fresh token pair so the user doesn't get logged out
    refresh = RefreshToken.for_user(user)
    return Response({
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    })


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
