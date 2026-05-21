"""
WindowsTrayManager - Handles the system tray icon for Windows.
Allows minimizing the application to the tray and restoring it.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

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

        try:
            image = self._get_icon_image()

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

            self.icon.run_detached()
        except Exception as e:
            print(f"Failed to start tray icon: {e}", file=sys.stderr)

    def stop(self) -> None:
        """Stop and remove the system tray icon."""
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def set_status(self, message: str) -> None:
        """Update the tooltip of the tray icon."""
        self._status_message = f"Hosty - {message}" if message else "Hosty"
        if self.icon is not None:
            try:
                self.icon.title = self._status_message
            except Exception:
                pass

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
        """Try to load the Hosty SVG icon; fall back to a drawn PIL image."""
        image = self._try_load_svg_icon()
        if image is not None:
            return image
        return self._create_fallback_icon()

    def _try_load_svg_icon(self) -> Image.Image | None:
        """Attempt to load the Hosty SVG via GdkPixbuf and return a PIL Image."""
        try:
            from gi.repository import GdkPixbuf
            svg_path = self._find_svg_path()
            if svg_path and svg_path.exists():
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(svg_path), 32, 32, True)
                res = pixbuf.save_to_bufferv("png", [], [])
                if isinstance(res, tuple) and len(res) == 2:
                    success, buffer = res
                    if success:
                        return Image.open(io.BytesIO(buffer))
        except Exception as e:
            print(f"SVG icon load failed: {e}", file=sys.stderr)
        return None

    def _find_svg_path(self) -> Path | None:
        """Locate the Hosty SVG icon from bundled or development paths."""
        if getattr(sys, "frozen", False):
            bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            candidates = [
                bundle_dir / "share" / "icons" / "hicolor" / "scalable" / "apps" / "io.github.sugarycandybar.Hosty.svg",
                bundle_dir / "icons" / "io.github.sugarycandybar.Hosty.svg",
                bundle_dir / "io.github.sugarycandybar.Hosty.svg",
            ]
            for candidate in candidates:
                if candidate.exists():
                    return candidate

        dev_path = Path(__file__).resolve().parents[3] / "packaging" / "linux" / "io.github.sugarycandybar.Hosty.svg"
        if dev_path.exists():
            return dev_path
        return None

    def _create_fallback_icon(self) -> Image.Image:
        """Create a visible fallback icon with a green circle and 'H' letter."""
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        draw.ellipse([2, 2, size - 2, size - 2], fill=(46, 194, 126, 255))

        try:
            from PIL import ImageFont
            font = ImageFont.truetype("segoeui.ttf", 36)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), "H", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (size - tw) / 2 - bbox[0]
        ty = (size - th) / 2 - bbox[1]
        draw.text((tx, ty), "H", fill=(255, 255, 255, 255), font=font)

        return img.resize((32, 32), Image.LANCZOS)
