"""File-handling helpers (safe filenames + upload limits)."""
from app.core.config import UPLOAD_DIR, MAX_UPLOAD_BYTES  # re-exported for convenience

__all__ = ["UPLOAD_DIR", "MAX_UPLOAD_BYTES", "safe_filename"]


def safe_filename(name: str) -> str:
    """Strip path components and keep only a conservative character set."""
    name = (name or "file").replace("\\", "/").split("/")[-1]
    out = "".join(c if (c.isalnum() or c in ("-", "_", ".", " ")) else "_" for c in name).strip()
    return out[:200] or "file"
