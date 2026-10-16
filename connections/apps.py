from django.apps import AppConfig


class ConnectionsConfig(AppConfig):
    name = 'connections'

    def ready(self):
        import connections.signals
