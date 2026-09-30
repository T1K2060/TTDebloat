"""
Bridge between the HTML UI (src/ui/index.html) and the Python backend.

Public methods on Api are callable from JS as `pywebview.api.<name>()`.
Everything else is underscore-prefixed on purpose: pywebview exposes public
attributes, and we don't want it walking the window object or our state.

Python -> JS events go through window.__emit(event, payload).
"""

import json
import threading

from src.detect import scan_installed_apps
from src.match import load_known_apps, match_apps
from src.queue_manager import STATUS_DONE_SUCCESS, UninstallQueue


class Api:
    def __init__(self):
        self._window = None
        self._emit_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._entries: dict[int, dict] = {}
        self._detected: list[dict] = []
        self._logs: dict[int, dict] = {}
        self._pending: dict[int, dict] = {}
        self._busy = False
        self._scanning = False

    def _attach(self, window) -> None:
        self._window = window

    # ---- callable from JS -------------------------------------------------

    def scan(self) -> bool:
        if self._scanning or self._busy:
            return False
        self._scanning = True
        threading.Thread(target=self._scan_worker, daemon=True).start()
        return True

    def uninstall(self, uids: list) -> bool:
        if self._busy:
            return False
        entries = [self._entries[u] for u in uids if u in self._entries]
        if not entries:
            return False
        self._busy = True
        for entry in entries:
            self._logs[entry["uid"]] = {"raw": [], "friendly": []}
        threading.Thread(target=self._run_batch, args=(entries,), daemon=True).start()
        return True

    def resolve_in_use(self, uid: int, bypass: bool) -> None:
        pending = self._pending.get(uid)
        if pending:
            pending["bypass"] = bool(bypass)
            pending["event"].set()

    def get_logs(self, uid: int) -> dict:
        return self._logs.get(uid, {"raw": [], "friendly": []})

    # ---- internals --------------------------------------------------------

    def _emit(self, event: str, payload: dict) -> None:
        if self._window is None:
            return
        js = f"window.__emit({json.dumps(event)}, {json.dumps(payload)})"
        with self._emit_lock:
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass  # window closing, etc.

    def _scan_worker(self) -> None:
        try:
            detected = scan_installed_apps()
            results = match_apps(detected, load_known_apps())

            other = [
                {**item, "friendly_name": item["detected"].get("name") or "Unknown", "category": "Other"}
                for item in results["other"]
            ]
            other.sort(key=lambda e: e["friendly_name"].lower())
            entries = list(results["recognized"]) + other

            payload, lookup = [], {}
            for uid, entry in enumerate(entries):
                entry["uid"] = uid
                lookup[uid] = entry
                payload.append({
                    "uid": uid,
                    "name": entry.get("friendly_name") or entry["detected"].get("name", "Unknown"),
                    "category": entry.get("category", "Other"),
                    "curated": "id" in entry,
                    "description": entry.get("description", ""),
                })

            with self._state_lock:
                self._detected = detected
                self._entries = lookup
            self._emit("apps", {"apps": payload, "recognized": len(results["recognized"]),
                                "other": len(results["other"])})
        except Exception as error:
            self._emit("scan_error", {"message": str(error)})
        finally:
            self._scanning = False

    def _run_batch(self, entries: list[dict]) -> None:
        queue = UninstallQueue(self._on_status, self._on_log, self._ask_in_use)
        try:
            with self._state_lock:
                snapshot = list(self._detected)
            queue.run_batch(entries, snapshot)
        except Exception as error:
            self._emit("error", {"message": str(error)})
        finally:
            self._busy = False  # always released, so the next batch can start
            self._emit("batch_done", {})

    def _on_status(self, uid: int, status: str) -> None:
        if status == STATUS_DONE_SUCCESS:
            with self._state_lock:
                entry = self._entries.pop(uid, None)
                if entry:
                    self._detected = [a for a in self._detected if a is not entry["detected"]]
        self._emit("status", {"uid": uid, "status": status})

    def _on_log(self, uid: int, raw: str, friendly) -> None:
        log = self._logs.setdefault(uid, {"raw": [], "friendly": []})
        log["raw"].append(raw)
        if friendly is not None:
            log["friendly"].append(friendly)
        self._emit("log", {"uid": uid, "raw": raw, "friendly": friendly})

    def _ask_in_use(self, uid: int, processes: list[dict]) -> bool:
        """Called from a worker thread; blocks until the user clicks Bypass or Skip."""
        event = threading.Event()
        self._pending[uid] = {"event": event, "bypass": False}
        self._emit("in_use", {"uid": uid, "processes": [p["name"] for p in processes]})
        event.wait()
        return self._pending.pop(uid)["bypass"]
