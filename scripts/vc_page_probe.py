import sys
import json
import time
import faulthandler
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import vc_audit_server
import django
django.setup()
from django.test import Client
from django.conf import settings
fixture = json.loads(vc_audit_server.manifest_path.read_text())
client = Client()
client.cookies[settings.SESSION_COOKIE_NAME] = fixture['identities']['host']['session_cookie']
faulthandler.dump_traceback_later(10, repeat=True)
started = time.monotonic()
response = client.get(f"/learning/sessions/{fixture['session_id']}/classroom/")
print('Classroom page:', response.status_code, 'seconds:', round(time.monotonic() - started, 2))
faulthandler.cancel_dump_traceback_later()
