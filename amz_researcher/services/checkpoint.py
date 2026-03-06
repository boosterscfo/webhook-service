import json
import logging
import time
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path("/tmp/amz_research")
EXPIRE_SECONDS = 24 * 60 * 60  # 24 hours


class Checkpoint:
    def __init__(self, keyword: str):
        safe_name = keyword.replace(" ", "_").replace("/", "_")
        self.base_dir = CHECKPOINT_DIR / safe_name
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._clean_expired()

    def _meta_path(self) -> Path:
        return self.base_dir / "_meta.json"

    def _clean_expired(self):
        meta = self._meta_path()
        if meta.exists():
            data = json.loads(meta.read_text())
            if time.time() - data.get("created_at", 0) > EXPIRE_SECONDS:
                logger.info("Checkpoint expired, clearing: %s", self.base_dir)
                self.clear()
                self.base_dir.mkdir(parents=True, exist_ok=True)
        # Write/refresh meta
        meta.write_text(json.dumps({"created_at": time.time()}))

    def save(self, step: str, items: list[BaseModel]):
        path = self.base_dir / f"{step}.json"
        data = [item.model_dump() for item in items]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.info("Checkpoint saved: %s (%d items)", path, len(data))

    def load(self, step: str, model_cls: type[BaseModel]) -> list[BaseModel] | None:
        path = self.base_dir / f"{step}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            items = [model_cls.model_validate(d) for d in data]
            logger.info("Checkpoint loaded: %s (%d items)", path, len(items))
            return items
        except Exception:
            logger.warning("Checkpoint corrupted, ignoring: %s", path)
            return None

    def clear(self):
        if self.base_dir.exists():
            for f in self.base_dir.iterdir():
                f.unlink()
            self.base_dir.rmdir()
            logger.info("Checkpoint cleared: %s", self.base_dir)
