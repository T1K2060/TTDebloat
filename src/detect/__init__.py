"""
Combines all three detection sources (Appx, provisioned, Win32 registry)
into one unified list of "detected apps" that the rest of the app works
with — so nothing downstream needs to know or care which source an app
came from.
"""

from src.detect.appx import get_appx_packages
from src.detect.provisioned import get_provisioned_packages
from src.detect.registry_apps import get_installed_win32_apps


def scan_installed_apps() -> list[dict]:
    """
    Runs all three detectors and returns one combined list.

    Every item has at least: name, source ("appx" / "provisioned" / "win32"),
    plus whatever source-specific fields that detector provides (see the
    individual detect/*.py files for exact shapes).

    Each detector is wrapped so that if one source fails entirely (e.g.
    PowerShell missing, registry access denied), the other two still
    return results instead of the whole scan dying.
    """
    detected_apps = []

    detected_apps.extend(_safe_scan("Appx packages", get_appx_packages))
    detected_apps.extend(_safe_scan("Provisioned packages", get_provisioned_packages))
    detected_apps.extend(_safe_scan("Win32 programs", get_installed_win32_apps))

    return detected_apps


def _safe_scan(label: str, scan_function) -> list[dict]:
    try:
        results = scan_function()
        print(f"[scan] {label}: found {len(results)}")
        return results
    except Exception as error:
        # A detection source failing shouldn't take down the whole app —
        # log it and move on with whatever the other sources found.
        print(f"[scan] {label} failed entirely: {error}")
        return []


if __name__ == "__main__":
    all_apps = scan_installed_apps()
    print(f"\nTotal detected: {len(all_apps)}")
