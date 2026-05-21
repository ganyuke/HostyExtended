"""
WindowsTrayManager - Handles the system tray icon for Windows.
Allows minimizing the application to the tray and restoring it.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from PIL import Image

import pystray
from gi.repository import GLib


class WindowsTrayManager:
    """Manages the Windows taskbar notification area (system tray) icon."""

    def __init__(self, app):
        self.app = app
        self.icon = None
        self._status_message = "Hosty"

    def start(self) -> None:
        """Create and display the tray icon in a background thread."""
        if self.icon is not None:
            return

        # Load application icon
        image = self._get_icon_image()

        # Define tray menu actions
        menu = pystray.Menu(
            pystray.MenuItem("Show Hosty", self._on_show, default=True),
            pystray.MenuItem("Quit", self._on_quit),
        )

        self.icon = pystray.Icon(
            "Hosty",
            image,
            title=self._status_message,
            menu=menu,
        )

        # Start the pystray main loop in a background thread
        self.icon.run_detached()

    def stop(self) -> None:
        """Stop and remove the system tray icon."""
        if self.icon is not None:
            self.icon.stop()
            self.icon = None

    def set_status(self, message: str) -> None:
        """Update the tooltip of the tray icon."""
        self._status_message = f"Hosty - {message}" if message else "Hosty"
        if self.icon is not None:
            self.icon.title = self._status_message

    def _on_show(self, icon, item) -> None:
        """Callback from tray menu to show the window."""
        GLib.idle_add(self._show_window)

    def _on_quit(self, icon, item) -> None:
        """Callback from tray menu to quit the application."""
        GLib.idle_add(self._quit_app)

    def _show_window(self) -> None:
        """Actually show and focus the main window (running on main GTK thread)."""
        if self.app._window:
            self.app._window.set_visible(True)
            self.app._window.present()

    def _quit_app(self) -> None:
        """Gracefully quit the entire application (running on main GTK thread)."""
        self.app.activate_action("quit", None)

    def _get_icon_image(self) -> Image.Image:
        """Retrieve the Hosty SVG icon, rasterize it via GdkPixbuf, and load as PIL Image."""
        try:
            from gi.repository import GdkPixbuf
            svg_path = None

            # 1. Check for bundled/frozen path candidates
            if getattr(sys, "frozen", False):
                bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
                candidates = [
                    bundle_dir / "share" / "icons" / "hicolor" / "scalable" / "apps" / "io.github.sugarycandybar.Hosty.svg",
                    bundle_dir / "icons" / "io.github.sugarycandybar.Hosty.svg",
                    bundle_dir / "io.github.sugarycandybar.Hosty.svg",
                ]
                for candidate in candidates:
                    if candidate.exists():
                        svg_path = candidate
                        break

            # 2. Check for development path
            if not svg_path:
                dev_path = Path(__file__).resolve().parents[3] / "packaging" / "linux" / "io.github.sugarycandybar.Hosty.svg"
                if dev_path.exists():
                    svg_path = dev_path

            if svg_path and svg_path.exists():
                # Load the SVG at standard 32x32 size for system tray
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg_path), 32, 32, True)
                res = pixbuf.save_to_bufferv("png", [], [])
                if isinstance(res, tuple) and len(res) == 2:
                    success, buffer = res
                    if success:
                        return Image.open(io.BytesIO(buffer))
        except Exception as e:
            print(f"Error loading SVG icon with GdkPixbuf: {e}", file=sys.stderr)

        # Fallback image: a simple solid colored image with Hosty's branding color
        return Image.new("RGBA", (32, 32), (46, 194, 126, 255))
