"""
FilesView — folders, worlds, backups, and Modrinth integration (per selected server).
"""
from __future__ import annotations

import json
import ast
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import uuid

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Adw, Gio, GLib, Pango, Gdk, GdkPixbuf

from hosty.shared.backend.config_manager import ConfigManager
from hosty.shared.backend.server_manager import ServerManager, ServerInfo



from ..utils import *

class WorldsMixin:
    def _configured_world_seed(self) -> str:
        if not self._server_info:
            return ""

        try:
            cfg = ConfigManager(self._server_info.server_dir)
            cfg.load()
            return cfg.get("level-seed", "").strip()
        except Exception:
            return ""

    def _make_world_row(self, path: Path) -> Adw.ActionRow:
        dims = _world_dimension_dirs(path)
        row_title = "World" if path.name == "world" else path.name
        row = Adw.ActionRow(title=row_title)
        seed = _world_seed(path) or self._configured_world_seed()
        
        subtitle_parts = []
        if seed:
            subtitle_parts.append(seed)
        if not dims:
            subtitle_parts.append("0 dimensions")
        else:
            subtitle_parts.append(f"{len(dims)} dimensions")
            
        row.set_subtitle(" · ".join(subtitle_parts))
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.set_activatable(True)
        row.connect("activated", lambda *_: self._push_world_page(path))

        return row

    def _push_world_page(self, path: Path) -> None:
        show_fullscreen = self._push_fullscreen_page_cb is not None
        page_title = "World" if path.name == "world" else path.name
        page = Adw.NavigationPage(
            title=page_title,
            child=self._build_world_page(path, show_controls=show_fullscreen)
        )
        if show_fullscreen:
            self._push_fullscreen_page_cb(page)
        else:
            self._nav.push(page)

    def _build_world_page(self, path: Path, show_controls: bool = False) -> Gtk.Widget:
        page = Adw.PreferencesPage()

        # Seed row
        seed = _world_seed(path) or self._configured_world_seed()
        if seed:
            seed_group = Adw.PreferencesGroup(title="Seed")
            seed_row = Adw.ActionRow(title="World Seed", subtitle=seed)
            copy_btn = self._icon_button(
                "edit-copy-symbolic",
                "Copy world seed",
                lambda *_p, s=seed: self._copy_world_seed(s),
            )
            seed_row.add_suffix(copy_btn)
            seed_group.add(seed_row)
            page.add(seed_group)

        # Actions
        actions_group = Adw.PreferencesGroup(title="Actions")
        
        open_row = Adw.ActionRow(title="Open World Folder")
        open_row.add_prefix(Gtk.Image.new_from_icon_name("folder-open-symbolic"))
        open_row.set_activatable(True)
        open_row.connect("activated", lambda *_: self._open_target(path))
        actions_group.add(open_row)

        export_row = Adw.ActionRow(title="Export World")
        export_row.add_prefix(Gtk.Image.new_from_icon_name("document-send-symbolic"))
        export_row.set_activatable(True)
        export_row.connect("activated", lambda *_: self._on_export_world(path))

        reset_row = Adw.ActionRow(title="Reset World")
        reset_row.add_prefix(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        reset_row.set_activatable(True)
        reset_row.connect("activated", lambda *_: self._on_reset_world(path))

        import_row = Adw.ActionRow(title="Import World Folder")
        import_row.add_prefix(Gtk.Image.new_from_icon_name("folder-download-symbolic"))
        import_row.set_activatable(True)
        import_row.connect("activated", lambda *_: self._on_import_world())

        actions_group.add(import_row)
        actions_group.add(reset_row)
        actions_group.add(export_row)

        page.add(actions_group)

        # Dimensions
        dims_group = Adw.PreferencesGroup(title="Dimensions")
        dims = _world_dimension_dirs(path)
        if not dims:
            none_row = Adw.ActionRow(title="No dimension folders found")
            none_row.set_activatable(False)
            dims_group.add(none_row)
        else:
            world_root = path.resolve()
            for label, dim_path in dims:
                dim_row = Adw.ActionRow(title=label)
                dim_row.set_activatable(False)

                if dim_path.resolve() != world_root:
                    delete_btn = self._icon_button(
                        "user-trash-symbolic",
                        f"Delete {label}",
                        lambda *_p, w=path, p=dim_path, n=label: self._confirm_delete_dimension(w, p, n),
                        destructive=True,
                    )
                    dim_row.add_suffix(delete_btn)

                dims_group.add(dim_row)

        page.add(dims_group)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sw.set_child(page)
        
        # We need a subpage shell for proper rendering. Assuming it exists in mixin or parent view.
        # But wait, `_build_subpage_shell` is in BackupsMixin. Let's see if we can use it.
        # If FilesView inherits both, self._build_subpage_shell is available.
        shell_title = "World" if path.name == "world" else path.name
        return self._build_subpage_shell(shell_title, sw, show_controls=show_controls)

    def _copy_world_seed(self, seed: str) -> None:
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(seed)
        self._toast("World seed copied")

    # We removed _on_world_settings as its content is now in the page.

    def _on_reset_world(self, path: Path) -> None:
        if self._is_running():
            self._alert("Server is running", "Stop the server before resetting the world.")
            return
        if not self._server_info or not self._server_manager:
            self._alert("No server selected", "Select a server before resetting the world.")
            return

        seed_group = Adw.PreferencesGroup()
        seed_row = Adw.EntryRow(title="Seed")
        seed_row.set_text(_world_seed(path) or self._configured_world_seed())
        seed_row.set_show_apply_button(False)
        seed_group.add(seed_row)

        dialog = Adw.AlertDialog()
        dialog.set_heading("Reset world")
        dialog.set_body("This deletes the current world and creates a new one. Leave Seed empty for a random seed.")
        dialog.set_extra_child(seed_group)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response != "reset":
                return
            ok, msg = self._server_manager.create_world_folder(
                self._server_info.id,
                "world",
                seed_row.get_text().strip(),
            )
            if ok:
                self._toast("World reset")
                self._rebuild_lists()
            else:
                self._alert("Could not reset world", msg)

        dialog.connect("response", on_response)
        dialog.present(self.get_root())

    def _on_import_world(self, *_):
        if self._is_running():
            self._alert("Server is running", "Stop the server before importing a world.")
            return
        if not self._server_info or not self._server_manager:
            self._alert("No server selected", "Select a server before importing a world.")
            return

        dialog = Gtk.FileDialog()
        dialog.set_title("Import World Folder")
        dialog.select_folder(self.get_root(), None, self._on_import_world_folder_selected)

    def _on_import_world_folder_selected(self, dialog, result):
        try:
            selected = dialog.select_folder_finish(result)
        except GLib.Error:
            return

        path = Path(selected.get_path() or "")
        if not path:
            return

        confirm = Adw.AlertDialog()
        confirm.set_heading("Import world folder?")
        confirm.set_body(
            "The imported world's type must match this server's World Type setting "
            "(normal, superflat, amplified, etc.). Hosty will replace the existing world with a single folder named world."
        )
        confirm.add_response("cancel", "Cancel")
        confirm.add_response("import", "Import")
        confirm.set_default_response("import")
        confirm.set_close_response("cancel")

        def on_response(_dialog, response):
            if response != "import" or not self._server_info or not self._server_manager:
                return
            ok, msg = self._server_manager.import_world_folder(self._server_info.id, path)
            if ok:
                self._toast(f"Imported world {msg}")
                self._rebuild_lists()
            else:
                self._alert("Could not import world", msg)

        confirm.connect("response", on_response)
        confirm.present(self.get_root())

    def _on_export_world(self, path: Path):
        if not self._server_info or not self._server_manager:
            self._alert("No server selected", "Select a server before exporting a world.")
            return

        dialog = Gtk.FileDialog()
        dialog.set_title("Export World")
        dialog.set_initial_name(f"{path.name}.zip")
        dialog.save(self.get_root(), None, lambda d, r, p=path: self._on_export_world_selected(d, r, p))

    def _on_export_world_selected(self, dialog, result, path: Path):
        try:
            selected = dialog.save_finish(result)
        except GLib.Error:
            return

        dest = Path(selected.get_path() or "")
        if not dest or not self._server_info or not self._server_manager:
            return

        ok, msg = self._server_manager.export_world_zip(self._server_info.id, path, dest)
        if ok:
            self._toast("World exported")
        else:
            self._alert("Could not export world", msg)

    def _confirm_delete_dimension(self, world_path: Path, dim_path: Path, name: str):
        if self._is_running():
            self._alert("Server is running", "Stop the server before deleting a dimension.")
            return

        if dim_path.resolve() == world_path.resolve():
            self._alert("Cannot delete world root", "Delete only individual dimensions from this list.")
            return

        dialog = Adw.AlertDialog()
        dialog.set_heading("Delete dimension?")
        dialog.set_body(f"Delete dimension “{name}”? This cannot be undone.")
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_d, response):
            if response == "delete":
                self._soft_delete_with_undo(
                    dim_path,
                    f"dimension \"{name}\"",
                    on_refresh=self._rebuild_lists,
                )

        dialog.connect("response", on_response)
        dialog.present(self.get_root())
