from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.auth_defaults import (
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_ADMIN_USERNAME,
    ensure_default_admin_user,
    reset_default_admin_password,
)
from accounts.views import _would_remove_last_active_admin


class AuthDefaultsTests(TestCase):
    def test_default_admin_is_created_only_when_auth_database_is_empty(self):
        user = ensure_default_admin_user()

        self.assertIsNotNone(user)
        self.assertEqual(user.username, DEFAULT_ADMIN_USERNAME)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(DEFAULT_ADMIN_PASSWORD))

        self.assertIsNone(ensure_default_admin_user())

    def test_reset_default_admin_password_recovers_disabled_or_changed_admin(self):
        User = get_user_model()
        admin = User.objects.create_user(username=DEFAULT_ADMIN_USERNAME, password="lost")
        admin.is_active = False
        admin.is_staff = False
        admin.is_superuser = False
        admin.save()

        user, created = reset_default_admin_password()

        self.assertFalse(created)
        self.assertEqual(user.id, admin.id)
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(DEFAULT_ADMIN_PASSWORD))

    def test_login_bootstraps_default_admin_when_no_user_exists(self):
        response = self.client.post(
            "/login/",
            {"username": "admin", "password": DEFAULT_ADMIN_PASSWORD},
        )

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username=DEFAULT_ADMIN_USERNAME)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(DEFAULT_ADMIN_PASSWORD))


class UserLockoutGuardTests(TestCase):
    def test_last_active_admin_cannot_be_disabled_or_demoted(self):
        User = get_user_model()
        admin = User.objects.create_superuser(username="admin", password="admin")

        self.assertTrue(_would_remove_last_active_admin(User, admin, is_active=False))
        self.assertTrue(_would_remove_last_active_admin(User, admin, is_superuser=False))

    def test_admin_can_be_changed_when_another_active_admin_exists(self):
        User = get_user_model()
        admin = User.objects.create_superuser(username="admin", password="admin")
        User.objects.create_superuser(username="backup-admin", password="admin")

        self.assertFalse(_would_remove_last_active_admin(User, admin, is_active=False))
        self.assertFalse(_would_remove_last_active_admin(User, admin, is_superuser=False))
