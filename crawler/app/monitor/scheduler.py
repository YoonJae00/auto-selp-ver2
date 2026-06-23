from __future__ import annotations

import logging
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class MonitorScheduler:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()
        self._started = False

    def start(self) -> None:
        if not self._started:
            self._scheduler.start(paused=True)
            self._started = True

    def shutdown(self) -> None:
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False

    def add_supplier_job(
        self,
        supplier_id: str,
        interval_hours: int,
        callback: Callable[[], Any],
    ) -> None:
        self.start()
        job_id = f"stock_check_{supplier_id}"
        self._scheduler.remove_job(job_id) if self._scheduler.get_job(job_id) else None
        self._scheduler.add_job(
            callback,
            IntervalTrigger(hours=interval_hours),
            id=job_id,
            replace_existing=True,
        )
        self._scheduler.resume_job(job_id)

    def remove_supplier_job(self, supplier_id: str) -> None:
        job_id = f"stock_check_{supplier_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        jobs = []
        for job in self._scheduler.get_jobs():
            if job.id.startswith("stock_check_"):
                supplier_id = job.id.replace("stock_check_", "")
                jobs.append({
                    "supplier_id": supplier_id,
                    "next_run": str(job.next_run_time) if job.next_run_time else None,
                    "interval_hours": job.trigger.interval.total_seconds() / 3600 if hasattr(job.trigger, "interval") else None,
                })
        return jobs

    def trigger_now(self, supplier_id: str, callback: Callable[[], Any]) -> None:
        job_id = f"stock_check_{supplier_id}"
        self._scheduler.add_job(
            callback,
            "date",
            id=f"{job_id}_manual_{supplier_id}",
            replace_existing=True,
        )
