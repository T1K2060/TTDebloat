"""
Detects installed UWP / Microsoft Store apps using PowerShell's Get-AppxPackage.

These are the "modern" Windows apps (Bing Weather, Xbox, Cortana, etc.) that
show up as packages rather than classic Program-Files-style installs.
"""

import json
import subprocess


def get_appx_packages(all_users: bool = True) -> list[dict]:
    """
    Returns a list of installed Appx (UWP/Store) packages.

    Each item looks like:
    {
        "name": "Microsoft.BingWeather",
        "package_full_name": "Microsoft.BingWeather_4.53.31921.0_x64__8wekyb3d8bbwe",
        "publisher": "CN=Microsoft Corporation, ...",
        "install_location": "C:\\Program Files\\WindowsApps\\...",
        "source": "appx"
    }

    Requires admin rights when all_users=True (needed to see packages
    installed for every user account, not just the current one).
    """
    scope_flag = "-AllUsers" if all_users else ""

    # ConvertTo-Json -Depth 3 keeps nested publisher/version info intact.
    # -Compress keeps the payload small; we don't need pretty-printed JSON.
    command = (
        f"Get-AppxPackage {scope_flag} | "
        "Select-Object Name, PackageFullName, Publisher, InstallLocation | "
        "ConvertTo-Json -Depth 3 -Compress"
    )

    result = _run_powershell(command)
    if result is None:
        return []

    # PowerShell returns a single object (not a list) when there's only
    # one match, so we normalize that case here.
    if isinstance(result, dict):
        result = [result]

    packages = []
    for item in result:
        packages.append({
            "name": item.get("Name", ""),
            "package_full_name": item.get("PackageFullName", ""),
            "publisher": item.get("Publisher", ""),
            "install_location": item.get("InstallLocation", ""),
            "source": "appx",
        })

    return packages


def _run_powershell(command: str):
    """
    Runs a PowerShell command and parses its JSON output.
    Returns None on failure (rather than raising) so callers can decide
    how to handle a missing/broken source without crashing the whole scan.
    """
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as error:
        print(f"[detect.appx] PowerShell call failed: {error}")
        return None

    if completed.returncode != 0:
        print(f"[detect.appx] PowerShell exited {completed.returncode}: {completed.stderr.strip()}")
        return None

    raw_output = completed.stdout.strip()
    if not raw_output:
        # No packages matched — not an error, just an empty result.
        return []

    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as error:
        print(f"[detect.appx] Failed to parse PowerShell JSON output: {error}")
        return None


if __name__ == "__main__":
    # Quick manual test: run this file directly on a Windows machine to see
    # what it detects, without needing the rest of the app wired up yet.
    found = get_appx_packages()
    print(f"Found {len(found)} Appx packages")
    for pkg in found[:5]:
        print(f"  - {pkg['name']}")
