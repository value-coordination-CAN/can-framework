"""Right of access (export) and right to withdrawal (account deletion)."""
import hashlib
import hmac

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import (
    AllocationRequest,
    Appeal,
    CareConsent,
    DeletionRecord,
    DIDSession,
    EntryDispute,
    LedgerEntry,
    ScoreSnapshot,
    SubjectLink,
    User,
)
from app.bridge.models import (
    BridgeTransfer,
    Contribution,
    Holding,
    Pledge,
    Project,
    SupplierAgreement,
    SupplierInvoice,
    Wallet,
)
from app.models.network_edge import NetworkEdge
from app.value.models import Asset, AssetEvidence, AssetShare, AssuranceRun


def _rows(q) -> list[dict]:
    out = []
    for r in q:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        out.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in d.items()})
    return out


def export_account(db: Session, me: User) -> dict:
    """Everything the backend holds about the person, in one document."""
    entry_ids = [e.id for e in db.query(LedgerEntry.id).filter(LedgerEntry.user_id == me.id)]
    return {
        "profile": _rows([me])[0],
        "ledger_entries": _rows(db.query(LedgerEntry).filter(LedgerEntry.user_id == me.id).order_by(LedgerEntry.created_at)),
        "entry_disputes": _rows(db.query(EntryDispute).filter(
            or_(EntryDispute.user_id == me.id, EntryDispute.entry_id.in_(entry_ids)))),
        "care_consents": _rows(db.query(CareConsent).filter(CareConsent.user_id == me.id)),
        "score_snapshots": _rows(db.query(ScoreSnapshot).filter(ScoreSnapshot.user_id == me.id).order_by(ScoreSnapshot.created_at)),
        "allocation_requests": _rows(db.query(AllocationRequest).filter(AllocationRequest.user_id == me.id)),
        "appeals": _rows(db.query(Appeal).filter(Appeal.user_id == me.id)),
        "network_edges": _rows(db.query(NetworkEdge).filter(NetworkEdge.source_user_id == me.id)),
        "assets": [
            {
                **_rows([a])[0],
                "evidence": _rows(db.query(AssetEvidence).filter(AssetEvidence.asset_id == a.id)),
                "shares": _rows(db.query(AssetShare).filter(AssetShare.asset_id == a.id)),
                "assurance_runs": _rows(db.query(AssuranceRun).filter(AssuranceRun.asset_id == a.id)),
            }
            for a in db.query(Asset).filter(Asset.holder_user_id == me.id)
        ],
        "wallet": _wallet_export(db, me.id),
    }


def _wallet_export(db: Session, uid: str) -> dict:
    wallet = db.query(Wallet).filter(Wallet.user_id == uid).first()
    if wallet is None:
        return {}
    holding_ids = [h.id for h in db.query(Holding.id).filter(Holding.wallet_id == wallet.id)]
    return {
        **_rows([wallet])[0],
        "holdings": _rows(db.query(Holding).filter(Holding.wallet_id == wallet.id)),
        "pledges": _rows(db.query(Pledge).filter(Pledge.holding_id.in_(holding_ids))) if holding_ids else [],
        "transfers": _rows(db.query(BridgeTransfer).filter(BridgeTransfer.wallet_id == wallet.id)),
        "projects_sponsored": _rows(db.query(Project).filter(Project.sponsor_user_id == uid)),
        "contributions": _rows(db.query(Contribution).filter(Contribution.contributor_user_id == uid)),
        "supplier_agreements": _rows(db.query(SupplierAgreement).filter(SupplierAgreement.supplier_user_id == uid)),
    }


def pseudonym(subject: str) -> str:
    h = hmac.new(settings.EXTERNAL_ID_PEPPER.encode(), subject.encode(), hashlib.sha256).hexdigest()
    return f"deleted:{h[:16]}"


