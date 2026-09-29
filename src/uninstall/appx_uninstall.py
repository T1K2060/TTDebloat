"""
Removes UWP/Store apps (Appx packages) and provisioned packages.

Both go through PowerShell since that's where these cmdlets live —
there's no equivalent in the Win32 API that Python can call directly.
"""

import subprocess
from typing import Callable, Optional

LogCallback = Optional[Callable[[str], None]]


def remove_appx_package(package_full_name: str, log: LogCallback = None) -> bool:
    """
    Removes an installed Appx package for all users.
    Returns True on success, False on failure. Emits raw lines to `log`
    as they happen so the caller can stream them into the UI terminal.
    """
    command = f"Remove-AppxPackage -Package '{package_full_name}' -AllUsers"
    return _run_powershell_streaming(command, log)


def remove_provisioned_package(package_name: str, log: LogCallback = None) -> bool:
    """
    De-provisions a package so it stops being installed for new user
    accounts. Doesn't affect the current user's already-installed copy —
    pair with remove_appx_package for a full removal.
    """
    command = f"Remove-AppxProvisionedPackage -Online -PackageName '{package_name}'"
    return _run_powershell_streaming(command, log)


def _run_powershell_streaming(command: str, log: LogCallback) -> bool:
    """
    Runs a PowerShell command and streams stdout line-by-line to `log`
    as it arrives, rather than waiting for the whole process to finish.
    This is what makes the live terminal panel feel live.
    """
    if log:
        log(f"$ {command}")

    try:
        process = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as error:
        if log:
            log(f"ERROR: could not launch PowerShell: {error}")
        return False

    for line in process.stdout:
        stripped = line.rstrip()
        if stripped and log:
            log(stripped)

    process.wait(timeout=120)

    if process.returncode != 0:
        if log:
            log(f"ERROR: exited with code {process.returncode}")
        return False

    if log:
        log("Done, exit code 0")
    return True
