"""Disposable, loopback-only audit services. Never installs Windows services.

PostgreSQL comes from EDB's binary archive. Redis is a checksum-pinned Windows
port of Redis, not evidence of the deployment's Linux Redis configuration.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
import subprocess
import socket
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".audit-vc-tools"
SOURCES = {
    "postgres": ("https://get.enterprisedb.com/postgresql/postgresql-17.11-1-windows-x64-binaries.zip", None),
    "redis": ("https://github.com/redis-windows/redis-windows/releases/download/8.10.2/Redis-8.10.2-Windows-x64-cygwin.zip",
              "6de5cc7f5adbf97b5928b13766383d4ad424626ef3d8b313ffff12d820ec6fc1"),
}
HIDDEN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def download(kind):
    TOOLS.mkdir(exist_ok=True)
    url, expected = SOURCES[kind]
    archive = TOOLS / f"{kind}.zip"
    if not archive.exists():
        print(f"Downloading {kind} portable test archive", flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "Awinlink-VC-local-audit"})
        with urllib.request.urlopen(request, timeout=30) as source, archive.open("xb") as target:
            size = 0
            while block := source.read(1024 * 1024):
                size += len(block)
                if size > 400 * 1024 * 1024:
                    raise RuntimeError("Unexpectedly large archive")
                target.write(block)
        print(f"Downloaded {size} bytes", flush=True)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if expected and digest != expected:
        raise RuntimeError("Portable Redis archive checksum mismatch; execution refused")
    destination = TOOLS / kind
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            if kind == "postgres" and not member.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                continue
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError("Unsafe archive path")
            package.extract(member, destination)
    metadata = {"source": url, "sha256": digest, "checksum_pinned": bool(expected)}
    (TOOLS / f"{kind}-provenance.json").write_text(json.dumps(metadata, indent=2))
    print(f"Prepared {kind} in the workspace; SHA256 {digest}", flush=True)


def run(*args):
    # A Windows daemon can inherit a pipe and keep communicate() waiting after
    # pg_ctl exits. A workspace log gives subprocess.run a finite wait instead.
    log = TOOLS / "bootstrap.log"
    with log.open("w+") as output:
        result = subprocess.run([str(arg) for arg in args], stdout=output, stderr=output,
            creationflags=HIDDEN, timeout=90)
        output.seek(0)
        text = output.read()
    if result.returncode:
        raise RuntimeError(text or f"Audit helper exited {result.returncode}")
    return text


def start():
    import psycopg2
    import redis
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 16379)) == 0:
            raise RuntimeError("Audit Redis port already belongs to another process; start refused")
    binaries = TOOLS / "postgres" / "pgsql" / "bin"
    # Reuse the already installed Python/wheel Microsoft runtimes privately;
    # never install a system-wide redistributable or change the machine PATH.
    for runtime in Path(sys.base_prefix).glob("vcruntime140*.dll"):
        if not (binaries / runtime.name).exists():
            shutil.copy2(runtime, binaries / runtime.name)
    cpp = list((Path(sys.prefix) / "Lib" / "site-packages").glob("msvcp140*.dll"))
    if cpp and not (binaries / "msvcp140.dll").exists():
        shutil.copy2(cpp[0], binaries / "msvcp140.dll")
    data = TOOLS / "postgres-data"
    if not data.exists():
        print(run(binaries / "initdb.exe", "-D", data, "-U", "vc_audit", "--auth=trust", "--encoding=UTF8", "--locale=C"))
        # This cluster exists only for the audit and accepts loopback connections.
        with (data / "postgresql.conf").open("a") as config:
            config.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\n")
    with socket.socket() as probe:
        pg_running = probe.connect_ex(("127.0.0.1", 55432)) == 0
    if pg_running:
        if not (data / "postmaster.pid").exists():
            raise RuntimeError("Audit PostgreSQL port already in use without our PID file")
    else:
        print(run(binaries / "pg_ctl.exe", "-D", data, "-l", TOOLS / "postgres.log", "-w", "start"))
    connection = psycopg2.connect(host="127.0.0.1", port=55432, user="vc_audit", dbname="postgres")
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SHOW data_directory")
        if Path(cursor.fetchone()[0]).resolve() != data.resolve():
            raise RuntimeError("PostgreSQL data directory does not match our audit cluster")
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'awinlink_audit_vc'")
        if cursor.fetchone() is None:
            cursor.execute("CREATE DATABASE awinlink_audit_vc")
    connection.close()
    executable = next((TOOLS / "redis").rglob("redis-server.exe"))
    log = (TOOLS / "redis.log").open("ab")
    process = subprocess.Popen([str(executable), "--bind", "127.0.0.1", "--port", "16379",
        "--protected-mode", "yes", "--save", "", "--appendonly", "no"], cwd=executable.parent,
        stdout=log, stderr=log, creationflags=HIDDEN)
    log.close()
    client = redis.Redis(host="127.0.0.1", port=16379, socket_timeout=2)
    for _ in range(30):
        if process.poll() is not None:
            raise RuntimeError("Portable Redis exited; inspect its isolated log")
        try:
            if client.ping():
                break
        except redis.RedisError:
            time.sleep(.2)
    else:
        process.terminate()
        raise RuntimeError("Portable Redis did not start; inspect its isolated log")
    versions = {"postgres": run(binaries / "postgres.exe", "--version").strip(),
                "redis": client.info("server")["redis_version"], "redis_pid": process.pid,
                "redis_server_pid": client.info("server")["process_id"],
                "postgres_port": 55432, "redis_port": 16379}
    (TOOLS / "services.json").write_text(json.dumps(versions, indent=2))
    print(json.dumps(versions, indent=2))


def stop():
    import redis
    # Never read REDIS_URL/DATABASE_URL or target externally configured resources.
    try:
        client = redis.Redis(host="127.0.0.1", port=16379, socket_timeout=3)
        recorded = json.loads((TOOLS / "services.json").read_text())
        if client.info("server")["process_id"] != recorded["redis_server_pid"]:
            raise RuntimeError("Redis audit process ownership changed; shutdown refused")
        client.shutdown(nosave=True)
    except redis.ConnectionError:
        pass
    data = (TOOLS / "postgres-data").resolve()
    if not data.is_relative_to(TOOLS.resolve()) or not (data / "PG_VERSION").exists():
        raise RuntimeError("Audit database directory validation failed")
    print(run(TOOLS / "postgres" / "pgsql" / "bin" / "pg_ctl.exe", "-D", data, "-m", "fast", "-w", "stop"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["download", "start", "stop"])
    parser.add_argument("--kind", choices=list(SOURCES))
    options = parser.parse_args()
    if options.action == "download":
        for kind in [options.kind] if options.kind else SOURCES:
            download(kind)
    elif options.action == "start":
        start()
    else:
        stop()
