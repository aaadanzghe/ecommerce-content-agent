"""SQLite-backed generation task queue."""

import json
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def initialize(self, recover_running: bool = False) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_tasks (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT,
                    error_json TEXT,
                    upstream_task_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            if recover_running:
                conn.execute(
                    "UPDATE generation_tasks SET status = 'queued', updated_at = ? WHERE status = 'running'",
                    (_now(),),
                )

    def create(self, kind: str, request: dict) -> dict:
        task_id = uuid.uuid4().hex
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO generation_tasks (id, kind, status, request_json, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?, ?)",
                (task_id, kind, json.dumps(request, ensure_ascii=False), now, now),
            )
        return self.get(task_id)

    def claim_next(self) -> Optional[dict]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT id FROM generation_tasks WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE generation_tasks SET status = 'running', updated_at = ? WHERE id = ?",
                (_now(), row["id"]),
            )
        return self.get(row["id"])

    def succeed(self, task_id: str, result: dict) -> None:
        self._finish(task_id, "succeeded", result_json=result)

    def fail(self, task_id: str, error: dict) -> None:
        self._finish(task_id, "failed", error_json=error)

    def set_upstream_task_id(self, task_id: str, upstream_task_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE generation_tasks SET upstream_task_id = ?, updated_at = ? WHERE id = ?",
                (upstream_task_id, _now(), task_id),
            )

    def get(self, task_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            return None
        task = dict(row)
        task["request"] = json.loads(task.pop("request_json"))
        task["result"] = json.loads(task.pop("result_json")) if task.get("result_json") else None
        task["error"] = json.loads(task.pop("error_json")) if task.get("error_json") else None
        return task

    def _finish(self, task_id: str, status: str, result_json=None, error_json=None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE generation_tasks SET status = ?, result_json = ?, error_json = ?, updated_at = ? WHERE id = ?",
                (
                    status,
                    json.dumps(result_json, ensure_ascii=False) if result_json is not None else None,
                    json.dumps(error_json, ensure_ascii=False) if error_json is not None else None,
                    _now(),
                    task_id,
                ),
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class TaskWorker:
    def __init__(self, store: TaskStore, handler: Callable[[dict], dict], poll_interval: float = 0.25):
        self.store = store
        self.handler = handler
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="generation-task-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            task = self.store.claim_next()
            if task is None:
                self._stop.wait(self.poll_interval)
                continue
            try:
                self.store.succeed(task["id"], self.handler(task))
            except Exception as exc:
                logger.exception("Generation task %s failed", task["id"])
                self.store.fail(task["id"], {"type": type(exc).__name__, "message": str(exc)})
