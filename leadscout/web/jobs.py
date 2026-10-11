"""Run pipeline steps in a background thread and keep their log for the dashboard."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

STEPS: dict[str, str] = {
    "run": "Full run (discover → audit → score → draft)",
    "discover": "Discover businesses",
    "audit": "Audit websites",
    "score": "Score leads",
    "draft": "Write drafts",
    "send_dry": "Send emails (dry run)",
    "send": "Send approved emails",
    "check_replies": "Check inbox for replies",
}


STEP_HELP: dict[str, str] = {
    "run": "Finds businesses, checks their websites, scores them and writes messages. Start here.",
    "discover": "Only search for new businesses in your area.",
    "audit": "Check websites of businesses not checked yet.",
    "score": "Re-score leads, e.g. after changing what you sell.",
    "draft": "Write messages for good leads that don't have one yet.",
    "send_dry": "Shows exactly what would be emailed. Sends nothing.",
    "send": "Emails the messages you approved, within your daily limit.",
    "check_replies": "Reads your inbox: stops follow-ups to anyone who replied or opted out.",
}


@dataclass
class Job:
    id: int
    step: str
    status: str = "running"  # running | done | failed
    lines: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    finished: float | None = None

    def log(self, *parts: object) -> None:
        self.lines.append(" ".join(str(p) for p in parts))

    def as_dict(self) -> dict:
        return {"id": self.id, "step": self.step, "title": STEPS.get(self.step, self.step), "status": self.status,
                "lines": self.lines[-300:], "started": self.started, "finished": self.finished}


class JobRunner:
    """One job at a time: the pipeline steps share one database and polite rate limits."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seq = 0
        self.current: Job | None = None

    def busy(self) -> bool:
        return self.current is not None and self.current.status == "running"

    def start(self, step: str, fn: Callable[[Job], None]) -> Job:
        with self._lock:
            if self.busy():
                raise RuntimeError(f"'{self.current.step}' is still running")
            self._seq += 1
            job = Job(self._seq, step)
            self.current = job

        def target() -> None:
            try:
                fn(job)
                job.status = "done"
            except Exception as e:  # surface any failure in the dashboard log
                job.log(f"ERROR: {type(e).__name__}: {e}")
                job.status = "failed"
            finally:
                job.finished = time.time()

        threading.Thread(target=target, daemon=True, name=f"job-{step}").start()
        return job
