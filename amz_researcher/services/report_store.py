"""File-based HTML report store with TTL cleanup."""
from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)


class ReportStore:
    """Save / serve / cleanup HTML reports on the local filesystem."""

    def __init__(self, base_dir: str = "data/reports", ttl_days: int = 30) -> None:
        self._base = Path(base_dir)
        self._ttl_seconds = ttl_days * 86_400
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, html_bytes: bytes, label: str = "") -> str:
        """Save HTML bytes to disk. Returns the report_id (uuid)."""
        report_id = uuid.uuid4().hex
        path = self._base / f"{report_id}.html"
        path.write_bytes(html_bytes)
        logger.info("Report saved: id=%s label=%s size=%d", report_id, label, len(html_bytes))
        return report_id

    def get_path(self, report_id: str) -> Path | None:
        """Return file path if exists, else None."""
        # sanitize: only allow hex chars
        clean_id = "".join(c for c in report_id if c in "0123456789abcdef")
        if not clean_id:
            return None
        path = self._base / f"{clean_id}.html"
        return path if path.is_file() else None

    def cleanup_expired(self) -> int:
        """Delete files older than TTL. Returns count of deleted files."""
        now = time.time()
        deleted = 0
        for path in self._base.glob("*.html"):
            age = now - path.stat().st_mtime
            if age > self._ttl_seconds:
                path.unlink()
                deleted += 1
        if deleted:
            logger.info("Report cleanup: deleted %d expired files", deleted)
        return deleted
