from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

_FILE_INDEX: dict[uuid.UUID, Path] = {}


def _base_dir() -> Path:
    base = Path(tempfile.gettempdir()) / "nexa_files_stub"
    base.mkdir(parents=True, exist_ok=True)
    return base


def store_bytes(content: bytes, filename: str, content_type: str) -> uuid.UUID:
    file_id = uuid.uuid4()
    safe_name = filename or "file.bin"
    extension = Path(safe_name).suffix or ".bin"
    file_path = _base_dir() / f"{file_id}{extension}"
    file_path.write_bytes(content)
    _FILE_INDEX[file_id] = file_path
    return file_id


def get_bytes(file_id: uuid.UUID) -> bytes:
    path = _FILE_INDEX.get(file_id)
    if path is None or not path.exists():
        raise FileNotFoundError(f"file_id not found: {file_id}")
    return path.read_bytes()
