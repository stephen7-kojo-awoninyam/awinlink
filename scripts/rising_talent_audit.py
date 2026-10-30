"""Run tests in a disposable DB on the verified workspace-only PostgreSQL cluster."""
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.rising_talent_test_settings"

import psycopg2

with psycopg2.connect(host="127.0.0.1", port=55432, user="vc_audit", dbname="postgres", connect_timeout=3) as probe:
    with probe.cursor() as cursor:
        cursor.execute("SHOW data_directory")
        if Path(cursor.fetchone()[0]).resolve() != (ROOT / ".audit-vc-tools/postgres-data").resolve():
            raise RuntimeError("Refusing to test against a PostgreSQL cluster outside the workspace audit directory.")

from django.conf import settings

settings.DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "127.0.0.1",
    "PORT": 55432, "USER": "vc_audit", "NAME": "postgres",
    "TEST": {"NAME": "test_awinlink_rising_" + uuid4().hex}}}

import django
django.setup()
from django.core.management import call_command

labels = sys.argv[1:] or ["recommendations.test_rising_talent", "recommendations.test_rising_talent_audit"]
call_command("test", *labels, interactive=False, verbosity=1)
