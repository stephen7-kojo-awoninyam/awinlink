"""Encrypted PostgreSQL backup to Google Drive. No secret-bearing subprocess arguments."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from urllib.parse import urlsplit, unquote, parse_qs

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPE = ["https://www.googleapis.com/auth/drive.file"]
MAGIC = b"AWINLINK-AES256-GCM-v1\n"
REQUIRED = ["DATABASE_URL", "BACKUP_ENCRYPTION_PASSWORD", "GOOGLE_DRIVE_TOKEN_JSON", "GOOGLE_DRIVE_FOLDER_ID"]
missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    raise RuntimeError("Missing configuration: " + ", ".join(missing))


def pg_environment():
    url = urlsplit(os.environ["DATABASE_URL"])
    if url.scheme not in ("postgres", "postgresql") or not url.hostname or not url.path.strip("/"):
        raise ValueError("DATABASE_URL must be a valid postgres URL")
    env = dict(os.environ)
    env.pop("DATABASE_URL", None)
    env.update(PGHOST=url.hostname, PGPORT=str(url.port or 5432),
               PGDATABASE=unquote(url.path.lstrip("/")), PGCONNECT_TIMEOUT="20")
    if url.username is not None:
        env["PGUSER"] = unquote(url.username)
    if url.password is not None:
        env["PGPASSWORD"] = unquote(url.password)
    qs = parse_qs(url.query)
    env["PGSSLMODE"] = qs.get("sslmode", ["require"])[0]
    return env


def encrypt_file(source: Path, destination: Path):
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(
        os.environ["BACKUP_ENCRYPTION_PASSWORD"].encode("utf-8"))
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    with source.open("rb") as src, destination.open("wb") as dst:
        dst.write(MAGIC + salt + nonce)
        while block := src.read(1024 * 1024):
            dst.write(encryptor.update(block))
        dst.write(encryptor.finalize())
        dst.write(encryptor.tag)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        dump = work / "awinlink.dump"
        archive = work / ("awinlink-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".awenc")
        subprocess.run(["pg_dump", "--format=custom", "--file", str(dump)],
                       env=pg_environment(), check=True)
        if dump.stat().st_size < 100:
            raise RuntimeError("Dump unexpectedly small")
        encrypt_file(dump, archive)
        creds = Credentials.from_authorized_user_info(
            json.loads(os.environ["GOOGLE_DRIVE_TOKEN_JSON"]), scopes=SCOPE)
        if not creds.valid:
            if not creds.refresh_token:
                raise RuntimeError("Google OAuth refresh token unavailable")
            creds.refresh(Request())
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = os.environ["GOOGLE_DRIVE_FOLDER_ID"]
        media = MediaFileUpload(str(archive), mimetype="application/octet-stream", resumable=True)
        uploaded = drive.files().create(
            body={"name": archive.name, "parents": [folder_id]},
            media_body=media, fields="id,name,size,md5Checksum").execute()
        local_md5 = hashlib.md5(archive.read_bytes()).hexdigest()
        if uploaded.get("md5Checksum", "").lower() != local_md5:
            raise RuntimeError("Upload checksum mismatch; do not prune backups")
        print("Encrypted backup uploaded and checksum verified:", uploaded["name"], uploaded["size"], "bytes")
        # Prune only this workflow's uniquely named files in this folder.
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
        page_token = None
        while True:
            page = drive.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields="nextPageToken,files(id,name,createdTime)", page_size=1000,
                page_token=page_token).execute()
            for item in page.get("files", []):
                name = item["name"]
                if not (name.startswith("awinlink-20") and name.endswith(".awenc")):
                    continue
                created = dt.datetime.fromisoformat(item["createdTime"].replace("Z", "+00:00"))
                if created < cutoff:
                    drive.files().delete(fileId=item["id"]).execute()
                    print("Deleted expired encrypted backup:", name)
            page_token = page.get("nextPageToken")
            if not page_token:
                break


if __name__ == "__main__":
    main()
