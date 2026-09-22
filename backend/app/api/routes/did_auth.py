import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_principal
from app.core.config import settings
from app.core.did_key import DIDFormatError, verify_did_key_ed25519
from app.core.did_session import mint_did_session_token
from app.db.models import DIDChallenge, DIDSession, SubjectLink
from app.db.session import get_db

router = APIRouter()

CHALLENGE_TTL_SECONDS = 300


class ChallengeOut(BaseModel):
    challenge: str
    expires_at: int


class DIDVerifyIn(BaseModel):
    did: str = Field(..., max_length=400, description="did:key:... (Ed25519)")
    challenge: str = Field(..., max_length=200)
    signature_b64url: str = Field(..., max_length=200, description="Signature over challenge encoded as base64url")


class DIDVerifyOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    subject: str
    assurance_level: str


@router.get("/challenge", response_model=ChallengeOut)
def get_challenge(db: Session = Depends(get_db)):
    ch = secrets.token_urlsafe(32)
    exp = int(time.time()) + CHALLENGE_TTL_SECONDS
    db.add(DIDChallenge(challenge=ch, expires_at=exp))
    db.commit()
    return {"challenge": ch, "expires_at": exp}


@router.post("/verify", response_model=DIDVerifyOut)
def verify(payload: DIDVerifyIn, db: Session = Depends(get_db)):
    rec = db.get(DIDChallenge, payload.challenge)
    if not rec:
        raise HTTPException(status_code=400, detail="unknown challenge")
    # Challenges are single-use, whatever the outcome.
    expired = int(time.time()) > int(rec.expires_at)
    db.delete(rec)
    db.commit()
    if expired:
        raise HTTPException(status_code=400, detail="expired challenge")

    try:
        ok = verify_did_key_ed25519(
            did=payload.did,
            message=payload.challenge.encode("utf-8"),
            signature_b64url=payload.signature_b64url,
        )
    except DIDFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not ok:
        raise HTTPException(status_code=401, detail="invalid did proof")

    assurance_level = "A1_DID_ONLY"
    if not db.query(SubjectLink).filter(SubjectLink.did == payload.did).first():
        db.add(SubjectLink(did=payload.did, oidc_sub=None, assurance_level=assurance_level))

    ttl = settings.CAN_DID_SESSION_TTL_SECONDS
    session = DIDSession(did=payload.did, expires_at=int(time.time()) + ttl, assurance_level=assurance_level)
    db.add(session)
    db.commit()
    db.refresh(session)

    token = mint_did_session_token(payload.did, session.id, roles=["can_user"], assurance_level=assurance_level)
    return {
        "access_token": token,
        "expires_in": ttl,
        "subject": payload.did,
        "assurance_level": assurance_level,
    }


@router.post("/logout")
def logout(db: Session = Depends(get_db), principal=Depends(get_current_principal)):
    """Revoke the current DID session so its token stops working immediately."""
    if principal.get("auth") != "did":
        raise HTTPException(status_code=400, detail="only DID sessions can be revoked here")
    s = db.get(DIDSession, principal["sid"])
    if s is not None:
        s.is_revoked = True
        db.commit()
    return {"revoked": True}
