"""
Processes a batch of apps to uninstall + deep-clean.

Strategy (per the plan): run up to MAX_CONCURRENT apps at once, but only
one Win32 app at a time (they often share the same installer service and
collide when run in parallel). If an app fails during the parallel pass,
it goes into a retry queue and gets one more attempt, alone, once the
current batch finishes — this catches failures that were really about
resource contention, not the app itself.

Runs on background threads and reports progress via callbacks so the GUI
can update card statuses and stream log lines without blocking.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from src.cleanup import deep_clean, snapshot_paths_for_app
from src.friendly_log import friendly_line
from src.uninstall import uninstall_app

MAX_CONCURRENT = 3

# Status values a callback might receive for an app.
STATUS_QUEUE = "queue"
STATUS_ACTIVE = "active"
STATUS_RETRYING = "retrying"
STATUS_DONE_SUCCESS = "done_success"
STATUS_DONE_FAILED = "done_failed"


class UninstallQueue:
    """
    status_callback(app_id, status) — called whenever an app's status changes.
    log_callback(app_id, raw_line, friendly_line_or_none) — called for every
        log line produced during that app's processing.
    """

    def __init__(self, status_callback: Callable, log_callback: Callable):
        self.status_callback = status_callback
        self.log_callback = log_callback
        self._lock = threading.Lock()

    def run_batch(self, app_entries: list[dict], all_detected_apps: list[dict]) -> None:
        """
        app_entries: list of matched entries (from match.py) the user selected.
        all_detected_apps: the full scan result, used to build the
            "still installed elsewhere" safety check for cleanup.
        """
        for entry in app_entries:
            self._set_status(entry, STATUS_QUEUE)

        win32_apps = [e for e in app_entries if e["detected"].get("source") == "win32"]
        other_apps = [e for e in app_entries if e["detected"].get("source") != "win32"]

        failed_first_pass = []

        # Non-Win32 apps can run with real concurrency.
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
            results = list(pool.map(
                lambda entry: self._process_one(entry, all_detected_apps),
                other_apps,
            ))
        failed_first_pass.extend(
            entry for entry, succeeded in zip(other_apps, results) if not succeeded
        )

        # Win32 apps run one at a time regardless, to avoid installer-service collisions.
        for entry in win32_apps:
            succeeded = self._process_one(entry, all_detected_apps)
            if not succeeded:
                failed_first_pass.append(entry)

        # Retry pass: alone, sequential, for anything that failed above.
        for entry in failed_first_pass:
            self._set_status(entry, STATUS_RETRYING)
            self._process_one(entry, all_detected_apps, is_retry=True)

    def _process_one(self, entry: dict, all_detected_apps: list[dict], is_retry: bool = False) -> bool:
        app_id = _app_id(entry)
        self._set_status(entry, STATUS_ACTIVE)

        def log(raw_line: str) -> None:
            translated = friendly_line(raw_line)
            self.log_callback(app_id, raw_line, translated)

        if is_retry:
            log("--- Retrying on its own ---")

        # Snapshot BEFORE uninstall, only needed for non-curated ("other") apps.
        snapshot = []
        if not entry.get("cleanup_paths"):
            snapshot = snapshot_paths_for_app(entry["detected"])

        succeeded = uninstall_app(entry, log=log)

        if succeeded:
            other_install_paths = _other_install_paths(entry, all_detected_apps)
            summary = deep_clean(entry, snapshot, other_install_paths, log=log)
            log(f"Cleanup summary: {len(summary['removed_paths'])} paths removed, "
                f"{len(summary['removed_registry_keys'])} registry entries removed")
            self._set_status(entry, STATUS_DONE_SUCCESS)
        else:
            self._set_status(entry, STATUS_DONE_FAILED)

        return succeeded

    def _set_status(self, entry: dict, status: str) -> None:
        with self._lock:
            self.status_callback(_app_id(entry), status)


def _app_id(entry: dict) -> str:
    """Stable-ish identifier for UI updates — falls back to the detected name."""
    return entry.get("id") or entry["detected"].get("name", "unknown")


def _other_install_paths(current_entry: dict, all_detected_apps: list[dict]) -> set[str]:
    """
    Install locations of every OTHER app (not the one currently being
    cleaned), used by deep_clean to avoid deleting a shared folder.
    """
    current_name = current_entry["detected"].get("name")
    return {
        app.get("install_location")
        for app in all_detected_apps
        if app.get("name") != current_name and app.get("install_location")
    }
