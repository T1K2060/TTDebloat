"""
Detects "provisioned" Appx packages — apps that Windows will automatically
install for ANY new user account created on this machine, even if the
current user never opened them.

This is what tools like Win11Debloat's "Sysprep mode" target: removing a
provisioned package stops it from being pushed to future user accounts,
separately from removing it for the current user.

Always requires admin rights.
"""

import json
import subprocess


def get_provisioned_packages() -> list[dict]:
    """
    Returns a list of provisioned Appx packages.

    Each item looks like:
    {
        "name": "Microsoft.BingWeather",
        "package_name": "Microsoft.BingWeather_4.53.31921.0_neutral_~_8wekyb3d8bbwe",
        "source": "provisioned"
    }
    """
    command = (
        "Get-AppxProvisionedPackage -Online | "
        "Select-Object DisplayName, PackageName | "
        "ConvertTo-Json -Depth 3 -Compress"
    )

    result = _run_powershell(command)
    if result is None:
        return []

    if isinstance(result, dict):
        result = [result]

    packages = []
    for item in result:
        packages.append({
            "name": item.get("DisplayName", ""),
            "package_name": item.get("PackageName", ""),
            "source": "provisioned",
        })

    return packages


def _run_powershell(command: str):
    """Same pattern as detect/appx.py — returns None on failure, [] on empty."""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as error:
        print(f"[detect.provisioned] PowerShell call failed: {error}")
        return None

    if completed.returncode != 0:
        print(f"[detect.provisioned] PowerShell exited {completed.returncode}: {completed.stderr.strip()}")
        return None

    raw_output = completed.stdout.strip()
    if not raw_output:
        return []

    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as error:
        print(f"[detect.provisioned] Failed to parse PowerShell JSON output: {error}")
        return None


if __name__ == "__main__":
    found = get_provisioned_packages()
    print(f"Found {len(found)} provisioned packages")
    for pkg in found[:5]:
        print(f"  - {pkg['name']}")
