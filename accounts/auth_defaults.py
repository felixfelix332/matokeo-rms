"""Authentication defaults and local recovery helpers for Matokeo RMS."""

from __future__ import annotations

from django.contrib.auth import get_user_model


DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"


def ensure_default_admin_user():
    """Create the first local admin account when the auth database is empty."""
    user_model = get_user_model()
    if user_model.objects.exists():
        return None
    return user_model.objects.create_superuser(
        username=DEFAULT_ADMIN_USERNAME,
        email="",
        password=DEFAULT_ADMIN_PASSWORD,
    )


def reset_default_admin_password():
    """Reset or recreate the built-in recovery admin account."""
    user_model = get_user_model()
    user, created = user_model.objects.get_or_create(
        username=DEFAULT_ADMIN_USERNAME,
        defaults={
            "email": "",
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        },
    )
    user.is_active = True
    user.is_staff = True
    user.is_superuser = True
    user.set_password(DEFAULT_ADMIN_PASSWORD)
    user.save()
    return user, created


def is_default_admin_password(user) -> bool:
    return (
        bool(user)
        and user.username.lower() == DEFAULT_ADMIN_USERNAME
        and user.check_password(DEFAULT_ADMIN_PASSWORD)
    )
