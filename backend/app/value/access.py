"""Who can see which assets, for people and for agents alike.

An agent sees exactly what its steward sees, and only for reading. It never gains access
its steward does not have, and being an agent is never a route to wider visibility.
"""
from sqlalchemy.orm import Session

from app.agents.auth import ROLE_AGENT
from app.agents.models import Agent
from app.core.auth import ROLE_ADMIN, ROLE_AUDITOR, ROLE_REVIEWER, has_any_role
from app.db.models import User
from app.value.models import Asset, AssetShare

FULL = "full"


def acting_user_id(db: Session, principal: dict) -> tuple[str | None, Agent | None]:
    """The person whose visibility applies: the caller, or an agent's steward."""
    if ROLE_AGENT in (principal.get("roles") or []):
        agent = db.query(Agent).filter(Agent.did == principal["sub"]).first()
        if agent is None or agent.status != "active":
            return None, agent
        return agent.steward_user_id, agent
    me = db.query(User).filter(User.subject == principal["sub"]).first()
    return (me.id if me else None), None


def visible_assets(db: Session, principal: dict) -> dict[str, str | set[str]]:
    """Asset id -> FULL, or the set of shared categories."""
    user_id, agent = acting_user_id(db, principal)
    if agent is None and has_any_role(principal, ROLE_REVIEWER, ROLE_ADMIN, ROLE_AUDITOR):
        return {a.id: FULL for a in db.query(Asset.id).all()}
    if user_id is None:
        return {}
    out: dict[str, str | set[str]] = {a.id: FULL for a in db.query(Asset.id).filter(Asset.holder_user_id == user_id)}
    for s in db.query(AssetShare).filter(AssetShare.grantee_user_id == user_id):
        out.setdefault(s.asset_id, set(s.categories))
    return out


def may_see_valuation(access: str | set[str]) -> bool:
    return access == FULL or "valuation" in access


def filter_inputs(result: dict, access: str | set[str]) -> dict:
    """Selective disclosure: a grantee sees the result, and only the inputs they were shared."""
    if access != FULL and isinstance(result.get("inputs"), dict):
        result["inputs"] = {k: v for k, v in result["inputs"].items() if v["category"] in access}
    return result
