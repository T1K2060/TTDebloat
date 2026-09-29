"""
Main application window. Wires together detection, matching, the app
card grid, the terminal log panels, and the uninstall queue.
"""

import threading

import customtkinter as ctk

from src.detect import scan_installed_apps
from src.gui.widgets.app_card import AppCard
from src.gui.widgets.terminal_panel import TerminalPanel
from src.match import load_known_apps, match_apps
from src.queue_manager import UninstallQueue

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class DebloatApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Debloat")
        self.geometry("900x650")
        self.configure(fg_color="#1a1a1a")

        self.cards: dict[str, AppCard] = {}
        self.entries_by_name: dict[str, dict] = {}
        self.selected_names: set[str] = set()
        self.log_panels: dict[str, TerminalPanel] = {}
        self.all_detected_apps: list[dict] = []

        self._build_layout()
        self._start_scan()

    def _build_layout(self) -> None:
        top_bar = ctk.CTkFrame(self, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(16, 8))

        self.status_label = ctk.CTkLabel(top_bar, text="Scanning your PC...", font=ctk.CTkFont(size=14))
        self.status_label.pack(side="left")

        self.uninstall_all_button = ctk.CTkButton(
            top_bar, text="Uninstall All Selected", fg_color="white", text_color="black",
            hover_color="#dddddd", command=self._on_uninstall_all,
        )
        self.uninstall_all_button.pack(side="right")
        self.uninstall_all_button.configure(state="disabled")

        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="#141414", corner_radius=12)
        self.scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Simple responsive-ish grid: fixed column count, cards flow left to right.
        self.columns = 4
        for col in range(self.columns):
            self.scroll_frame.grid_columnconfigure(col, weight=1)

    def _start_scan(self) -> None:
        # Scanning touches the registry/PowerShell — keep it off the UI thread
        # so the window doesn't freeze while it runs.
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self) -> None:
        detected = scan_installed_apps()
        known = load_known_apps()
        results = match_apps(detected, known)

        self.all_detected_apps = detected
        self.after(0, lambda: self._populate_grid(results))

    def _populate_grid(self, results: dict) -> None:
        self.status_label.configure(
            text=f"Found {len(results['recognized'])} recognized apps, "
                 f"{len(results['other'])} others"
        )
        self.uninstall_all_button.configure(state="normal")

        all_entries = results["recognized"] + [
            {**item, "friendly_name": item["detected"].get("name", "Unknown"), "category": "Other"}
            for item in results["other"]
        ]

        for index, entry in enumerate(all_entries):
            name = entry.get("friendly_name", entry["detected"].get("name", "Unknown"))
            category = entry.get("category", "Other")
            is_curated = bool(entry.get("cleanup_paths")) or "id" in entry

            card = AppCard(
                self.scroll_frame, app_name=name, category=category, is_curated=is_curated,
                on_select_toggle=self._on_card_select_toggle,
                on_show_logs=self._on_show_logs,
            )
            row, col = divmod(index, self.columns)
            card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

            self.cards[name] = card
            self.entries_by_name[name] = entry

    def _on_card_select_toggle(self, name: str, selected: bool) -> None:
        if selected:
            self.selected_names.add(name)
        else:
            self.selected_names.discard(name)

    def _on_show_logs(self, name: str) -> None:
        if name not in self.log_panels or not self.log_panels[name].winfo_exists():
            self.log_panels[name] = TerminalPanel(self, name)
        self.log_panels[name].focus()

    def _on_uninstall_all(self) -> None:
        if not self.selected_names:
            return

        self.uninstall_all_button.configure(state="disabled")
        selected_entries = [self.entries_by_name[name] for name in self.selected_names]

        queue = UninstallQueue(
            status_callback=self._on_status_update,
            log_callback=self._on_log_line,
        )

        threading.Thread(
            target=queue.run_batch,
            args=(selected_entries, self.all_detected_apps),
            daemon=True,
        ).start()

    def _on_status_update(self, app_id: str, status: str) -> None:
        # app_id from queue_manager is the entry's "id" (curated) or detected
        # name (other) — for curated apps that differs from the card's
        # friendly_name key, so we resolve it back here.
        name = self._resolve_card_name(app_id)
        if name and name in self.cards:
            self.after(0, lambda: self.cards[name].set_status(status))

    def _on_log_line(self, app_id: str, raw_line: str, friendly: str | None) -> None:
        name = self._resolve_card_name(app_id)
        if name and name in self.log_panels and self.log_panels[name].winfo_exists():
            self.after(0, lambda: self.log_panels[name].add_line(raw_line, friendly))

    def _resolve_card_name(self, app_id: str) -> str | None:
        for name, entry in self.entries_by_name.items():
            entry_id = entry.get("id") or entry["detected"].get("name")
            if entry_id == app_id:
                return name
        return None


if __name__ == "__main__":
    app = DebloatApp()
    app.mainloop()
