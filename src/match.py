"""
Takes the raw output of src/detect (everything actually found on the
machine) and matches it against data/known_apps.json (the curated,
hand-verified database).

Splits the result into two buckets:
  - "recognized": matched a curated entry, gets friendly name/category/
    description/cleanup_paths from the database
  - "other": detected but not in the database — still shown to the user
    (per the "Other/Unrecognized" section design), just without curated
    metadata, and removal falls back to the registry UninstallString
    rather than a hand-verified method.
"""

import json
from pathlib import Path

DEFAULT_DATABASE_PATH = Path(__file__).parent.parent / "data" / "known_apps.json"


def load_known_apps(database_path: Path = DEFAULT_DATABASE_PATH) -> list[dict]:
    with open(database_path, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data["apps"]


def match_apps(detected_apps: list[dict], known_apps: list[dict]) -> dict:
    """
    Returns {"recognized": [...], "other": [...]}.

    Each "recognized" item is the curated database entry, with the raw
    detected data attached under "detected" so removal logic still has
    access to things like uninstall_string or package_full_name.

    Each "other" item is just the raw detected data, tagged so the UI
    knows it has no curated metadata to show.
    """
    recognized = []
    matched_detected_ids = set()

    for known_app in known_apps:
        for detected_app in detected_apps:
            if _is_match(detected_app, known_app["match"]):
                recognized.append({
                    **known_app,
                    "detected": detected_app,
                })
                # Track by identity (object id) so the same physical
                # detected app isn't later re-listed under "other".
                matched_detected_ids.add(id(detected_app))

    other = [
        {"detected": app, "curated": False}
        for app in detected_apps
        if id(app) not in matched_detected_ids
    ]

    return {"recognized": recognized, "other": other}


def _is_match(detected_app: dict, match_rule: dict) -> bool:
    """
    Checks a single detected app against a single known_apps.json match
    rule. Rules are source-specific:

      - appx/provisioned: match by package family name prefix, since the
        full package name includes a version number that changes on
        every update (so exact-matching would break constantly).
      - win32: match by substring in the DisplayName, since there's no
        stable identifier — known_apps.json can list multiple variants
        per app to catch naming differences across versions.
    """
    if detected_app.get("source") != match_rule.get("source"):
        return False

    if match_rule["source"] in ("appx", "provisioned"):
        name = detected_app.get("name", "")
        prefixes = match_rule.get("package_family_prefixes", [])
        return any(name.startswith(prefix) for prefix in prefixes)

    if match_rule["source"] == "win32":
        name = detected_app.get("name", "")
        needles = match_rule.get("name_contains", [])
        return any(needle.lower() in name.lower() for needle in needles)

    return False


if __name__ == "__main__":
    # Manual smoke test using fake data, so this can be sanity-checked
    # without needing to run on a real Windows machine.
    fake_detected = [
        {"name": "Microsoft.BingWeather", "source": "appx"},
        {"name": "Some Random Utility", "source": "win32"},
    ]
    known = load_known_apps()
    results = match_apps(fake_detected, known)
    print(f"Recognized: {len(results['recognized'])}")
    print(f"Other: {len(results['other'])}")
