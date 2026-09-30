"""
Detects installed classic Win32 programs by reading the registry's
"Uninstall" keys — the same place Windows' own "Add or Remove Programs"
list pulls from.

Unlike Appx packages, Win32 programs don't have a stable machine-readable
ID — we only get whatever the installer chose to write (DisplayName,
UninstallString, etc). This is why matching these against known_apps.json
later has to be name-based rather than ID-based.
"""

import winreg

# Windows keeps separate Uninstall trees for 64-bit and 32-bit (WOW6432Node)
# programs, and separate hives for machine-wide vs current-user installs.
# We need to check all four combinations to see everything.
UNINSTALL_KEY_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def get_installed_win32_apps() -> list[dict]:
    """
    Returns a list of installed classic (Win32) programs.

    Each item looks like:
    {
        "name": "Some Program",
        "publisher": "Some Vendor",
        "install_location": "C:\\Program Files\\Some Program",
        "uninstall_string": "C:\\Program Files\\Some Program\\uninstall.exe",
        "display_icon": "C:\\Program Files\\Some Program\\app.exe",
        "registry_key_path": "SOFTWARE\\...\\Uninstall\\{GUID}",
        "source": "win32"
    }
    """
    apps = []

    for hive, base_path in UNINSTALL_KEY_PATHS:
        apps.extend(_read_uninstall_entries(hive, base_path))

    return apps


def _read_uninstall_entries(hive, base_path: str) -> list[dict]:
    entries = []

    try:
        base_key = winreg.OpenKey(hive, base_path)
    except FileNotFoundError:
        # This tree doesn't exist on this machine (e.g. no WOW6432Node on
        # a 32-bit OS) — not an error, just nothing to read here.
        return entries

    subkey_count = winreg.QueryInfoKey(base_key)[0]

    for index in range(subkey_count):
        try:
            subkey_name = winreg.EnumKey(base_key, index)
            entry = _read_single_entry(hive, base_path, subkey_name)
            if entry:
                entries.append(entry)
        except OSError as error:
            # A single malformed/inaccessible key shouldn't stop the whole
            # scan — skip it and keep going.
            print(f"[detect.registry_apps] Skipped key #{index} under {base_path}: {error}")
            continue

    winreg.CloseKey(base_key)
    return entries


def _read_single_entry(hive, base_path: str, subkey_name: str) -> dict | None:
    full_path = f"{base_path}\\{subkey_name}"

    with winreg.OpenKey(hive, full_path) as key:
        display_name = _get_value(key, "DisplayName")

        # Entries with no DisplayName are usually system components or
        # patches, not real user-facing programs — skip them.
        if not display_name:
            return None

        # SystemComponent=1 marks entries Windows deliberately hides from
        # "Add or Remove Programs" (shared runtimes, driver bits, etc).
        # We skip these for the same reason Windows does.
        if _get_value(key, "SystemComponent") == 1:
            return None

        return {
            "name": display_name,
            "publisher": _get_value(key, "Publisher") or "",
            "install_location": _get_value(key, "InstallLocation") or "",
            "uninstall_string": _get_value(key, "UninstallString") or "",
            "display_icon": _get_value(key, "DisplayIcon") or "",
            "registry_key_path": full_path,
            "registry_hive": "HKCU" if hive == winreg.HKEY_CURRENT_USER else "HKLM",
            "source": "win32",
        }


def _get_value(key, value_name: str):
    """Reads a single registry value, returning None if it doesn't exist."""
    try:
        value, _ = winreg.QueryValueEx(key, value_name)
        return value
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    found = get_installed_win32_apps()
    print(f"Found {len(found)} Win32 programs")
    for app in found[:10]:
        print(f"  - {app['name']}")
