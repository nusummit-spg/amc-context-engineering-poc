"""AMC VectorStore-compatible opt-in verified FAISS retrieval.

Only reads are implemented. No public fallback to the legacy FAISS reader.
The existing ingestion interface should remain explicitly isolated until
canonical corpus publication and source ownership are audited in the app.
"""
from __future__ import annotations
import asyncio
import math
import os
from typing import Any
from .faiss_reader27 import VerifiedFaissRetriever
from .serving27 import ServingDenied
from .serving28 import ActiveReceiptResolver

def verified_mode() -> str:
    """Strict mode parser: a typo must never silently enable legacy retrieval."""
    value=os.environ.get('AMC_VERIFIED_SERVING_MODE','off')
    if value not in ('off','enforce'):
        raise ServingDenied('invalid AMC_VERIFIED_SERVING_MODE; expected off or enforce')
    return value


class VerifiedVectorBridge:
    def __init__(self, *, embedder, retriever, user_id=None, tenant_id=None):
        self._embedder=embedder
        self._retriever=retriever
        self._user=user_id
        self._tenant=tenant_id

    def _identity(self, user_id, tenant_id):
        if tenant_id is not None and self._tenant is not None and tenant_id!=self._tenant:
            raise ServingDenied('request tenant differs from authenticated scope')
        if user_id is not None and self._user is not None and user_id!=self._user:
            raise ServingDenied('request user differs from authenticated scope')
        tenant=tenant_id if tenant_id is not None else self._tenant
        user=user_id if user_id is not None else self._user
        if not isinstance(tenant,str) or not tenant.strip():
            raise ServingDenied('verified read requires authenticated explicit tenant')
        return tenant,user

    async def assert_serving_authority(self, tenant_id: str):
        tenant, _ = self._identity(None, tenant_id)
        return await asyncio.to_thread(self._retriever.resolver.resolve_for_serving, tenant)

    async def _search(self, *, embedding=None, query=None, limit=8, taxonomy_paths=None,
                      metadata_filter=None, user_id=None, tenant_id=None):
        tenant,user=self._identity(user_id,tenant_id)
        if type(limit) is not int or limit<1 or limit>100:raise ValueError('limit must be 1..100')
        if query is not None and embedding is not None:raise ValueError('ambiguous embedding/query')
        if embedding is None:
            if not isinstance(query,str) or not query.strip():raise ValueError('nonempty query required')
            vecs=await self._embedder.embed_async([query])
            if not isinstance(vecs,list) or len(vecs)!=1:raise ServingDenied('embedder returned wrong count')
            embedding=vecs[0]
        if hasattr(embedding,'tolist'):embedding=embedding.tolist()
        if not isinstance(embedding,(list,tuple)) or not embedding:raise ValueError('nonempty embedding required')
        # W30: pin current authority across BOTH physical retrieval and
        # filtering. A rollback can occur after the retriever returns hits.
        # The bridge must not release old hits if the active receipt changed.
        authority = getattr(getattr(self._retriever, 'resolver', None), '_authority', None)
        before = None
        if verified_mode() == 'enforce':
            if not callable(authority):
                raise ServingDenied('active authority probe required for verified vector search')
            before = await asyncio.to_thread(authority, tenant)
        # max limit 100; requesting larger candidates is deliberate: user/tenant
        # and metadata filters must never be applied AFTER truncation.
        results=await asyncio.to_thread(self._retriever.search,tenant,list(embedding),limit=100)
        hits=[]
        seen=set()
        for h in results:
            doc=h.get('document')
            if not isinstance(doc,dict) or h.get('chunk_id')!=doc.get('chunk_id'):
                raise ServingDenied('returned hit/document identity mismatch')
            if doc.get('tenant_id')!=tenant:
                raise ServingDenied('cross-tenant vector hit from verified index')
            owner=doc.get('user_id')
            if owner is not None and owner!=user:continue
            if metadata_filter:
                meta=doc.get('metadata') or {}
                if any(doc.get(k)!=v and meta.get(k)!=v for k,v in metadata_filter.items()):continue
            if taxonomy_paths:
                if not set(doc.get('taxonomy_paths') or []).intersection(taxonomy_paths):continue
            cid=doc['chunk_id']
            if cid in seen:raise ServingDenied('duplicate returned chunk ID')
            seen.add(cid)
            score=float(h['score'])
            if not math.isfinite(score):raise ServingDenied('nonfinite vector result')
            hits.append({**doc,'chunk_id':cid,'score':round(max(0.0,min(1.0,score)),4)})
            if len(hits)>=limit:break
        if before is not None:
            after = await asyncio.to_thread(authority, tenant)
            if after != before:
                raise ServingDenied('active receipt changed before verified search delivery')
        return hits

    async def search(self,query,top_k=8,taxonomy_paths=None,entity_names=None,
                     user_id=None,tenant_id=None,metadata_filter=None,limit=None,**kwargs):
        if kwargs:raise ServingDenied('unreviewed vector-search options are not allowed')
        if entity_names is not None and not isinstance(entity_names,list):raise ValueError('invalid entity name filter')
        is_vec=isinstance(query,(list,tuple)) or hasattr(query,'tolist')
        return await self._search(embedding=query if is_vec else None,query=None if is_vec else query,
            limit=limit if limit is not None else top_k,taxonomy_paths=taxonomy_paths,
            metadata_filter=metadata_filter,user_id=user_id,tenant_id=tenant_id)

    async def similarity_search(self,embedding=None,query=None,limit=10,
                                metadata_filter=None,user_id=None,tenant_id=None):
        return await self._search(embedding=embedding,query=query,limit=limit,
            metadata_filter=metadata_filter,user_id=user_id,tenant_id=tenant_id)

    def __getattr__(self,name):
        # Explicitly forbid leaked legacy client, writes and bypass APIs.
        raise ServingDenied(f'unverified vector API not enabled: {name}')


def create_verified_vector_store(*,base_client,user_id=None,tenant_id=None):
    """Use from get_vector_store() ONLY with AMC_VERIFIED_SERVING_MODE=enforce."""
    root=os.getenv('AMC_VERIFIED_FAISS_ROOT')
    if not root:raise ServingDenied('AMC_VERIFIED_FAISS_ROOT is required')
    from app.core.database import SessionLocal
    retriever=VerifiedFaissRetriever(SessionLocal,root)
    retriever.resolver=ActiveReceiptResolver(SessionLocal,retriever.store,serving_loader=retriever._load)
    return VerifiedVectorBridge(embedder=base_client,retriever=retriever,user_id=user_id,tenant_id=tenant_id)
