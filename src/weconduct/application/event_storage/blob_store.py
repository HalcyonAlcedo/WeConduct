"""Content-addressed blob store with dedup (design doc §7.1).

Large values (variable snapshots, runtime previews, node IO) are moved out of
records and stored once per unique content, keyed by SHA-256 of the msgpack
encoding. Events and checkpoints keep only the blob_id. Identical content
written repeatedly (e.g. the same keyframe landing in both debug_keyframes and
debug_snapshots) collapses to a single blob.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import uuid

from weconduct.packaging.msgpack_codec import packb, unpackb


class BlobError(ValueError):
    pass


class BlobStore:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def put(self, value: object) -> str:
        """Store value if new; return its content-addressed blob_id."""
        payload = packb(value)
        blob_id = sha256(payload).hexdigest()
        path = self._path_for(blob_id)
        if path.exists():
            return blob_id
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        temp_path.write_bytes(payload)
        temp_path.replace(path)
        return blob_id

    def get(self, blob_id: str) -> object:
        path = self._path_for(blob_id)
        if not path.exists():
            raise BlobError(f"blob missing: {blob_id}")
        payload = path.read_bytes()
        if sha256(payload).hexdigest() != blob_id:
            raise BlobError(f"blob content hash mismatch: {blob_id}")
        return unpackb(payload)

    def try_get(self, blob_id: str | None) -> object | None:
        """Return the blob value, or None if the id is missing/corrupt.

        Used on the projection read path so a missing/corrupt blob degrades to
        an absent field with a diagnostic instead of crashing (design doc §5).
        """
        if not isinstance(blob_id, str) or not blob_id.strip():
            return None
        try:
            return self.get(blob_id)
        except BlobError:
            return None

    def exists(self, blob_id: str) -> bool:
        return self._path_for(blob_id).exists()

    def _path_for(self, blob_id: str) -> Path:
        if len(blob_id) < 2:
            raise BlobError(f"invalid blob_id: {blob_id!r}")
        return self._root / blob_id[:2] / f"{blob_id}.blob"
