import base64
import base58
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

ED25519_PREFIX = bytes([0xED, 0x01])  # multicodec for Ed25519 public key

def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def extract_ed25519_pubkey_from_did_key(did: str) -> bytes:
    if not did.startswith("did:key:z"):
        raise ValueError("unsupported DID method (expected did:key)")
    multibase = did.split("did:key:")[1]
    if not multibase.startswith("z"):
        raise ValueError("unsupported multibase (expected base58btc 'z')")
    data = base58.b58decode(multibase[1:])  # strip 'z'
    if not data.startswith(ED25519_PREFIX):
        raise ValueError("not an Ed25519 did:key")
    return data[len(ED25519_PREFIX):]  # raw 32-byte pubkey

def verify_did_key_ed25519(did: str, message: bytes, signature_b64url: str) -> bool:
    pub = extract_ed25519_pubkey_from_did_key(did)
    sig = _b64url_decode(signature_b64url)
    vk = VerifyKey(pub)
    try:
        vk.verify(message, sig)
        return True
    except BadSignatureError:
        return False
