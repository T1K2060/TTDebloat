"""
Uninstalls classic Win32 programs using the UninstallString recorded in
the registry — the same command Windows' own "Add or Remove Programs"
would run.

There's no universal silent flag (every installer framework does it
differently), so this makes a best-effort attempt to add a common silent
flag for recognized installer types (MSI, InstallShield, NSIS) and falls
back to running the uninstaller as-is otherwise, which may pop the
vendor's own uninstall wizard.
"""

import shlex
import subprocess
from typing import Callable, Optional

LogCallback = Optional[Callable[[str], None]]


def uninstall_win32_program(uninstall_string: str, log: LogCallback = None) -> bool:
    if not uninstall_string:
        if log:
            log("ERROR: no uninstall string available for this program")
        return False

    command_parts = _build_silent_command(uninstall_string, log)

    if log:
        log(f"$ {' '.join(command_parts)}")

    try:
        process = subprocess.Popen(
            command_parts,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=False,
        )
    except (FileNotFoundError, OSError) as error:
        if log:
            log(f"ERROR: could not launch uninstaller: {error}")
        return False

    for line in process.stdout:
        stripped = line.rstrip()
        if stripped and log:
            log(stripped)

    process.wait(timeout=300)

    if process.returncode != 0:
        if log:
            log(f"ERROR: uninstaller exited with code {process.returncode}")
        return False

    if log:
        log("Done, exit code 0")
    return True


def _build_silent_command(uninstall_string: str, log: LogCallback) -> list[str]:
    """
    Tries to add a silent flag based on recognizable installer patterns.
    Falls back to the raw uninstall string (which may show a UI) if we
    don't recognize the installer type — better to succeed loudly than
    fail silently.
    """
    lowered = uninstall_string.lower()

    # MSI-based uninstalls: "MsiExec.exe /X{GUID}" — add /qn for fully silent.
    if "msiexec" in lowered:
        parts = shlex.split(uninstall_string, posix=False)
        if "/qn" not in [p.lower() for p in parts]:
            parts.append("/qn")
        if log:
            log("Detected MSI uninstaller, adding silent flag")
        return parts

    # NSIS-based uninstallers commonly support /S for silent mode.
    if "uninst" in lowered and lowered.endswith(".exe"):
        parts = shlex.split(uninstall_string, posix=False)
        if log:
            log("Detected likely NSIS uninstaller, attempting /S silent flag")
        return parts + ["/S"]

    # Unknown installer type — run as-is, may show the vendor's UI.
    if log:
        log("Unrecognized installer type, running as-is (may show a window)")
    return shlex.split(uninstall_string, posix=False)
