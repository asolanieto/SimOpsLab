"""SQLite campaign journal and content-addressed local artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contracts import (
    ArtifactRef,
    CampaignSpec,
    RunResult,
    RunSpec,
    RunStatus,
    SystemOutcome,
)
from .serialization import (
    canonical_json,
    campaign_spec_from_dict,
    run_result_from_dict,
    to_json_value,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class CampaignConflictError(ValueError):
    """An existing campaign ID is bound to a different spec or backend."""


class CampaignBusyError(RuntimeError):
    """Another local coordinator currently owns the campaign lock."""


class SQLiteCampaignStore:
    """Local journal with an append-only event history and latest-state indexes."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @contextmanager
    def campaign_lock(self, campaign_id: str, *, timeout_s: float = 30.0):
        """Serialize local coordinators; the OS releases this lock if a process exits."""
        if not isinstance(campaign_id, str) or not campaign_id.strip():
            raise ValueError("campaign_id must be a non-empty string")
        if timeout_s < 0:
            raise ValueError("timeout_s must be non-negative")
        lock_directory = self.database_path.parent / f"{self.database_path.name}.locks"
        lock_directory.mkdir(parents=True, exist_ok=True)
        lock_name = hashlib.sha256(campaign_id.encode("utf-8")).hexdigest() + ".lock"
        lock_path = lock_directory / lock_name
        deadline = time.monotonic() + timeout_s

        with lock_path.open("a+b") as lock_file:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0, os.SEEK_END)
                if lock_file.tell() == 0:
                    lock_file.write(b"\0")
                    lock_file.flush()
                while True:
                    try:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise CampaignBusyError(
                                f"campaign {campaign_id!r} is already being run; retry later"
                            )
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                return

            import fcntl

            while True:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise CampaignBusyError(
                            f"campaign {campaign_id!r} is already being run; retry later"
                        )
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    backend_id TEXT NOT NULL,
                    backend_version TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
                    run_spec_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    latest_result_json TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    result_json TEXT,
                    PRIMARY KEY (run_id, attempt_number)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
                    run_id TEXT,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runs_campaign_idx ON runs(campaign_id, status);
                CREATE INDEX IF NOT EXISTS events_campaign_idx ON events(campaign_id, sequence);
                """
            )

    def register_campaign(
        self,
        campaign: CampaignSpec,
        backend_id: str,
        backend_version: str = "unknown",
    ) -> str:
        manifest = {
            "backend_id": backend_id,
            "backend_version": backend_version,
            "campaign": to_json_value(campaign),
        }
        manifest_json = canonical_json(manifest)
        fingerprint = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
        now = utc_now().isoformat()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT fingerprint FROM campaigns WHERE campaign_id = ?",
                (campaign.campaign_id,),
            ).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise CampaignConflictError(
                        f"campaign {campaign.campaign_id!r} already exists with a different "
                        "manifest or backend; use a new campaign_id"
                    )
                return fingerprint
            connection.execute(
                """INSERT INTO campaigns
                   (campaign_id, title, backend_id, backend_version, fingerprint, manifest_json,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'planned', ?, ?)""",
                (
                    campaign.campaign_id,
                    campaign.title,
                    backend_id,
                    backend_version,
                    fingerprint,
                    manifest_json,
                    now,
                    now,
                ),
            )
            for run in campaign.runs:
                connection.execute(
                    """INSERT INTO runs
                       (run_id, campaign_id, run_spec_json, status, updated_at)
                       VALUES (?, ?, ?, 'planned', ?)""",
                    (run.run_id, campaign.campaign_id, canonical_json(run), now),
                )
            self._event(
                connection,
                campaign.campaign_id,
                None,
                "campaign_registered",
                {"backend_id": backend_id, "fingerprint": fingerprint, "run_count": len(campaign.runs)},
            )
        return fingerprint

    def _event(
        self,
        connection: sqlite3.Connection,
        campaign_id: str,
        run_id: str | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO events (campaign_id, run_id, event_type, created_at, payload_json) "
            "VALUES (?, ?, ?, ?, ?)",
            (campaign_id, run_id, event_type, utc_now().isoformat(), canonical_json(payload)),
        )

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
        if row is None:
            return None
        manifest = json.loads(row["manifest_json"])
        return {
            "campaign_id": row["campaign_id"],
            "title": row["title"],
            "backend_id": row["backend_id"],
            "backend_version": row["backend_version"],
            "fingerprint": row["fingerprint"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "campaign": campaign_spec_from_dict(manifest["campaign"]),
        }

    def set_campaign_status(self, campaign_id: str, status: str) -> None:
        now = utc_now().isoformat()
        with self._connection() as connection:
            connection.execute(
                "UPDATE campaigns SET status = ?, updated_at = ? WHERE campaign_id = ?",
                (status, now, campaign_id),
            )
            self._event(connection, campaign_id, None, "campaign_status", {"status": status})

    def run_states(self, campaign_id: str) -> dict[str, dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT run_id, status, attempt_count FROM runs WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchall()
            failures = connection.execute(
                """SELECT a.run_id, COUNT(*) AS failures FROM attempts a
                   JOIN runs r ON r.run_id = a.run_id
                   WHERE r.campaign_id = ? AND a.status IN ('failed_infrastructure', 'interrupted')
                   GROUP BY a.run_id""",
                (campaign_id,),
            ).fetchall()
        failure_counts = {row["run_id"]: row["failures"] for row in failures}
        return {
            row["run_id"]: {
                "status": row["status"],
                "attempt_count": row["attempt_count"],
                "infrastructure_failures": failure_counts.get(row["run_id"], 0),
            }
            for row in rows
        }

    def start_attempt(self, run: RunSpec) -> int:
        now = utc_now().isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, attempt_count, campaign_id FROM runs WHERE run_id = ?",
                (run.run_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"run {run.run_id!r} is not registered")
            if row["status"] == RunStatus.RUNNING.value:
                raise RuntimeError(f"run {run.run_id!r} is already running")
            if row["status"] not in {
                RunStatus.PLANNED.value,
                RunStatus.FAILED_INFRASTRUCTURE.value,
                RunStatus.INTERRUPTED.value,
            }:
                raise RuntimeError(f"run {run.run_id!r} cannot start from state {row['status']!r}")
            attempt_number = int(row["attempt_count"]) + 1
            connection.execute(
                "INSERT INTO attempts (run_id, attempt_number, status, started_at) "
                "VALUES (?, ?, 'running', ?)",
                (run.run_id, attempt_number, now),
            )
            connection.execute(
                "UPDATE runs SET status = 'running', attempt_count = ?, updated_at = ? "
                "WHERE run_id = ?",
                (attempt_number, now, run.run_id),
            )
            self._event(
                connection,
                row["campaign_id"],
                run.run_id,
                "run_started",
                {"attempt_number": attempt_number},
            )
        return attempt_number

    def finish_attempt(self, result: RunResult, attempt_number: int) -> None:
        if result.status in (RunStatus.PLANNED, RunStatus.QUEUED, RunStatus.RUNNING):
            raise ValueError("a finished attempt must have a terminal RunStatus")
        result_json = canonical_json(result)
        now = utc_now().isoformat()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT campaign_id FROM runs WHERE run_id = ?", (result.run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"run {result.run_id!r} is not registered")
            updated = connection.execute(
                """UPDATE attempts SET status = ?, finished_at = ?, result_json = ?
                   WHERE run_id = ? AND attempt_number = ? AND status = 'running'""",
                (result.status.value, now, result_json, result.run_id, attempt_number),
            ).rowcount
            if updated != 1:
                raise RuntimeError("attempt is missing or already terminal")
            connection.execute(
                "UPDATE runs SET status = ?, latest_result_json = ?, updated_at = ? "
                "WHERE run_id = ?",
                (result.status.value, result_json, now, result.run_id),
            )
            self._event(
                connection,
                row["campaign_id"],
                result.run_id,
                "run_finished",
                {"attempt_number": attempt_number, "status": result.status.value},
            )

    def recover_interrupted(self, campaign_id: str) -> int:
        """Mark RUNNING attempts from a prior process as interrupted before resume."""
        recovered = 0
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT r.run_id, r.run_spec_json, r.attempt_count
                   FROM runs r WHERE r.campaign_id = ? AND r.status = 'running'""",
                (campaign_id,),
            ).fetchall()
            for row in rows:
                result = RunResult(
                    run_id=row["run_id"],
                    status=RunStatus.INTERRUPTED,
                    system_outcome=SystemOutcome.UNKNOWN,
                    finished_at=utc_now(),
                    failure_reason="process stopped before the attempt result was persisted",
                )
                result_json = canonical_json(result)
                connection.execute(
                    """UPDATE attempts SET status = 'interrupted', finished_at = ?, result_json = ?
                       WHERE run_id = ? AND attempt_number = ? AND status = 'running'""",
                    (utc_now().isoformat(), result_json, row["run_id"], row["attempt_count"]),
                )
                connection.execute(
                    "UPDATE runs SET status = 'interrupted', latest_result_json = ?, updated_at = ? "
                    "WHERE run_id = ?",
                    (result_json, utc_now().isoformat(), row["run_id"]),
                )
                self._event(
                    connection,
                    campaign_id,
                    row["run_id"],
                    "run_recovered_as_interrupted",
                    {"attempt_number": row["attempt_count"]},
                )
                recovered += 1
        return recovered

    def results(self, campaign_id: str) -> tuple[RunResult, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT latest_result_json FROM runs
                   WHERE campaign_id = ? AND latest_result_json IS NOT NULL ORDER BY run_id""",
                (campaign_id,),
            ).fetchall()
        return tuple(run_result_from_dict(json.loads(row["latest_result_json"])) for row in rows)

    def events(self, campaign_id: str) -> tuple[dict[str, Any], ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE campaign_id = ? ORDER BY sequence", (campaign_id,)
            ).fetchall()
        return tuple(
            {
                "sequence": row["sequence"],
                "run_id": row["run_id"],
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        )

    def record_event(
        self,
        campaign_id: str,
        event_type: str,
        payload: dict[str, Any],
        run_id: str | None = None,
    ) -> None:
        with self._connection() as connection:
            self._event(connection, campaign_id, run_id, event_type, payload)


class FilesystemArtifactStore:
    """Immutable SHA-256-addressed artifacts stored under one local directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        name: str,
        content: bytes,
        media_type: str,
        schema_version: str | None = None,
    ) -> ArtifactRef:
        digest = hashlib.sha256(content).hexdigest()
        destination = self.root / digest[:2] / digest
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            handle, temporary_name = tempfile.mkstemp(prefix=".artifact-", dir=destination.parent)
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(content)
                os.replace(temporary_name, destination)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        return ArtifactRef(
            name=name,
            uri=f"sha256:{digest}",
            media_type=media_type,
            sha256=digest,
            size_bytes=len(content),
            schema_version=schema_version,
        )

    def get(self, reference: ArtifactRef) -> bytes:
        if not reference.sha256 or len(reference.sha256) != 64:
            raise ValueError("artifact reference must contain a SHA-256 digest")
        path = self.root / reference.sha256[:2] / reference.sha256
        content = path.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
        if actual != reference.sha256:
            raise ValueError("artifact checksum mismatch")
        return content
