"""Native OS dialogs (folder picker) for the desktop app."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def pick_folder(initial: str | None = None) -> str | None:
    """Open a native folder picker. Returns the chosen path, or None if cancelled."""
    start = initial or str(Path.home() / "Downloads")
    if not Path(start).exists():
        start = str(Path.home())

    try:
        import webview

        if webview.windows:
            result = webview.windows[0].create_file_dialog(
                webview.FOLDER_DIALOG,
                directory=start,
            )
            if result:
                return str(result[0])
            return None
    except Exception:
        pass

    if sys.platform == "darwin":
        script = (
            'set defaultPath to POSIX file "{path}"\n'
            'set chosen to choose folder with prompt "Choose download folder" default location defaultPath\n'
            "POSIX path of chosen"
        ).format(path=start.replace('"', '\\"'))
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
        return None

    if sys.platform == "win32":
        try:
            import tkinter as tk
            from tkinter import filedialog

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            chosen = filedialog.askdirectory(initialdir=start, title="Choose download folder")
            root.destroy()
            return chosen or None
        except Exception:
            return None

    return None
