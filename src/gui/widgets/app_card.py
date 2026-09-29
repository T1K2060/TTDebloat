"""
A single app card: icon placeholder, name, select checkbox / status badge,
and a "Show Logs" button. Matches the dark card style from the mockups.
"""

import customtkinter as ctk

STATUS_COLORS = {
    "queue": "#8a8a8a",
    "active": "#e8b923",
    "retrying": "#e8892f",
    "done_success": "#3fb950",
    "done_failed": "#e5484d",
}

STATUS_LABELS = {
    "queue": "Queue",
    "active": "Active",
    "retrying": "Retrying",
    "done_success": "Done",
    "done_failed": "Failed",
}


class AppCard(ctk.CTkFrame):
    def __init__(self, master, app_name: str, category: str, is_curated: bool,
                 on_select_toggle, on_show_logs, **kwargs):
        super().__init__(master, corner_radius=12, fg_color="#242424", **kwargs)

        self.app_name = app_name
        self.selected = False
        self.status = None
        self._on_select_toggle = on_select_toggle
        self._on_show_logs = on_show_logs

        self.icon_placeholder = ctk.CTkFrame(self, width=64, height=64, fg_color="#f0f0f0", corner_radius=6)
        self.icon_placeholder.pack(pady=(16, 8))
        self.icon_placeholder.pack_propagate(False)

        self.name_label = ctk.CTkLabel(self, text=app_name, font=ctk.CTkFont(size=14, weight="bold"))
        self.name_label.pack(pady=(0, 4))

        if not is_curated:
            self.category_label = ctk.CTkLabel(self, text="Unrecognized", font=ctk.CTkFont(size=11),
                                                 text_color="#b58900")
        else:
            self.category_label = ctk.CTkLabel(self, text=category, font=ctk.CTkFont(size=11),
                                                 text_color="#9a9a9a")
        self.category_label.pack(pady=(0, 8))

        self.select_button = ctk.CTkButton(self, text="Select", command=self._toggle_select,
                                             fg_color="white", text_color="black", hover_color="#dddddd")
        self.select_button.pack(fill="x", padx=16, pady=(0, 6))

        self.logs_button = ctk.CTkButton(self, text="Show Logs", command=self._show_logs,
                                           fg_color="#333333", hover_color="#404040")
        self.logs_button.pack(fill="x", padx=16, pady=(0, 6))
        self.logs_button.configure(state="disabled")

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11, weight="bold"))
        self.status_label.pack(pady=(0, 12))

    def _toggle_select(self) -> None:
        self.selected = not self.selected
        self.select_button.configure(
            text="Selected ✓" if self.selected else "Select",
            fg_color="#3fb950" if self.selected else "white",
            text_color="white" if self.selected else "black",
        )
        self._on_select_toggle(self.app_name, self.selected)

    def _show_logs(self) -> None:
        self._on_show_logs(self.app_name)

    def set_status(self, status: str) -> None:
        self.status = status
        self.status_label.configure(text=STATUS_LABELS.get(status, ""), text_color=STATUS_COLORS.get(status, "#ffffff"))
        # Logs become available as soon as there's something to show.
        if status is not None:
            self.logs_button.configure(state="normal")
