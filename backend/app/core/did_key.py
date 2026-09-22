import base64
import binascii

import base58
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

ED25519_PREFIX = bytes([0xED, 0x01])  # multicodec for Ed25519 public key


class DIDFormatError(ValueError):
    """The DID or signature is malformed (a client error, not a failed proof)."""


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    try:
        return base64.urlsafe_b64decode(s + pad)
    except (binascii.Error, ValueError) as e:
        raise DIDFormatError("signature is not valid base64url") from e


def extract_ed25519_pubkey_from_did_key(did: str) -> bytes:
    if not did.startswith("did:key:z"):
        raise DIDFormatError("unsupported DID method (expected did:key with base58btc 'z')")
    multibase = did[len("did:key:"):]
    try:
        data = base58.b58decode(multibase[1:])  # strip 'z'
    except ValueError as e:
        raise DIDFormatError("did:key is not valid base58btc") from e
    if not data.startswith(ED25519_PREFIX) or len(data) != len(ED25519_PREFIX) + 32:
        raise DIDFormatError("not an Ed25519 did:key")
    return data[len(ED25519_PREFIX):]  # raw 32-byte pubkey


def verify_did_key_ed25519(did: str, message: bytes, signature_b64url: str) -> bool:
    """Return True/False for a well-formed proof; raise DIDFormatError for malformed input."""
    pub = extract_ed25519_pubkey_from_did_key(did)
    sig = _b64url_decode(signature_b64url)
    if len(sig) != 64:
        raise DIDFormatError("Ed25519 signature must be 64 bytes")
    try:
        VerifyKey(pub).verify(message, sig)
        return True
    except BadSignatureError:
        return False
