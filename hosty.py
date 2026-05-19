#!/usr/bin/env python3
"""
Hosty - Fabric Minecraft Server Manager
A modern libadwaita application for creating, running,
and managing Fabric Minecraft servers.
"""
import os
import sys
from pathlib import Path

from hosty.factory import create_application


def _prepend_env_path(name: str, value: Path) -> None:
    value_text = str(value)
    current = os.environ.get(name)
    if current:
        os.environ[name] = value_text + os.pathsep + current
    else:
        os.environ[name] = value_text


def _configure_frozen_gtk_environment() -> None:
    """Point GTK/PyGObject at bundled runtime files in PyInstaller builds."""
    if not getattr(sys, "frozen", False):
        return

    bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    _prepend_env_path("PATH", bundle_dir)

    typelib_dir = bundle_dir / "lib" / "girepository-1.0"
    if typelib_dir.exists():
        _prepend_env_path("GI_TYPELIB_PATH", typelib_dir)

    share_dir = bundle_dir / "share"
    if share_dir.exists():
        _prepend_env_path("XDG_DATA_DIRS", share_dir)
        os.environ.setdefault("GTK_DATA_PREFIX", str(bundle_dir))
        os.environ.setdefault("GTK_EXE_PREFIX", str(bundle_dir))

    schemas_dir = share_dir / "glib-2.0" / "schemas"
    if schemas_dir.exists():
        os.environ.setdefault("GSETTINGS_SCHEMA_DIR", str(schemas_dir))


def _format_missing_gtk_message() -> str:
    if sys.platform == "win32":
        return (
            "GTK startup error: PyGObject is not installed for this Python. "
            "Install GTK4/libadwaita and PyGObject with MSYS2 UCRT64 or Conda, "
            "then run Hosty with that environment's Python."
        )

    return (
        "GTK startup error: PyGObject is not installed for this Python. "
        "Install GTK4/libadwaita and PyGObject for your system, then try again."
    )


def main():
    """Launch the Hosty application."""
    try:
        _configure_frozen_gtk_environment()
        app = create_application()
        return app.run(sys.argv)
    except KeyboardInterrupt:
        return 130
    except ModuleNotFoundError as exc:
        if exc.name == "gi":
            print(_format_missing_gtk_message(), file=sys.stderr)
            return 2
        print(f"Hosty startup error: {exc}", file=sys.stderr)
        return 1
    except NotImplementedError as exc:
        print(f"Hosty startup error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Hosty startup error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
