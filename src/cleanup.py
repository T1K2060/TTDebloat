"""
Runs after an app's uninstaller finishes — removes leftover files and
registry residue it left behind.

Two strategies depending on whether the app was curated or not:
  - Curated apps: use the hand-verified cleanup_paths from known_apps.json.
  - Other apps: snapshot the install/vendor paths BEFORE uninstalling,
    then check after uninstall whether they still exist and aren't
    referenced by any other still-installed app, before removing them.

No quarantine — matches deletes are immediate and permanent, but every
action is logged to disk regardless (not for recovery, just a record).
"""

import os
import shutil
import winreg
from pathlib import Path
from typing import Callable, Optional

LogCallback = Optional[Callable[[str], None]]


def snapshot_paths_for_app(detected_app: dict) -> list[str]:
    """
    Called BEFORE uninstalling an "Other" (non-curated) app. Derives
    likely leftover locations from whatever the registry entry told us,
    so we have something to check against after the uninstall runs.
    """
    candidates = []

    install_location = detected_app.get("install_location")
    if install_location:
        candidates.append(install_location)

    publisher = detected_app.get("publisher")
    if publisher:
        # Strip common legal suffixes so "Acme Corp, Inc." becomes a
        # folder-name-like "Acme Corp" for matching against AppData.
        vendor_guess = publisher.split(",")[0].strip()
        for base in ("%APPDATA%", "%LOCALAPPDATA%", "%PROGRAMDATA%"):
            candidates.append(os.path.join(base, vendor_guess))

    return [os.path.expandvars(path) for path in candidates if path]


def deep_clean(app_entry: dict, snapshot: list[str], other_active_install_paths: set[str],
                log: LogCallback = None) -> dict:
    """
    Removes leftover files/folders and registry residue for one app.

    - app_entry: the matched entry from match.py (curated or "other")
    - snapshot: paths captured by snapshot_paths_for_app before uninstall
                (only used for "other" apps; curated apps use their own
                cleanup_paths instead)
    - other_active_install_paths: install_location values from every OTHER
                still-installed app, used as a safety check so we don't
                delete a folder another program still depends on

    Returns a summary dict for the report screen:
      {"removed_paths": [...], "skipped_paths": [...], "removed_registry_keys": [...]}
    """
    removed_paths = []
    skipped_paths = []

    if app_entry.get("cleanup_paths"):
        # Curated: trust the hand-verified list directly.
        candidate_paths = [os.path.expandvars(p) for p in app_entry["cleanup_paths"]]
    else:
        # Other: use what we snapshotted before uninstalling.
        candidate_paths = snapshot

    for path in candidate_paths:
        if not os.path.exists(path):
            continue

        if path in other_active_install_paths:
            skipped_paths.append(path)
            if log:
                log(f"⚠️  Skipped {path} — still used by another installed app")
            continue

        _remove_path(path)
        removed_paths.append(path)
        if log:
            log(f"🧹 Removed leftover: {path}")

    removed_keys = _clean_registry_residue(app_entry, log)

    return {
        "removed_paths": removed_paths,
        "skipped_paths": skipped_paths,
        "removed_registry_keys": removed_keys,
    }


def _remove_path(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    elif os.path.isfile(path):
        os.remove(path)


def _clean_registry_residue(app_entry: dict, log: LogCallback) -> list[str]:
    """
    Removes orphaned Run/RunOnce startup entries left behind by the app.
    This is lower-risk than file deletion (no user data involved), so it
    runs regardless of curated vs other.
    """
    removed_keys = []
    detected = app_entry["detected"]
    app_name = detected.get("name", "")

    if not app_name:
        return removed_keys

    run_key_paths = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    ]

    for hive, key_path in run_key_paths:
        removed_keys.extend(_remove_matching_run_entries(hive, key_path, app_name, log))

    # Also clean up the app's own now-orphaned Uninstall registry key, if
    # its uninstaller didn't remove its own registration.
    registry_key_path = detected.get("registry_key_path")
    if registry_key_path:
        hive = winreg.HKEY_CURRENT_USER if detected.get("registry_hive") == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        if _key_still_exists(hive, registry_key_path):
            try:
                winreg.DeleteKey(hive, registry_key_path)
                removed_keys.append(registry_key_path)
                if log:
                    log(f"🧹 Removed leftover registry entry: {registry_key_path}")
            except OSError as error:
                if log:
                    log(f"⚠️  Could not remove {registry_key_path}: {error}")

    return removed_keys


def _remove_matching_run_entries(hive, key_path: str, app_name: str, log: LogCallback) -> list[str]:
    removed = []
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return removed

    value_count = winreg.QueryInfoKey(key)[1]
    value_names_to_delete = []

    for index in range(value_count):
        name, value, _ = winreg.EnumValue(key, index)
        if app_name.lower() in name.lower() or app_name.lower() in str(value).lower():
            value_names_to_delete.append(name)

    for name in value_names_to_delete:
        try:
            winreg.DeleteValue(key, name)
            removed.append(f"{key_path}\\{name}")
            if log:
                log(f"🧹 Removed startup entry: {name}")
        except OSError as error:
            if log:
                log(f"⚠️  Could not remove startup entry {name}: {error}")

    winreg.CloseKey(key)
    return removed


def _key_still_exists(hive, key_path: str) -> bool:
    try:
        winreg.OpenKey(hive, key_path)
        return True
    except FileNotFoundError:
        return False
