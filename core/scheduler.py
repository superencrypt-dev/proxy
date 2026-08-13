import time
import inspect
import asyncio
import threading
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any


class AutoScheduler:
    """Background scheduler loop for recurring scraping and health check tasks."""

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.interval_minutes: float = 0.0
        self.last_run: str = ""
        self.next_run: str = ""
        self.task_callback: Optional[Callable] = None
        self.on_log: Optional[Callable[[str], None]] = None
        self._check_interval: float = 0.5

    def start(
        self,
        interval_minutes: float,
        task_callback: Callable,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Starts the background schedule loop."""
        if self.is_running():
            self.stop()

        self.interval_minutes = interval_minutes
        self.task_callback = task_callback
        self.on_log = on_log
        self._stop_event.clear()

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Gracefully stops the schedule loop."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def is_running(self) -> bool:
        """Returns True if the background scheduler thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def _execute_task(self) -> None:
        """Executes the task callback, handling both sync and async functions."""
        now = datetime.now()
        self.last_run = now.strftime("%Y-%m-%d %H:%M:%S")
        next_dt = now + timedelta(minutes=self.interval_minutes)
        self.next_run = next_dt.strftime("%Y-%m-%d %H:%M:%S")

        if self.on_log:
            self.on_log("[Scheduler] Executing scheduled update task...")

        if self.task_callback:
            try:
                if inspect.iscoroutinefunction(self.task_callback):
                    asyncio.run(self.task_callback())
                else:
                    res = self.task_callback()
                    if asyncio.iscoroutine(res):
                        asyncio.run(res)
            except Exception as e:
                if self.on_log:
                    self.on_log(f"[Scheduler] Task error: {str(e)}")

    def _run_loop(self) -> None:
        """Main background loop."""
        while not self._stop_event.is_set():
            self._execute_task()

            interval_sec = max(0.05, self.interval_minutes * 60.0)
            target_time = time.time() + interval_sec

            while not self._stop_event.is_set() and time.time() < target_time:
                step = min(getattr(self, "_check_interval", 0.5), max(0.005, target_time - time.time()))
                time.sleep(step)

    def get_status(self) -> Dict[str, Any]:
        """Returns status of the scheduler."""
        return {
            "status": "RUNNING" if self.is_running() else "STOPPED",
            "interval_minutes": self.interval_minutes,
            "last_run": self.last_run,
            "next_run": self.next_run,
        }
