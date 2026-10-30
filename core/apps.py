from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.db.models.signals import pre_migrate
        from config.migration_safety import preflight_reverse
        pre_migrate.connect(preflight_reverse, sender=self, dispatch_uid='awinlink.reverse_plan_preflight')
