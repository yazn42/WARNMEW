from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from .models import UserProfile, DailyDiseaseRecord


@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    Register a new user with role.
    POST: { username, email, password, role, organization (optional) }
    """
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')
    role = request.data.get('role', 'researcher')
    organization = request.data.get('organization', '')

    if not username or not email or not password:
        return Response(
            {"error": "username, email, and password are required."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(username=username).exists():
        return Response(
            {"error": "Username already exists."},
            status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {"error": "Email already registered."},
            status=status.HTTP_400_BAD_REQUEST
        )

    valid_roles = ['admin', 'researcher', 'health_authority']
    if role not in valid_roles:
        return Response(
            {"error": f"Invalid role. Must be one of: {', '.join(valid_roles)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    user = User.objects.create_user(
        username=username,
        email=email,
        password=password
    )

    # Update the auto-created profile
    profile = user.profile
    profile.role = role
    profile.organization = organization
    profile.save()

    return Response({
        "message": "Registration successful.",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": profile.role,
            "organization": profile.organization
        }
    }, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """
    Get current user's profile info.
    """
    user = request.user
    try:
        profile = user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=user)

    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": profile.role,
        "role_display": profile.get_role_display(),
        "organization": profile.organization,
        "date_joined": user.date_joined
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def get_districts(request):
    """
    Return list of all districts available in the database.
    """
    districts = (
        DailyDiseaseRecord.objects
        .order_by('district')
        .values_list('district', flat=True)
        .distinct()
    )
    return Response(list(districts))
