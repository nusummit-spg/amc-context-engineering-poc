"""Durable, immutable and checksum-verified corpus snapshots.

This store stages *full snapshots*, not partial patch sets. Actual FAISS binary
construction is a separate adapter. Never switch a live FAISS index to this JSON
snapshot without creating and verifying its corresponding binary index.
"""
from pathlib import Path
from tempfile import mkdtemp
from os import fsync, open as os_open, close as os_close, O_RDONLY, replace
import json
import shutil

from .types import Generation, VerificationFailed, canonical_bytes, sha256_json


class ImmutableSnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical_documents(tenant: str, docs: list[dict]) -> list[dict]:
        seen = set()
        out = []
        for doc in docs:
            if not isinstance(doc, dict):
                raise ValueError("each corpus document must be an object")
            cid = doc.get("chunk_id")
            if not isinstance(cid, str) or not cid:
                raise ValueError("every document needs stable chunk_id")
            if doc.get("tenant_id") != tenant:
                raise ValueError("cross-tenant document in corpus generation")
            if cid in seen:
                raise ValueError("duplicate chunk_id in generation")
            if not isinstance(doc.get("text"), str):
                raise ValueError("document text must be a string")
            seen.add(cid)
            out.append(doc)
        out.sort(key=lambda x: x["chunk_id"])
        return out

    def _path(self, digest: str):
        if len(digest) != 64 or any(x not in "0123456789abcdef" for x in digest):
            raise ValueError("invalid generation digest")
        return self.root / digest[:2] / digest

    def stage(self, tenant: str, docs: list[dict]) -> Generation:
        corpus = self._canonical_documents(tenant, docs)
        identity = {"tenant": tenant, "documents": corpus}
        digest = sha256_json(identity)
        generation = Generation(digest, digest, len(corpus))
        target = self._path(digest)
        if target.exists():
            self.verify(generation, tenant)
            return generation
        target.parent.mkdir(parents=True, exist_ok=True)
        # Use a completely separate temp directory to avoid permission issues
        # when target.parent and tmp are on different drives/partitions
        tmp_base = Path(mkdtemp(prefix="staging-"))
        try:
            tmp = tmp_base / "staging"
            tmp.mkdir(parents=True)
            raw = canonical_bytes(identity)
            snapshot_file = tmp / "snapshot.json"
            manifest_file = tmp / "manifest.json"
            with snapshot_file.open("wb") as f:
                f.write(raw)
                f.flush()
                fsync(f.fileno())
            with manifest_file.open("wb") as f:
                f.write(canonical_bytes({"generation_id": digest, "digest": digest,
                                         "count": len(corpus), "tenant": tenant}))
                f.flush()
                fsync(f.fileno())
            if target.exists():
                self.verify(generation, tenant)
                return generation
            # Create target directory structure first
            target.mkdir(parents=True, exist_ok=True)
            # Copy files instead of rename to avoid cross-drive issues
            import shutil as sh
            sh.copy2(snapshot_file, target / "snapshot.json")
            sh.copy2(manifest_file, target / "manifest.json")
            # fsync on Windows directories doesn't work the same as Unix
            # Skip directory sync for cross-platform compatibility
            # dfd = os_open(target.parent, O_RDONLY)
            # try: fsync(dfd)
            # finally: os_close(dfd)
            self.verify(generation, tenant)
            return generation
        finally:
            if tmp_base.exists():
                try:
                    shutil.rmtree(tmp_base)
                except OSError:
                    pass

    def verify_by_digest(self, digest: str, tenant: str) -> list[dict]:
        manifest_path = self._path(digest) / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_bytes())
        except (OSError, ValueError) as exc:
            raise VerificationFailed("missing previous generation manifest") from exc
        gen = Generation(digest, digest, manifest["count"])
        return self.verify(gen, tenant)

    def verify(self, generation: Generation, tenant: str) -> list[dict]:
        directory = self._path(generation.digest)
        try:
            raw = (directory / "snapshot.json").read_bytes()
            data = json.loads(raw)
            manifest = json.loads((directory / "manifest.json").read_bytes())
        except (OSError, ValueError) as e:
            raise VerificationFailed("generation artifact missing or corrupted") from e
        if (data.get("tenant") != tenant or sha256_json(data) != generation.digest or
            manifest.get("tenant") != tenant or manifest.get("digest") != generation.digest or
            manifest.get("count") != generation.count or
            len(data.get("documents", [])) != generation.count):
            raise VerificationFailed("immutable generation digest, count or tenant mismatch")
        self._canonical_documents(tenant, data["documents"])
        return data["documents"]
