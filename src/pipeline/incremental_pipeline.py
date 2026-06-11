from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import JobPosting

logger = logging.getLogger(__name__)


@dataclass
class PipelineState:
    in_progress: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    cached: list[str] = field(default_factory=list)
    total: int = 0
    ingested: int = 0
    skipped: int = 0
    start_time: float = 0.0
    end_time: float = 0.0


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


class IncrementalJobPipeline:
    def __init__(
        self,
        source_name: str,
        session_factory: async_sessionmaker[AsyncSession],
        state_dir: str = "data/pipeline",
        batch_size: int = 100,
        checkpoint_interval: int = 100,
    ) -> None:
        self.source_name = source_name
        self.session_factory = session_factory
        self.batch_size = batch_size
        self.checkpoint_interval = checkpoint_interval
        self.state_path = Path(state_dir) / f"{source_name}_state.json"
        self.state = PipelineState()
        self._buffer: list[dict[str, Any]] = []
        self._records_since_checkpoint = 0

    @property
    def elapsed(self) -> float:
        if self.state.start_time == 0:
            return 0.0
        end = self.state.end_time or time.time()
        return end - self.state.start_time

    async def checkpoint(self) -> PipelineState:
        await self.flush()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state.end_time = time.time()
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2, default=str))
        logger.info(
            "Checkpoint saved — total=%d completed=%d failed=%d cached=%d elapsed=%.2fs",
            self.state.total,
            len(self.state.completed),
            len(self.state.failed),
            len(self.state.cached),
            self.elapsed,
        )
        return self.state

    def recover(self) -> bool:
        if not self.state_path.exists():
            logger.info("No state file found at %s — starting fresh", self.state_path)
            return False
        try:
            raw = json.loads(self.state_path.read_text())
            self.state = PipelineState(**raw)
            orphaned = len(self.state.in_progress)
            self.state.in_progress = []
            logger.info(
                "Recovered state — total=%d completed=%d orphaned_in_progress=%d skipped=%d",
                self.state.total,
                len(self.state.completed),
                orphaned,
                self.state.skipped,
            )
            return True
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to recover state from %s: %s", self.state_path, exc)
            return False

    async def write_batch(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return

        if self.state.start_time == 0:
            self.state.start_time = time.time()

        for record in records:
            source_id = str(record.get("id", record.get("source_id", "")))
            if not source_id:
                logger.warning("Record missing id/source_id — skipping")
                self.state.skipped += 1
                continue

            if source_id in self.state.completed or source_id in self.state.in_progress:
                self.state.skipped += 1
                continue

            self.state.in_progress.append(source_id)
            self._buffer.append(record)
            self.state.total += 1

            if len(self._buffer) >= self.batch_size:
                await self._flush()

    async def flush(self) -> None:
        if self._buffer:
            await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return

        records = self._buffer
        self._buffer = []
        source_ids = []

        try:
            async with self.session_factory() as session:
                for record in records:
                    job = JobPosting(
                        source_id=str(record.get("id", record.get("source_id", ""))),
                        source=self.source_name,
                        title=str(record.get("title", "")),
                        company=str(record.get("company", "")),
                        company_domain=record.get("company_domain"),
                        location=record.get("location"),
                        description=record.get("description"),
                        skills=record.get("skills", []),
                        industry=record.get("industry"),
                        role_category=record.get("role_category"),
                        posted_at=_parse_dt(record.get("posted_at")),
                        url=record.get("url"),
                        raw=record,
                    )
                    session.add(job)
                    sid = job.source_id
                    source_ids.append(sid)

                await session.commit()

            for sid in source_ids:
                self.state.completed.append(sid)
                if sid in self.state.in_progress:
                    self.state.in_progress.remove(sid)
            self.state.ingested += len(source_ids)

            self._records_since_checkpoint += len(source_ids)
            if self._records_since_checkpoint >= self.checkpoint_interval:
                await self.checkpoint()
                self._records_since_checkpoint = 0

        except Exception:
            logger.exception("Batch flush failed — %d records will be retried", len(records))
            self._buffer.extend(records)
            self.state.failed.extend(source_ids)
            for sid in source_ids:
                if sid in self.state.in_progress:
                    self.state.in_progress.remove(sid)
            raise

    def mark_failed(self, source_ids: list[str]) -> None:
        for sid in source_ids:
            if sid not in self.state.failed:
                self.state.failed.append(sid)
            if sid in self.state.in_progress:
                self.state.in_progress.remove(sid)

    def mark_cached(self, source_ids: list[str]) -> None:
        for sid in source_ids:
            if sid not in self.state.cached:
                self.state.cached.append(sid)
            if sid in self.state.in_progress:
                self.state.in_progress.remove(sid)
