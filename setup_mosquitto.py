import os
from pathlib import Path

ROOT = Path(__file__).parent
CERTS = ROOT / "mosquitto_certs"
CONF = ROOT / "mosquitto_ohm.conf"

CERTS.mkdir(exist_ok=True)


def gen_certs():
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from datetime import datetime, timedelta
    except ImportError:
        print("[FAIL] cryptography not installed")
        return False

    ca_key_path = CERTS / "ca.key"
    ca_crt_path = CERTS / "ca.crt"
    srv_key_path = CERTS / "server.key"
    srv_crt_path = CERTS / "server.crt"

    if ca_crt_path.exists() and srv_crt_path.exists():
        print("[ok]   certificates already exist")
        return True

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OHM-CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.utcnow())
        .not_valid_after(datetime.utcnow() + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_subject)
        .issuer_name(ca_subject)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
        ]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    ca_key_path.write_bytes(ca_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    ca_crt_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    srv_key_path.write_bytes(srv_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    srv_crt_path.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))
    print(f"[ok]   certificates generated in {CERTS}")
    return True


def write_conf():
    conf = f"""listener 8883
allow_anonymous true
cafile {CERTS.as_posix()}/ca.crt
certfile {CERTS.as_posix()}/server.crt
keyfile {CERTS.as_posix()}/server.key
tls_version tlsv1.2

listener 1883
allow_anonymous true
"""
    CONF.write_text(conf, encoding="utf-8")
    print(f"[ok]   config written: {CONF}")


if __name__ == "__main__":
    print("=" * 60)
    print("MOSQUITTO SETUP")
    print("=" * 60)
    ok = gen_certs()
    if ok:
        write_conf()
    print("=" * 60)
    print("NEXT STEPS:")
    print("  1. Install Mosquitto: choco install mosquitto")
    print(f"  2. Run: mosquitto -c \"{CONF}\" -v")
    print("  3. Leave that terminal open")
    print("=" * 60)