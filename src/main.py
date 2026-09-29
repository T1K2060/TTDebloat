"""
Entry point for the whole app. This is what the bootstrapper will launch
(via the bundled portable Python) once that part is built.
"""

from src.gui.app import DebloatApp

if __name__ == "__main__":
    app = DebloatApp()
    app.mainloop()
