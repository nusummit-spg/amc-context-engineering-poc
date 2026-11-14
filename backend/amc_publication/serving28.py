"""Wave 2.8 request-time serving bound to one durable active receipt.

No guessing when multiple historical published receipts share a generation. The
same authority identity is re-read after loaded-reader and byte verification.
"""
from __future__ import annotations
from .serving27 import VerifiedGenerationResolver, ServingDenied
from .active_authority28 import current_binding
from .types import Conflict

class ActiveReceiptResolver(VerifiedGenerationResolver):
    def _authority(self, tenant):
        with self.sessions() as s:
            try:
                return current_binding(s, tenant)
            except Conflict as exc:
                raise ServingDenied('no valid active receipt authority') from exc

    def resolve_for_serving(self, tenant: str, *, work_id=None, receipt_id=None):
        self._check_tenant(tenant)
        binding=self._authority(tenant)
        generation,digest,epoch,work,receipt=binding
        if work_id is not None and work_id!=work:
            raise ServingDenied('requested work is not currently authoritative')
        if receipt_id is not None and receipt_id!=receipt:
            raise ServingDenied('requested receipt is not currently authoritative')
        verified=super().resolve_for_serving(tenant,work_id=work,receipt_id=receipt)
        if (verified.generation_id,verified.digest,verified.epoch,verified.work_id,verified.receipt_id)!=binding:
            raise ServingDenied('serving authority changed during read')
        if self._authority(tenant)!=binding:
            raise ServingDenied('serving authority revoked while validating reader')
        return verified
