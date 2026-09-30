"""
Detects whether an app is currently running (so its uninstall would fail or
leave files locked) and can close its processes when the user chooses to bypass.

Safety: only processes whose executable lives INSIDE the app's own folder are
ever matched, and protected system folders are never used as a match root.
"""

import os
import re
from typing import Optional

import psutil


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _protected_roots() -> set[str]:
    env = os.environ
    candidates = [
        env.get("SystemRoot"), env.get("ProgramFiles"), env.get("ProgramFiles(x86)"),
        env.get("ProgramData"), env.get("LOCALAPPDATA"), env.get("APPDATA"),
        os.path.expanduser("~"), os.path.dirname(os.path.expanduser("~")),
    ]
    if env.get("ProgramFiles"):
        candidates.append(os.path.join(env["ProgramFiles"], "WindowsApps"))
    return {_norm(p) for p in candidates if p}


def _is_safe_root(root: str) -> bool:
    root = _norm(root)
    drive, tail = os.path.splitdrive(root)
    if not tail.strip("\\/"):  # drive root like C:\
        return False
    if root in _protected_roots():
        return False
    windir = os.environ.get("SystemRoot")
    if windir and (root == _norm(windir) or root.startswith(_norm(windir) + os.sep)):
        return False
    return True


def _dir_from_command(value: Optional[str]) -> Optional[str]:
    """Pull a folder out of DisplayIcon / UninstallString values."""
    if not value:
        return None
    match = re.search(r'[A-Za-z]:\\[^"<>|?*]*?\.(?:exe|dll|ico)', value, re.IGNORECASE)
    return os.path.dirname(match.group(0)) if match else None


def _roots_for(entry: dict) -> list[str]:
    detected = entry["detected"]
    candidates = [detected.get("install_location")]
    if detected.get("source") == "win32":
        candidates.append(_dir_from_command(detected.get("display_icon")))
        candidates.append(_dir_from_command(detected.get("uninstall_string")))
    return list({_norm(c) for c in candidates if c and _is_safe_root(c)})


def find_running_processes(entry: dict) -> list[dict]:
    """Returns [{"pid": int, "name": str}] for processes running from the app's folder."""
    roots = _roots_for(entry)
    if not roots:
        return []

    me = psutil.Process()
    skip = {me.pid} | {p.pid for p in me.parents()}

    found = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        exe = proc.info.get("exe")
        if not exe or proc.info["pid"] in skip:
            continue
        exe = _norm(exe)
        if any(exe.startswith(root + os.sep) for root in roots):
            found.append({"pid": proc.info["pid"], "name": proc.info.get("name") or "unknown"})
    return found


def kill_processes(pids: list[int]) -> int:
    """Politely terminate, then force-kill stragglers. Returns how many were targeted."""
    me = os.getpid()
    targets = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            targets.append(proc)
            targets.extend(c for c in proc.children(recursive=True) if c.pid != me)
        except psutil.NoSuchProcess:
            continue

    for proc in targets:
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(targets, timeout=3)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return len(targets)