def delete_account(db: Session, me: User) -> dict:
    """Erase the person's data. Records that belong to other people (entries they attested,
    decisions they made) are kept for those people, with the deleted person's identity
    replaced by a pseudonym. An audit record with counts only is kept."""
    uid, subject = me.id, me.subject
    counts: dict[str, int] = {}

    request_ids = [r.id for r in db.query(AllocationRequest.id).filter(AllocationRequest.user_id == uid)]
    entry_ids = [e.id for e in db.query(LedgerEntry.id).filter(LedgerEntry.user_id == uid)]

    counts["appeals"] = db.query(Appeal).filter(
        or_(Appeal.user_id == uid, Appeal.request_id.in_(request_ids))
    ).delete(synchronize_session=False)
    counts["allocation_requests"] = db.query(AllocationRequest).filter(
        AllocationRequest.user_id == uid
    ).delete(synchronize_session=False)
    counts["score_snapshots"] = db.query(ScoreSnapshot).filter(
        ScoreSnapshot.user_id == uid
    ).delete(synchronize_session=False)
    counts["entry_disputes"] = db.query(EntryDispute).filter(
        or_(EntryDispute.user_id == uid, EntryDispute.entry_id.in_(entry_ids))
    ).delete(synchronize_session=False)
    db.query(LedgerEntry).filter(LedgerEntry.user_id == uid).update(
        {LedgerEntry.supersedes_id: None}, synchronize_session=False
    )
    counts["ledger_entries"] = db.query(LedgerEntry).filter(
        LedgerEntry.user_id == uid
    ).delete(synchronize_session=False)
    counts["care_consents"] = db.query(CareConsent).filter(
        CareConsent.user_id == uid
    ).delete(synchronize_session=False)
    counts["network_edges"] = db.query(NetworkEdge).filter(
        or_(NetworkEdge.source_user_id == uid, NetworkEdge.target_user_id == uid)
    ).delete(synchronize_session=False)

    # Value Assurance (WP-011): assets held, and shares granted to the person
    asset_ids = [a.id for a in db.query(Asset.id).filter(Asset.holder_user_id == uid)]
    if asset_ids:
        db.query(AssuranceRun).filter(AssuranceRun.asset_id.in_(asset_ids)).delete(synchronize_session=False)
        db.query(AssetShare).filter(AssetShare.asset_id.in_(asset_ids)).delete(synchronize_session=False)
        db.query(AssetEvidence).filter(AssetEvidence.asset_id.in_(asset_ids)).delete(synchronize_session=False)
    counts["assets"] = db.query(Asset).filter(Asset.holder_user_id == uid).delete(synchronize_session=False)
    counts["asset_shares_received"] = db.query(AssetShare).filter(
        AssetShare.grantee_user_id == uid
    ).delete(synchronize_session=False)

    # Bridge wallet (WP-010): the person's wallet, and projects they sponsor
    wallet = db.query(Wallet).filter(Wallet.user_id == uid).first()
    project_ids = [p.id for p in db.query(Project.id).filter(Project.sponsor_user_id == uid)]
    agreement_ids = [a.id for a in db.query(SupplierAgreement.id).filter(
        or_(SupplierAgreement.supplier_user_id == uid,
            SupplierAgreement.project_id.in_(project_ids) if project_ids else False)
    )]
    if agreement_ids:
        db.query(SupplierInvoice).filter(SupplierInvoice.agreement_id.in_(agreement_ids)).delete(synchronize_session=False)
    counts["supplier_agreements"] = db.query(SupplierAgreement).filter(
        SupplierAgreement.id.in_(agreement_ids)
    ).delete(synchronize_session=False) if agreement_ids else 0
    counts["contributions"] = db.query(Contribution).filter(
        or_(Contribution.contributor_user_id == uid,
            Contribution.project_id.in_(project_ids) if project_ids else False)
    ).delete(synchronize_session=False)
    if wallet is not None:
        holding_ids = [h.id for h in db.query(Holding.id).filter(Holding.wallet_id == wallet.id)]
        if holding_ids:
            db.query(Pledge).filter(Pledge.holding_id.in_(holding_ids)).delete(synchronize_session=False)
        db.query(BridgeTransfer).filter(BridgeTransfer.wallet_id == wallet.id).delete(synchronize_session=False)
        counts["holdings"] = db.query(Holding).filter(Holding.wallet_id == wallet.id).delete(synchronize_session=False)
        db.query(Wallet).filter(Wallet.id == wallet.id).delete(synchronize_session=False)
    db.query(Pledge).filter(Pledge.lender_user_id == uid).update({Pledge.lender_user_id: None}, synchronize_session=False)
    if project_ids:
        db.query(Holding).filter(Holding.project_id.in_(project_ids)).update(
            {Holding.project_id: None}, synchronize_session=False
        )
    counts["projects_sponsored"] = db.query(Project).filter(
        Project.sponsor_user_id == uid
    ).delete(synchronize_session=False)

    if subject:
        alias = pseudonym(subject)
        counts["pseudonymised_attestations"] = db.query(LedgerEntry).filter(
            LedgerEntry.attester_subject == subject
        ).update({LedgerEntry.attester_subject: alias}, synchronize_session=False)
        counts["pseudonymised_decisions"] = db.query(AllocationRequest).filter(
            AllocationRequest.decided_by == subject
        ).update({AllocationRequest.decided_by: alias}, synchronize_session=False)
        counts["pseudonymised_appeal_resolutions"] = db.query(Appeal).filter(
            Appeal.resolved_by == subject
        ).update({Appeal.resolved_by: alias}, synchronize_session=False)
        counts["pseudonymised_dispute_resolutions"] = db.query(EntryDispute).filter(
            EntryDispute.resolved_by == subject
        ).update({EntryDispute.resolved_by: alias}, synchronize_session=False)
        counts["pseudonymised_contribution_decisions"] = db.query(Contribution).filter(
            Contribution.decided_by == subject
        ).update({Contribution.decided_by: alias}, synchronize_session=False)
        counts["pseudonymised_invoice_verifications"] = db.query(SupplierInvoice).filter(
            SupplierInvoice.verified_by == subject
        ).update({SupplierInvoice.verified_by: alias}, synchronize_session=False)
        counts["pseudonymised_asset_evidence"] = db.query(AssetEvidence).filter(
            AssetEvidence.attester_subject == subject
        ).update({AssetEvidence.attester_subject: alias}, synchronize_session=False)
        counts["did_sessions"] = db.query(DIDSession).filter(
            DIDSession.did == subject
        ).delete(synchronize_session=False)
        counts["subject_links"] = db.query(SubjectLink).filter(
            or_(SubjectLink.did == subject, SubjectLink.oidc_sub == subject)
        ).delete(synchronize_session=False)

    db.delete(me)
    db.add(DeletionRecord(counts=counts))
    db.commit()
    return counts
