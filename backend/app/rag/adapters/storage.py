"""Document-object storage abstraction.

The first release is intentionally local-first.  The stable ``storage_key``
means an S3/MinIO adapter can be added without changing document workflows.
"""

from pathlib import Path

from backend.core.conf import settings


class LocalStorage:
    def __init__(self) -> None:
        self.root = Path(settings.RAG_STORAGE_LOCAL_PATH).resolve()

    def put(self, *, key: str, content: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get(self, *, key: str) -> bytes:
        return (self.root / key).read_bytes()

    def delete(self, *, key: str) -> None:
        path = self.root / key
        if path.exists():
            path.unlink()


storage = LocalStorage()
