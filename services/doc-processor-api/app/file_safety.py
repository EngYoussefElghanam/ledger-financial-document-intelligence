"""
file_safety.py

Small helpers for handling untrusted uploaded filenames and
user-supplied document_ids before they ever touch the filesystem.
Kept separate from main.py so the HTTP layer stays thin, per the
project's existing convention.
"""

import re
from pathlib import Path

# document_id must be a plain token: letters, digits, dash, underscore.
# No dots, slashes, or path separators of any kind.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")

PDF_MAGIC = b"%PDF-"


def sanitize_document_id(document_id: str) -> str:
    """
    Validate a caller-supplied document_id. Raises ValueError rather than
    trying to 'clean' the input - an id containing '..' or '/' should be
    rejected outright, not silently rewritten.
    """
    if not document_id or not _SAFE_ID_RE.match(document_id):
        raise ValueError(f"Invalid document_id: {document_id!r}")
    return document_id


def safe_upload_filename(filename: str) -> str:
    """
    Derive a safe on-disk filename from an uploaded file's client-supplied
    name. Strips any directory components (Path(...).name drops '../' and
    absolute-path prefixes) and rejects degenerate results.
    """
    if not filename:
        raise ValueError("Empty filename")
    name = Path(filename).name
    if not name or name in (".", "..") or not name.lower().endswith(".pdf"):
        raise ValueError(f"Invalid filename: {filename!r}")
    return name


def resolve_within(base_dir: Path, filename: str) -> Path:
    """
    Build base_dir / filename and verify the resolved path is still
    actually inside base_dir. Catches traversal attempts that survive
    name-stripping (e.g. via symlinks) as a second line of defense.
    """
    base_resolved = base_dir.resolve()
    candidate = (base_dir / filename).resolve()
    if base_resolved != candidate and base_resolved not in candidate.parents:
        raise ValueError(f"Path would escape base directory: {filename!r}")
    return candidate


def looks_like_pdf(content: bytes) -> bool:
    """Check real magic bytes instead of trusting content_type/extension."""
    return content[:5] == PDF_MAGIC


def unique_variant(base_dir: Path, filename: str) -> str:
    """
    If filename already exists in base_dir, return a numbered variant
    (file.pdf -> file_1.pdf -> file_2.pdf ...) instead of overwriting
    a previous upload with the same name.
    """
    candidate = base_dir / filename
    if not candidate.exists():
        return filename

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    n = 1
    while (base_dir / f"{stem}_{n}{suffix}").exists():
        n += 1
    return f"{stem}_{n}{suffix}"