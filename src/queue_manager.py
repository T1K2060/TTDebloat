"""
Processes a batch of apps to uninstall + deep-clean.

Strategy: run up to MAX_CONCURRENT non-Win32 apps at once, but only one Win32
app at a time (they often share the same installer service). Anything that
fails gets one more attempt, alone, after the batch.

Before each uninstall we check whether the app is running. If it is, the
in_use_callback asks the user; "bypass" closes its processes and continues,
anything else skips that app (skipped apps are NOT retried).

Runs on background threads and reports progress through callbacks.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from src.cleanup import deep_clean, snapshot_paths_for_app
from src.friendly_log import friendly_line
from src.inuse import find_running_processes, kill_processes
from src.uninstall import uninstall_app

MAX_CONCURRENT = 3

STATUS_QUEUE = "queue"
STATUS_ACTIVE = "active"
STATUS_RETRYING = "retrying"
STATUS_DONE_SUCCESS = "done_success"
STATUS_DONE_FAILED = "done_failed"
STATUS_SKIPPED = "skipped"

_OK, _FAILED, _SKIPPED = "ok", "failed", "skipped"


class UninstallQueue:
    """
    status_callback(uid, status)
    log_callback(uid, raw_line, friendly_line_or_none)
    in_use_callback(uid, processes) -> True to bypass (close them), False to skip.
        Blocks until the user decides.
    """

    def __init__(self, status_callback: Callable, log_callback: Callable,
                 in_use_callback: Optional[Callable] = None):
        self.status_callback = status_callback
        self.log_callback = log_callback
        self.in_use_callback = in_use_callback
        self._lock = threading.Lock()

    def run_batch(self, app_entries: list[dict], all_detected_apps: list[dict]) -> None:
        for entry in app_entries:
            self._set_status(entry, STATUS_QUEUE)

        win32_apps = [e for e in app_entries if e["detected"].get("source") == "win32"]
        other_apps = [e for e in app_entries if e["detected"].get("source") != "win32"]
        failed_first_pass = []

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
            results = list(pool.map(lambda e: self._process_one(e, all_detected_apps), other_apps))
        failed_first_pass += [e for e, r in zip(other_apps, results) if r == _FAILED]

        for entry in win32_apps:
            if self._process_one(entry, all_detected_apps) == _FAILED:
                failed_first_pass.append(entry)

        for entry in failed_first_pass:
            self._set_status(entry, STATUS_RETRYING)
            self._process_one(entry, all_detected_apps, is_retry=True)

    def _process_one(self, entry: dict, all_detected_apps: list[dict], is_retry: bool = False) -> str:
        uid = _app_id(entry)

        def log(raw_line: str) -> None:
            self.log_callback(uid, raw_line, friendly_line(raw_line))

        # One app crashing must never take down the rest of the batch.
        try:
            self._set_status(entry, STATUS_ACTIVE)
            if is_retry:
                log("--- Retrying on its own ---")

            if not self._clear_running_processes(entry, uid, log):
                self._set_status(entry, STATUS_SKIPPED)
                return _SKIPPED

            snapshot = []
            if not entry.get("cleanup_paths"):
                snapshot = snapshot_paths_for_app(entry["detected"])

            if not uninstall_app(entry, log=log):
                self._set_status(entry, STATUS_DONE_FAILED)
                return _FAILED

            summary = deep_clean(entry, snapshot, _other_install_paths(entry, all_detected_apps), log=log)
            log(f"Cleanup summary: {len(summary['removed_paths'])} paths removed, "
                f"{len(summary['removed_registry_keys'])} registry entries removed")
            self._set_status(entry, STATUS_DONE_SUCCESS)
            return _OK
        except Exception as error:
            log(f"ERROR: unexpected failure: {error}")
            self._set_status(entry, STATUS_DONE_FAILED)
            return _FAILED

    def _clear_running_processes(self, entry: dict, uid, log) -> bool:
        """True = safe to proceed (nothing running, or user bypassed). False = skip app."""
        running = find_running_processes(entry)
        if not running:
            return True

        names = ", ".join(sorted({p["name"] for p in running}))
        log(f"⚠️  App is in use ({names}) — waiting for your decision")

        bypass = self.in_use_callback(uid, running) if self.in_use_callback else False
        if not bypass:
            log("⚠️  Skipped — app in use")
            return False

        count = kill_processes([p["pid"] for p in running])
        log(f"⚠️  Closed {count} running process(es), continuing")
        return True

    def _set_status(self, entry: dict, status: str) -> None:
        with self._lock:
            self.status_callback(_app_id(entry), status)


def _app_id(entry: dict):
    """Unique per card (assigned by the bridge) — names/ids can collide."""
    return entry["uid"]


def _other_install_paths(current_entry: dict, all_detected_apps: list[dict]) -> set[str]:
    current_name = current_entry["detected"].get("name")
    return {
        app.get("install_location")
        for app in all_detected_apps
        if app.get("name") != current_name and app.get("install_location")
    }
