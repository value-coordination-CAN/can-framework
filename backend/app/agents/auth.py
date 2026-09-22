"""Agent sign-in. An agent proves its DID, exactly as a person does, and receives a token
carrying the role `can_agent` only: it can record derivations, and nothing else.

An agent token can never create a profile, hold a wallet, own an asset or receive an
entitlement, because every one of those routes requires `can_user`.
"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.models import Agent
from app.core.auth import get_current_principal
from app.db.models import User
from app.db.session import get_db

ROLE_AGENT = "can_agent"


def get_current_agent(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> Agent:
    if ROLE_AGENT not in (principal.get("roles") or []):
        raise HTTPException(status_code=403, detail="this endpoint is for registered agents")
    agent = db.query(Agent).filter(Agent.did == principal["sub"]).first()
    if agent is None:
        raise HTTPException(status_code=403, detail="unknown agent; a steward must register this DID first")
    if agent.status != "active":
        raise HTTPException(status_code=403, detail=f"agent is {agent.status}")
    if db.get(User, agent.steward_user_id) is None:
        raise HTTPException(status_code=403, detail="agent has no steward: write access withdrawn")
    return agent
