# Debloat App

A Windows debloat tool with a GUI. Detects installed bloatware (Store apps,
provisioned packages, and classic programs), matches them against a
curated database, and removes them along with leftover files/registry
entries.

## Running it (on Windows, with admin rights)

```
pip install -r requirements.txt
python -m src.main
```

Admin rights are required for full detection (`-AllUsers` package queries)
and for most uninstall/cleanup actions. Run your terminal/IDE as
Administrator during development. The bootstrapper (built separately,
not part of this repo) will handle elevation automatically for end users.

## Project structure

```
src/
  detect/           - finds installed apps (Appx, provisioned, Win32 registry)
  uninstall/         - removes apps via the right method per source
  gui/               - CustomTkinter interface
  cleanup.py         - deep-clean: leftover files + registry residue
  match.py           - matches detected apps against data/known_apps.json
  friendly_log.py    - translates raw log lines into friendly messages
  queue_manager.py   - hybrid parallel uninstall queue with retry
  main.py            - entry point
data/
  known_apps.json    - curated database of known bloatware + cleanup paths
```

## Adding a new curated app

Add an entry to `data/known_apps.json`. See the existing entries for the
shape — you need a `match` rule (how to recognize it from detection
output) and a `removal_method`. `cleanup_paths` is optional but
recommended so leftovers get removed reliably instead of relying on the
heuristic fallback used for uncurated apps.

## Notes

- This code is Windows-only (uses `winreg` and PowerShell) — it won't run
  on macOS/Linux.
- Deletion of leftover files is immediate, not quarantined. Every action
  is logged.
- No quarantine/undo mechanism exists for cleanup deletions by design —
  see the project planning notes if you want to add one later.
