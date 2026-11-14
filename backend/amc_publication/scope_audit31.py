"""Read-only operator evidence for durable publication mutation reservations.

Never unlock, retry, reconcile, publish, mutate graph or switch pointers.
Held claims are intentional fail-closed state after ambiguous crashes; clearing
one without verifying external effects can enable a double mutation.
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .active_authority28 import PublicationScopeClaim31,ActiveReceiptAuthority
from .models import PublicationWork,utcnow


def audit_scope_claims(sessions, *, tenant: str|None=None) -> dict:
    findings=[]
    try:
        with sessions() as s:
            q=select(PublicationScopeClaim31).order_by(
                PublicationScopeClaim31.tenant,PublicationScopeClaim31.namespace)
            if tenant is not None:
                if not isinstance(tenant,str) or not tenant.strip():
                    raise ValueError('non-empty tenant filter required')
                q=q.where(PublicationScopeClaim31.tenant==tenant)
            for claim in s.scalars(q).all():
                work=s.get(PublicationWork,claim.owner_work_id)
                authority=s.get(ActiveReceiptAuthority,(claim.tenant,claim.namespace))
                reasons=[]
                if not work or work.tenant!=claim.tenant:
                    reasons.append('MISSING_OR_CROSS_TENANT_OWNER')
                if claim.status=='HELD':
                    if not work or work.status not in {'leased','rollback_pending'}:
                        reasons.append('HELD_WITH_NON_EXECUTING_WORK')
                    if authority is not None and (authority.status!='SUSPENDED' or
                        authority.suspended_by!=claim.owner_work_id):
                        reasons.append('HELD_SCOPE_NOT_MATCHING_AUTHORITY_SUSPENSION')
                    if work and work.status=='leased' and (work.lease_until is None or work.lease_until <= utcnow()):
                        reasons.append('EXPIRED_LEASE_NEEDS_FORENSIC_RECONCILIATION')
                elif claim.status=='RELEASED':
                    if not work or work.status not in {'published','rolled_back'}:
                        reasons.append('RELEASED_WITH_UNEXPECTED_WORK_STATE')
                    if authority is not None and authority.status=='SUSPENDED':
                        reasons.append('RELEASED_SCOPE_BUT_SERVING_SUSPENDED')
                else:reasons.append('INVALID_SCOPE_STATE')
                findings.append({'tenant':claim.tenant,'namespace':claim.namespace,
                    'owner_work_id':claim.owner_work_id,'work_status':work.status if work else None,
                    'scope_status':claim.status,'claim_epoch':claim.claim_epoch,
                    'authority_status':authority.status if authority else None,
                    'anomalies':reasons,'needs_operator':bool(reasons)})
    except SQLAlchemyError as exc:
        # Failed DDL or database read MUST NOT become an empty success report.
        return {'schema':'amc-publication-scope-audit-v31','status':'BLOCKED',
                'reason':'database read or scope migration unavailable',
                'findings':[],'needs_operator':True,'read_only':True}
    alerts=sum(x['needs_operator'] for x in findings)
    return {'schema':'amc-publication-scope-audit-v31',
        'status':'NEEDS_OPERATOR' if alerts else 'READ_ONLY_NO_SCOPE_ANOMALIES',
        'scope_count':len(findings),'anomaly_count':alerts,'findings':findings,
        'read_only':True,'uat':'BLOCKED'}
