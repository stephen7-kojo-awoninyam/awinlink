from django.contrib.admin.apps import AdminConfig


class SecureAdminConfig(AdminConfig):
    default_site = 'accounts.admin_site.SecureAdminSite'

    def ready(self):
        super().ready()
        from . import deployment_checks  # noqa: F401
