"""
The "fun terminal" — a log viewer styled to feel like a terminal (dark,
monospace-ish, scrollable) but showing translated, friendly messages by
default instead of raw technical output. A toggle reveals the raw log
underneath for anyone who wants it.
"""

import customtkinter as ctk


class TerminalPanel(ctk.CTkToplevel):
    def __init__(self, master, app_name: str):
        super().__init__(master)
        self.title(f"{app_name} — Logs")
        self.geometry("560x420")
        self.configure(fg_color="#1a1a1a")

        self.showing_raw = False
        self.friendly_lines: list[str] = []
        self.raw_lines: list[str] = []

        header = ctk.CTkLabel(self, text=f"🖥️  {app_name}", font=ctk.CTkFont(size=16, weight="bold"))
        header.pack(pady=(16, 4), padx=16, anchor="w")

        self.textbox = ctk.CTkTextbox(
            self, fg_color="#0f0f0f", text_color="#e8e8e8",
            font=ctk.CTkFont(family="Consolas", size=13),
            corner_radius=10,
        )
        self.textbox.pack(fill="both", expand=True, padx=16, pady=8)
        self.textbox.configure(state="disabled")

        self.toggle_button = ctk.CTkButton(
            self, text="Show raw log", fg_color="#333333", hover_color="#404040",
            command=self._toggle_raw,
        )
        self.toggle_button.pack(pady=(0, 16), padx=16, fill="x")

    def add_line(self, raw_line: str, friendly: str | None) -> None:
        self.raw_lines.append(raw_line)
        if friendly is not None:
            self.friendly_lines.append(friendly)
        self._refresh()

    def _toggle_raw(self) -> None:
        self.showing_raw = not self.showing_raw
        self.toggle_button.configure(text="Show friendly log" if self.showing_raw else "Show raw log")
        self._refresh()

    def _refresh(self) -> None:
        lines = self.raw_lines if self.showing_raw else self.friendly_lines
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.insert("end", "\n".join(lines) if lines else "Waiting for activity...")
        self.textbox.see("end")
        self.textbox.configure(state="disabled")
