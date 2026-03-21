"""Local filesystem storage adapter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings

_FILENAME_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class LocalFileStorage:
    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = (base_path or settings.local_storage_path).resolve()

    def save_file(self, *, storage_key: str, content: bytes) -> None:
        path = self._resolve_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def get_file_stream(self, *, storage_key: str) -> BinaryIO:
        return self._resolve_path(storage_key).open("rb")

    def read_file(self, *, storage_key: str) -> bytes:
        return self._resolve_path(storage_key).read_bytes()

    def delete_file(self, *, storage_key: str) -> None:
        path = self._resolve_path(storage_key)
        if path.exists():
            path.unlink()

    def build_public_or_signed_url(self, *, storage_key: str) -> str:
        return f"local://{storage_key}"

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        basename = Path(filename).name.strip()
        sanitized = _FILENAME_SANITIZE_PATTERN.sub("_", basename)
        sanitized = sanitized.strip("._")
        return sanitized or "document.bin"

    def _resolve_path(self, storage_key: str) -> Path:
        path = (self.base_path / storage_key).resolve()
        if not str(path).startswith(str(self.base_path)):
            msg = "Attempted to access a storage path outside the configured base directory."
            raise ValueError(msg)
        return path
