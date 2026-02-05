import time
import secrets
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.db.models import DIDChallenge, DIDSession, SubjectLink
from app.core.did_key import verify_did_key_ed25519
from app.core.did_session import mint_did_session_token

router = APIRouter()

class ChallengeOut(BaseModel):
    challenge: str
    expires_at: int

class DIDVerifyIn(BaseModel):
    did: str = Field(..., description="did:key:... (Ed25519)")
    challenge: str
    signature_b64url: str = Field(..., description="Signature over challenge encoded as base64url")

class DIDVerifyOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    subject: str
    assurance_level: str

@router.get("/challenge", response_model=ChallengeOut)
def get_challenge(db: Session = Depends(get_db)):
    ch = secrets.token_urlsafe(32)
    exp = int(time.time()) + 300
    db.add(DIDChallenge(challenge=ch, expires_at=exp))
    db.commit()
    return {"challenge": ch, "expires_at": exp}

@router.post("/verify", response_model=DIDVerifyOut)
def verify(payload: DIDVerifyIn, db: Session = Depends(get_db)):
    rec = db.get(DIDChallenge, payload.challenge)
    if not rec:
        raise HTTPException(status_code=400, detail="unknown challenge")
    if int(time.time()) > int(rec.expires_at):
        db.delete(rec)
        db.commit()
        raise HTTPException(status_code=400, detail="expired challenge")

    ok = verify_did_key_ed25519(
        did=payload.did,
        message=payload.challenge.encode("utf-8"),
        signature_b64url=payload.signature_b64url,
    )
    if not ok:
        raise HTTPException(status_code=401, detail="invalid did proof")

    db.delete(rec)
    db.commit()

    assurance_level = "A1_DID_ONLY"

    if not db.query(SubjectLink).filter(SubjectLink.did == payload.did).first():
        db.add(SubjectLink(did=payload.did, oidc_sub=None, assurance_level=assurance_level))
        db.commit()

    token = mint_did_session_token(payload.did, roles=["can_user"], assurance_level=assurance_level)

    db.add(DIDSession(did=payload.did, expires_at=int(time.time()) + 900, assurance_level=assurance_level))
    db.commit()

    return {
        "access_token": token,
        "expires_in": 900,
        "subject": payload.did,
        "assurance_level": assurance_level,
    }
