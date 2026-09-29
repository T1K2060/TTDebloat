"""
Single entry point for removing an app, regardless of which detection
source it came from. Looks at the app's removal_method (curated apps) or
falls back to source-based logic (Other/Unrecognized apps), then calls
the right function from appx_uninstall.py or win32_uninstall.py.
"""

from typing import Callable, Optional

from src.uninstall.appx_uninstall import remove_appx_package, remove_provisioned_package
from src.uninstall.win32_uninstall import uninstall_win32_program

LogCallback = Optional[Callable[[str], None]]


def uninstall_app(app_entry: dict, log: LogCallback = None) -> bool:
    """
    app_entry is either:
      - a "recognized" entry from match.py (has "removal_method" + "detected")
      - an "other" entry from match.py (has "detected" only, curated=False)

    Returns True if the uninstall succeeded, False otherwise.
    """
    detected = app_entry["detected"]
    removal_method = app_entry.get("removal_method")

    # Curated apps declare their removal method explicitly.
    if removal_method == "appx":
        package_full_name = detected.get("package_full_name")
        return remove_appx_package(package_full_name, log)

    if removal_method == "provisioned":
        package_name = detected.get("package_name")
        return remove_provisioned_package(package_name, log)

    if removal_method == "win32_uninstall_string":
        uninstall_string = detected.get("uninstall_string")
        return uninstall_win32_program(uninstall_string, log)

    # "Other" apps have no curated removal_method — fall back based on
    # which detector found them.
    source = detected.get("source")

    if source == "appx":
        return remove_appx_package(detected.get("package_full_name"), log)

    if source == "provisioned":
        return remove_provisioned_package(detected.get("package_name"), log)

    if source == "win32":
        return uninstall_win32_program(detected.get("uninstall_string"), log)

    if log:
        log(f"ERROR: don't know how to uninstall source '{source}'")
    return False
