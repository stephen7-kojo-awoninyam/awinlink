from django.apps import AppConfig


class MediaErasureConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'media_erasure'
    verbose_name = 'Media retention and erasure queue'
