from django.core.management.base import BaseCommand

from accounts.auth_defaults import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, reset_default_admin_password


class Command(BaseCommand):
    help = "Reset or recreate the local Matokeo RMS recovery admin account."

    def handle(self, *args, **options):
        user, created = reset_default_admin_password()
        action = "created" if created else "reset"
        self.stdout.write(
            self.style.SUCCESS(
                f"Admin account {action}: {user.username} / {DEFAULT_ADMIN_PASSWORD}"
            )
        )
        self.stdout.write(
            f"Sign in as {DEFAULT_ADMIN_USERNAME} and change this password in Settings > Users."
        )
