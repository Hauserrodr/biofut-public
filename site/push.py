"""Web Push for the BioFut site (RFC 8291 aes128gcm + RFC 8292 VAPID), so the phones that said yes get a notification.
Needs the cryptography package (the A1 python3 has it); server.py runs without it, with push off.
Self-check: python push.py (encrypts a message and decrypts it back as the phone would)."""
import base64
import json
import os
import struct
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

P256, PT = ec.SECP256R1(), serialization.PublicFormat.UncompressedPoint


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hkdf(salt, info, ikm, n):
    return HKDF(hashes.SHA256(), n, salt, info).derive(ikm)


def vapid(path):
    """The server's VAPID key, made on first use and kept in data/ (never in git)."""
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(ec.generate_private_key(P256).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                                     serialization.NoEncryption()))
        os.chmod(path, 0o600)
    return serialization.load_pem_private_key(path.read_bytes(), None)


def public_key(key):
    """The applicationServerKey the page subscribes with."""
    return b64(key.public_key().public_bytes(serialization.Encoding.X962, PT))


def encrypt(p256dh, auth, data, salt=None, eph=None):
    ua = unb64(p256dh)
    eph = eph or ec.generate_private_key(P256)
    pub = eph.public_key().public_bytes(serialization.Encoding.X962, PT)
    ikm = hkdf(unb64(auth), b"WebPush: info\0" + ua + pub, eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(P256, ua)), 32)
    salt = salt or os.urandom(16)
    cek, nonce = hkdf(salt, b"Content-Encoding: aes128gcm\0", ikm, 16), hkdf(salt, b"Content-Encoding: nonce\0", ikm, 12)
    return salt + struct.pack(">IB", 4096, len(pub)) + pub + AESGCM(cek).encrypt(nonce, data + b"\x02", None)


def jwt(key, endpoint, sub="https://biofut.h-brain.org"):
    u = urlsplit(endpoint)
    head = b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode()) + "." + b64(json.dumps(
        {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": sub}).encode())
    r, s = decode_dss_signature(key.sign(head.encode(), ec.ECDSA(hashes.SHA256())))
    return head + "." + b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))


def send(key, sub, msg):
    """One notification to one subscription ({endpoint, keys: {p256dh, auth}}). -> the push service's HTTP status
    (201 sent; 404/410 the phone left, drop it)."""
    body = encrypt(sub["keys"]["p256dh"], sub["keys"]["auth"], json.dumps(msg, ensure_ascii=False).encode())
    req = urllib.request.Request(sub["endpoint"], data=body, method="POST", headers={
        "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream", "TTL": "86400", "Urgency": "high",
        "Authorization": f"vapid t={jwt(key, sub['endpoint'])}, k={public_key(key)}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def decrypt(ua_key, auth, blob):  # what the phone does: only the self-check uses it
    salt, n = blob[:16], blob[20]
    pub, ct = blob[21:21 + n], blob[21 + n:]
    ua = ua_key.public_key().public_bytes(serialization.Encoding.X962, PT)
    ikm = hkdf(auth, b"WebPush: info\0" + ua + pub, ua_key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(P256, pub)), 32)
    out = AESGCM(hkdf(salt, b"Content-Encoding: aes128gcm\0", ikm, 16)).decrypt(hkdf(salt, b"Content-Encoding: nonce\0", ikm, 12), ct, None)
    return out[:-1]


if __name__ == "__main__":
    phone, auth = ec.generate_private_key(P256), os.urandom(16)
    msg = "Quem pagar o pix hoje até meia noite ganha 10 moedas".encode()
    assert decrypt(phone, auth, encrypt(b64(phone.public_key().public_bytes(serialization.Encoding.X962, PT)), b64(auth), msg)) == msg
    k = ec.generate_private_key(P256)
    h, c, s = jwt(k, "https://fcm.googleapis.com/fcm/send/x").split(".")
    assert json.loads(unb64(c))["aud"] == "https://fcm.googleapis.com" and len(unb64(s)) == 64 and len(unb64(public_key(k))) == 65
    print("ok")
