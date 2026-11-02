"""Decrypt a .awenc backup to a local pg_dump custom-format file."""
import getpass
from pathlib import Path
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.exceptions import InvalidTag

MAGIC = b"AWINLINK-AES256-GCM-v1\n"
if len(sys.argv) != 3:
    raise SystemExit("Usage: python restore.py encrypted.awenc output.dump")
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
if destination.exists():
    raise SystemExit("Output already exists; choose a new output path")
with source.open("rb") as src:
    if src.read(len(MAGIC)) != MAGIC:
        raise SystemExit("Not a supported Awinlink encrypted backup")
    salt, nonce = src.read(16), src.read(12)
    src.seek(-16, 2)
    tag = src.read(16)
    end = src.tell() - 16
    src.seek(len(MAGIC) + 28)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(getpass.getpass("Backup password: ").encode())
    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    try:
        with destination.open("xb") as dst:
            remaining = end - src.tell()
            while remaining:
                chunk = src.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise EOFError("Unexpected end of backup")
                dst.write(decryptor.update(chunk))
                remaining -= len(chunk)
            dst.write(decryptor.finalize())
    except (InvalidTag, Exception):
        destination.unlink(missing_ok=True)
        raise
print("Decrypted PostgreSQL dump:", destination)
