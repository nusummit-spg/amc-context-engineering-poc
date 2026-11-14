"""Wave 2.9: pin verified receipt over complete response lifetimes.

The legacy retrieval orchestrator may return from fast path/cache or perform
multiple vector operations. This wrapper checks the same active receipt before
and after a full answer; in enforce mode SSE output is buffered, checked, and
rechecked before each frame. There is no cross-store global read transaction:
a rollback between the final check and network delivery remains a physical race.
"""
from __future__ import annotations
import asyncio
import json
from .serving27 import ServingDenied
from .vector_bridge28 import verified_mode


def generation_key(g):
    attrs=('tenant','generation_id','digest','epoch','work_id','receipt_id')
    if any(not hasattr(g, a) for a in attrs):
        raise ServingDenied('missing complete active generation identity')
    return tuple(getattr(g,a) for a in attrs)


class VerifiedOrchestratorFence29:
    MAX_FRAMES=4096
    MAX_BYTES=4*1024*1024

    def __init__(self, delegate, reader):
        self._delegate=delegate
        self._reader=reader

    async def _pin(self, tenant_id):
        if not isinstance(tenant_id,str) or not tenant_id.strip():
            raise ServingDenied('verified answer requires authenticated tenant')
        probe=getattr(self._reader,'assert_serving_authority',None)
        if not callable(probe):
            raise ServingDenied('verified reader missing receipt authority probe')
        gen=await probe(tenant_id)
        return generation_key(gen)

    async def _check(self, tenant_id, before):
        after=await self._pin(tenant_id)
        if before != after:
            raise ServingDenied('active receipt changed while rendering answer')

    async def answer(self, *args, **kwargs):
        if verified_mode() != 'enforce':
            return await self._delegate.answer(*args, **kwargs)
        tenant=kwargs.get('tenant_id')
        before=await self._pin(tenant)
        response=await self._delegate.answer(*args, **kwargs)
        await self._check(tenant, before)
        return response

    async def traditional_search(self, *args, **kwargs):
        if verified_mode() != 'enforce':
            return await self._delegate.traditional_search(*args, **kwargs)
        tenant=kwargs.get('tenant_id')
        before=await self._pin(tenant)
        response=await self._delegate.traditional_search(*args, **kwargs)
        await self._check(tenant, before)
        return response

    async def answer_stream(self, *args, **kwargs):
        if verified_mode() != 'enforce':
            async for frame in self._delegate.answer_stream(*args, **kwargs):
                yield frame
            return
        tenant=kwargs.get('tenant_id')
        before=await self._pin(tenant)
        frames=[]; size=0
        async for frame in self._delegate.answer_stream(*args, **kwargs):
            if not isinstance(frame,dict):
                raise ServingDenied('unrecognized stream frame')
            try:
                packed=json.dumps(frame,sort_keys=True,ensure_ascii=False,default=str).encode('utf-8')
            except (ValueError,TypeError,OverflowError) as ex:
                raise ServingDenied('unserializable stream frame') from ex
            size += len(packed)
            if len(frames) >= self.MAX_FRAMES or size > self.MAX_BYTES:
                raise ServingDenied('verified response exceeds buffered stream limits')
            frames.append(json.loads(packed))
        await self._check(tenant,before)
        for frame in frames:
            # A concurrent rollback aborts subsequent SSE frames, rather than
            # continuing to emit stale sourced answers. Check is not a lock.
            await self._check(tenant,before)
            yield frame

    def __getattr__(self, name):
        # Not a security boundary on the Python object graph; the application
        # must only expose answer/stream/traditional methods to request routes.
        return getattr(self._delegate,name)
