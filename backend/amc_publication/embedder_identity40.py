"""Wave 4.0 (TDS-40 E6, ADR40-06): embedder identity bound into signed FAISS generations.

A FAISS index is only meaningful for queries embedded by the SAME model that built it. Before Wave 4.0 nothing
recorded which embedder built a generation, so a deployment could silently pair a real index with a different
(or stub) query embedder and serve plausible-looking but wrong neighbours.

Now FaissGenerationStore.stage() writes manifest["embedder"] = embedder_identity(embedder); the manifest is what
the publisher signs. At serving time VerifiedVectorBridge compares the query embedder's identity with the loaded
generation's and refuses to release hits on any difference (when AMC_EMBEDDER_BINDING=on).

An embedder declares itself with an `embedder_identity` attribute or method returning {"id", "model", ...}.
Without one, the class path is used, which is stable but coarse: declare an identity for production embedders.
"""
from __future__ import annotations

import os

FLAG = "AMC_EMBEDDER_BINDING"
_COMPARED = ("id", "model", "version")


def binding_enabled() -> bool:
    value = os.environ.get(FLAG, "off").strip().lower()
    if value not in ("on", "off"):
        raise ValueError(f"{FLAG} must be 'on' or 'off'")
    return os.environ.get("AMC_VERIFIED_SERVING_MODE", "off") == "enforce" and value == "on"


def embedder_identity(embedder, *, dimension: int | None = None) -> dict:
    declared = getattr(embedder, "embedder_identity", None)
    if callable(declared):
        declared = declared()
    if isinstance(declared, dict) and declared.get("id"):
        ident = {k: declared.get(k) for k in _COMPARED if declared.get(k) is not None}
    else:
        cls = type(embedder)
        ident = {"id": f"{cls.__module__}.{cls.__qualname__}"}
        model = getattr(embedder, "model_name", None) or getattr(embedder, "_model_name", None)
        if model:
            ident["model"] = str(model)
    dim = dimension if dimension is not None else getattr(embedder, "_dim", None)
    if dim:
        ident["dimension"] = int(dim)
    return ident


def same_embedder(index_identity, query_identity) -> bool:
    if not isinstance(index_identity, dict) or not isinstance(query_identity, dict):
        return False
    return all(index_identity.get(k) == query_identity.get(k) for k in _COMPARED)


__all__ = ["FLAG", "binding_enabled", "embedder_identity", "same_embedder"]
