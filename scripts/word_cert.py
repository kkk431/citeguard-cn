"""Generate a trusted localhost certificate for the Word task pane.

Usage:
    python scripts/word_cert.py

Writes out/word_tls/{cert.pem,key.pem} and (on Windows) trusts the cert for
the current user via certutil, so WebView2/Word accept https://localhost:8443.
"""
from __future__ import annotations

import ipaddress
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def main() -> int:
    out = Path("out/word_tls")
    out.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=5))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = out / "cert.pem"
    key_path = out / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    print(f"wrote {cert_path} and {key_path}")
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["certutil", "-addstore", "-user", "Root", str(cert_path)],
                check=True,
                capture_output=True,
            )
            print("trusted the certificate for the current user")
        except Exception as exc:  # pragma: no cover - platform specific
            print(f"could not trust cert automatically: {exc}")
    print("start HTTPS demo:")
    print(
        "  python -m uvicorn web.app:app --host 127.0.0.1 --port 8443 "
        "--ssl-certfile out/word_tls/cert.pem --ssl-keyfile out/word_tls/key.pem"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
