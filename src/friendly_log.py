"""
Translates raw log lines (PowerShell output, subprocess errors, our own
internal action logs) into friendly, emoji-flavored messages for the
non-technical terminal view.

Every raw line still gets stored untouched — the friendly version is
just what's DISPLAYED by default. Nothing is lost, just re-presented.
"""

import re
from typing import Optional

# Ordered list of (pattern, friendly_message_or_function). Checked top to
# bottom, first match wins — so more specific patterns should come first.
_TRANSLATIONS = [
    (re.compile(r"^\$ "), None),  # command echo lines are hidden by default
    (re.compile(r"Removed leftover:", re.IGNORECASE), None),  # already friendly (from cleanup.py)
    (re.compile(r"Removed startup entry:", re.IGNORECASE), None),  # already friendly
    (re.compile(r"Removed leftover registry entry:", re.IGNORECASE), None),  # already friendly
    (re.compile(r"Skipped .* still used by", re.IGNORECASE), None),  # already friendly
    (re.compile(r"Detected MSI uninstaller"), lambda line: "🔧 Found the uninstaller, getting it ready..."),
    (re.compile(r"Detected likely NSIS uninstaller"), lambda line: "🔧 Found the uninstaller, getting it ready..."),
    (re.compile(r"Unrecognized installer type"), lambda line: "🔧 Starting the uninstaller..."),
    (re.compile(r"^Done, exit code 0"), lambda line: "✅ All done!"),
    (re.compile(r"ERROR: exited with code", re.IGNORECASE), lambda line: "⚠️ Hit a snag — retrying..."),
    (re.compile(r"ERROR: uninstaller exited with code", re.IGNORECASE), lambda line: "⚠️ Hit a snag — retrying..."),
    (re.compile(r"ERROR: no uninstall string", re.IGNORECASE), lambda line: "❌ Couldn't find how to remove this one."),
    (re.compile(r"ERROR: could not launch", re.IGNORECASE), lambda line: "❌ Couldn't start the removal process."),
]

_FALLBACK_MESSAGE = "⚙️ Working on it..."


def friendly_line(raw_line: str) -> Optional[str]:
    """
    Returns a friendly version of a raw log line, or None if this line
    should be hidden from the friendly view entirely (still kept in the
    raw log, just not surfaced by default).
    """
    for pattern, translator in _TRANSLATIONS:
        if pattern.search(raw_line):
            if translator is None:
                # None means "already friendly enough, or intentionally hidden"
                return raw_line if _looks_already_friendly(raw_line) else None
            return translator(raw_line)

    # Unrecognized raw output (e.g. arbitrary PowerShell/installer chatter)
    # — don't show the raw text to non-technical users, show a generic
    # "still working" message instead so the terminal doesn't feel dead.
    return _FALLBACK_MESSAGE


def _looks_already_friendly(line: str) -> bool:
    """Lines from cleanup.py already use emoji + plain English — pass through."""
    return any(marker in line for marker in ("🧹", "⚠️", "✅", "❌"))

