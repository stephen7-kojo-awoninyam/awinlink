from django.apps import AppConfig


class RecommendationsConfig(AppConfig):
    name = 'recommendations'

    def ready(self):
        from . import rising_signals  # noqa: F401
