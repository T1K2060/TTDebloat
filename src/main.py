"""
Entry point. Opens the HTML UI in a native window (Edge WebView2 on Windows)
and wires it to the Python backend through src/bridge.py.
"""

from pathlib import Path

import webview

from src.bridge import Api

UI_FILE = Path(__file__).parent / "ui" / "index.html"


def main() -> None:
    api = Api()
    window = webview.create_window(
        "Debloat", str(UI_FILE), js_api=api,
        width=1120, height=760, min_size=(820, 560), background_color="#0d0e11",
    )
    api._attach(window)
    webview.start()


if __name__ == "__main__":
    main()
