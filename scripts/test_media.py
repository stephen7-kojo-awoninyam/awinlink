"""Run media regressions against an isolated in-memory database."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
from django.conf import settings

settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
settings.CHANNEL_LAYERS = {'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}}
settings.SECURE_SSL_REDIRECT = False
settings.STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}
import django
django.setup()
from django.core.management import call_command

call_command('test', *(sys.argv[1:] or ['config.test_media', 'config.test_deployment', 'messaging.tests', 'feed.tests']), verbosity=1, interactive=False)
