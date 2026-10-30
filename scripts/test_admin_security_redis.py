"""Start a memory-only, password-protected loopback Redis fixture; never use REDIS_URL."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
executable = next((ROOT / '.audit-vc-tools/redis').rglob('redis-server.exe'), None)
if executable is None or not executable.resolve().is_relative_to(ROOT):
    raise RuntimeError('The workspace Redis test binary is required; no service was contacted.')
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
with tempfile.TemporaryDirectory(prefix='.audit-admin-security-', dir=ROOT) as directory:
    if not Path(directory).resolve().is_relative_to(ROOT):
        raise RuntimeError('Fixture directory must remain inside the workspace.')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
    password = uuid4().hex
    process = None
    client = redis.Redis(host='127.0.0.1', port=port, password=password, socket_timeout=2,
                        socket_connect_timeout=2, retry=Retry(NoBackoff(), 0))
    run_id = None
    with open(Path(directory) / 'redis.log', 'ab') as log:
        try:
            process = subprocess.Popen([str(executable), '--bind', '127.0.0.1', '--port', str(port),
                '--protected-mode', 'yes', '--requirepass', password, '--save', '', '--appendonly', 'no',
                '--dir', directory, '--maxmemory', '64mb'], cwd=executable.parent, stdout=log, stderr=log, creationflags=HIDDEN)
            for _ in range(50):
                if process.poll() is not None:
                    raise RuntimeError('Isolated Redis fixture exited before startup.')
                try:
                    if client.ping():
                        run_id = client.info('server')['run_id']; break
                except redis.RedisError:
                    time.sleep(.1)
            if run_id is None:
                raise RuntimeError('Isolated Redis fixture did not start.')
            environment = os.environ.copy()
            environment.update(AWINLINK_SECURITY_TEST_REDIS_URL=f'redis://:{password}@127.0.0.1:{port}/0',
                AWINLINK_SECURITY_TEST_PREFIX='awinlink-admin-test-' + uuid4().hex,
                AWINLINK_SECURITY_TEST_FIXED_TIME=str(int(time.time())))
            labels = sys.argv[1:] or ['accounts.test_admin_login.SharedAdminRedisTests']
            print('Running isolated Redis security tests.', flush=True)
            result = subprocess.run([sys.executable, '-u', '-B', 'scripts/test_security_phase1.py',
                *labels, '--fast'], cwd=ROOT, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180, creationflags=HIDDEN)
            print(result.stdout.replace(password, '[redacted]'), flush=True)
        finally:
            if run_id and process and process.poll() is None:
                try:
                    if client.info('server')['run_id'] == run_id:
                        client.shutdown(nosave=True)
                except redis.RedisError:
                    pass
            client.close()
            if process and process.poll() is None:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.terminate(); process.wait(timeout=5)
    raise SystemExit(result.returncode)
