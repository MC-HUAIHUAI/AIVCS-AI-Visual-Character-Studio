"""Dummy AI 3D Runtime - standalone localhost HTTP process (Phase 2).

A real independent process that mimics a local AI 3D runtime WITHOUT any real
AI: it produces a deterministic GLB, simulates progress and long tasks, and
supports create/poll/cancel/download/health.

Purpose: validate the EmbeddedClient + Runtime Manager + Provider + Job +
ModelStore pipeline end-to-end, so a real runtime (TripoSR/Hunyuan3D/TRELLIS)
can later be swapped in without redesigning the architecture.

NOT real AI. No model download. No external API. No random geometry.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[5]  # dummy/ -> repo root
sys.path.insert(0, str(ROOT))

from backend.app.services.glb_builder import Primitive, build_glb  # noqa: E402

TASK_DURATION_SECONDS = 3.0


@dataclass
class Task:
    id: str
    status: str = "queued"
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    output_bytes: bytes | None = None
    cancelled: bool = False
    thread: threading.Thread = None  # type: ignore[assignment]


class DummyRuntime:
    def __init__(self, token: str):
        self._token = token
        self._tasks: dict[str, Task] = {}

    def _run_task(self, task: Task) -> None:
        task.status = "running"
        task.message = "started"
        steps = max(1, int(TASK_DURATION_SECONDS * 4))
        for i in range(steps):
            time.sleep(TASK_DURATION_SECONDS / steps)
            if task.cancelled:
                task.status = "cancelled"
                task.message = "cancelled by user"
                return
            task.progress = min(1.0, (i + 1) / steps)
            task.message = f"generating {int(task.progress * 100)}%"
        # Deterministic GLB (no random geometry).
        try:
            prims = [Primitive("box", (0.4, 0.4, 0.4), center=(0, 0.4, 0), color="#44AA66")]
            task.output_bytes = build_glb(prims)
            task.status = "done"
            task.progress = 1.0
            task.message = "done"
        except Exception as exc:  # noqa: BLE001
            task.status = "failed"
            task.error = str(exc)
            task.message = "failed"

    def create_task(self, summary: str) -> Task:
        task = Task(id=secrets.token_hex(8))
        self._tasks[task.id] = task
        task.thread = threading.Thread(target=self._run_task, args=(task,), daemon=True)
        task.thread.start()
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task or task.status in ("done", "failed", "cancelled"):
            return False
        task.cancelled = True
        return True

    def handle(self, method: str, path: str, body: bytes, token: str | None = None) -> tuple[int, dict, bytes | None]:
        parts = urlparse(path)
        p = parts.path
        if p == "/health":
            return 200, {"status": "ok", "tasks": len(self._tasks)}, None
        if not self._auth(token or ""):
            return 401, {"detail": "unauthorized"}, None
        if p == "/task" and method == "POST":
            data = json.loads(body or b"{}")
            task = self.create_task(str(data.get("summary", ""))[:200])
            return 202, {"taskId": task.id, "status": task.status}, None
        if p.startswith("/task/"):
            segs = p.split("/")
            task_id = segs[2] if len(segs) >= 3 else ""
            if method == "GET" and len(segs) == 3:
                t = self.get_task(task_id)
                if not t:
                    return 404, {"detail": "task not found"}, None
                return 200, self._task_payload(t), None
            if method == "POST" and len(segs) == 4 and segs[3] == "cancel":
                ok = self.cancel_task(task_id)
                return 200 if ok else 409, {"cancelled": ok}, None
            if method == "GET" and len(segs) == 4 and segs[3] == "output":
                t = self.get_task(task_id)
                if not t:
                    return 404, {"detail": "task not found"}, None
                if t.status != "done" or not t.output_bytes:
                    return 409, {"detail": "output not ready"}, None
                return 200, {}, t.output_bytes
        return 404, {"detail": "not found"}, None

    def _auth(self, token: str) -> bool:
        return secrets.compare_digest(token, self._token)

    @staticmethod
    def _task_payload(t: Task) -> dict:
        return {
            "taskId": t.id,
            "status": t.status,
            "progress": t.progress,
            "message": t.message,
            "error": t.error,
        }


class DummyHandler(BaseHTTPRequestHandler):
    runtime: DummyRuntime

    def log_message(self, *_):  # silence (token must not enter logs)
        pass

    def _respond(self, code: int, json_obj: dict, raw: bytes | None) -> None:
        self.send_response(code)
        if raw is not None:
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            data = json.dumps(json_obj).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    def do_GET(self):
        token = self.headers.get("X-AIVCS-Token", "")
        code, obj, raw = DummyRuntime.handle(self.runtime, "GET", self.path, b"", token)
        self._respond(code, obj, raw)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        token = self.headers.get("X-AIVCS-Token", "")
        code, obj, raw = DummyRuntime.handle(self.runtime, "POST", self.path, body, token)
        self._respond(code, obj, raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--token", type=str, required=True)
    parser.add_argument("--ready-file", type=str, default="")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), DummyHandler)
    DummyHandler.runtime = DummyRuntime(args.token)
    if args.ready_file:
        Path(args.ready_file).write_text("ready", encoding="utf-8")
    server.serve_forever()


if __name__ == "__main__":
    main()
