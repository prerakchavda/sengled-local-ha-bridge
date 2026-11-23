"""
Cryptographic utilities for Sengled Local Home Assistant Bridge:

1. RC4 + Base64 payload encryption/decryption for Sengled Wi-Fi AP onboarding
   (`setParamsRequest` on 192.168.8.1:9080).
2. Self-signed TLS CA & Server certificate generation for local port 8883
   Mosquitto MQTT broker.
"""

from __future__ import annotations

import base64
import datetime
import ipaddress
import json
from pathlib import Path
from typing import Any, Dict, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# Hardcoded RC4 key string embedded in the Sengled mobile app and bulb firmware
KEY_STR = "MTlCaWppbmdTaGFuZ2hhaVdpU2VuZ2xlZEZpMjBBQUJBU0U2NA=="


def rc4_crypt(data: bytes, key: bytes) -> bytes:
    """Standard RC4 (ARC4) symmetric stream cipher."""
    s = list(range(256))
    j = 0
    key_len = len(key)

    for i in range(256):
        j = (j + s[i] + key[i % key_len]) % 256
        s[i], s[j] = s[j], s[i]

    i = 0
    j = 0
    out = bytearray()
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        k = s[(s[i] + s[j]) % 256]
        out.append(byte ^ k)

    return bytes(out)


def encrypt_wifi_payload(data: Union[Dict[str, Any], str, bytes], key_str: str = KEY_STR) -> str:
    """
    Encrypt a Wi-Fi setup payload (`setParamsRequest`) with RC4 and encode as Base64.
    """
    if isinstance(data, dict):
        raw_bytes = json.dumps(data).encode("utf-8")
    elif isinstance(data, str):
        raw_bytes = data.encode("utf-8")
    else:
        raw_bytes = bytes(data)

    encrypted = rc4_crypt(raw_bytes, key_str.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt_wifi_payload(b64_payload: str, key_str: str = KEY_STR) -> Dict[str, Any]:
    """
    Decode a Base64 + RC4-encrypted Wi-Fi setup payload back into a JSON dictionary.
    """
    ciphertext = base64.b64decode(b64_payload.strip())
    plaintext = rc4_crypt(ciphertext, key_str.encode("utf-8"))
    return json.loads(plaintext.decode("utf-8"))


def generate_self_signed_certs(
    cert_dir: Union[str, Path],
    common_name: str = "sengled.local",
    server_ip: str = "127.0.0.1",
    validity_days: int = 3650,
    overwrite: bool = False,
) -> Dict[str, Path]:
    """
    Generate a local Root CA (`ca.crt`, `ca.key`) and Server TLS certificate
    (`server.crt`, `server.key`) for the local port 8883 MQTT broker.

    Sengled Wi-Fi bulbs require TLS on port 8883 and accept a self-signed server
    certificate signed by a local CA.
    """
    out_dir = Path(cert_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ca_key_path = out_dir / "ca.key"
    ca_crt_path = out_dir / "ca.crt"
    srv_key_path = out_dir / "server.key"
    srv_crt_path = out_dir / "server.crt"

    if (
        not overwrite
        and ca_crt_path.exists()
        and srv_crt_path.exists()
        and srv_key_path.exists()
    ):
        return {
            "ca_key": ca_key_path,
            "ca_cert": ca_crt_path,
            "server_key": srv_key_path,
            "server_cert": srv_crt_path,
        }

    now = datetime.datetime.now(datetime.timezone.utc)
    expires = now + datetime.timedelta(days=validity_days)

    # 1. Generate CA key and certificate
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sengled Local Bridge CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{common_name}-ca"),
        ]
    )
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(expires)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    # 2. Generate Server key and certificate signed by CA
    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_subject = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sengled Local Bridge"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )

    san_entries = [
        x509.DNSName(common_name),
        x509.DNSName("localhost"),
        x509.DNSName("us-mqtt.cloud.sengled.com"),
        x509.DNSName("mqtt.cloud.sengled.com"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    try:
        ip_obj = ipaddress.ip_address(server_ip)
        if ip_obj != ipaddress.ip_address("127.0.0.1"):
            san_entries.append(x509.IPAddress(ip_obj))
    except ValueError:
        san_entries.append(x509.DNSName(server_ip))

    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_subject)
        .issuer_name(ca_subject)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(expires)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_key_path.write_bytes(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    ca_crt_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    srv_key_path.write_bytes(
        srv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    srv_crt_path.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))

    return {
        "ca_key": ca_key_path,
        "ca_cert": ca_crt_path,
        "server_key": srv_key_path,
        "server_cert": srv_crt_path,
    }
