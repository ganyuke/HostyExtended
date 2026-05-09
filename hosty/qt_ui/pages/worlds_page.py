"""
Worlds page for the Files tab.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hosty.shared.backend.server_manager import ServerInfo, ServerManager
from ..components import SmoothScrollArea
from ..utils import _iter_world_dirs, _open_path


class WorldsPage(QWidget):
    def __init__(self, server_manager: ServerManager, back_callback):
        super().__init__()
        self._server_manager = server_manager
        self._server_info = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setProperty("class", "header-bar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        back_btn = QPushButton("← Back")
        back_btn.setProperty("class", "flat")
        back_btn.clicked.connect(back_callback)
        header_layout.addWidget(back_btn)

        title = QLabel("Worlds")
        title.setProperty("class", "title")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        layout.addWidget(header)

        # Content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(12)

        self._scroll = SmoothScrollArea()
        self._world_list = QListWidget()
        self._world_list.itemDoubleClicked.connect(self._open_selected_world)
        self._world_list.itemSelectionChanged.connect(self._on_world_selected)
        content_layout.addWidget(self._world_list)

        settings_btn = QPushButton("⚙ World Settings")
        settings_btn.setProperty("class", "accent")
        settings_btn.clicked.connect(self._on_world_settings)
        self._settings_btn = settings_btn
        self._settings_btn.setEnabled(False)
        content_layout.addWidget(settings_btn)

        layout.addWidget(content, 1)

    def load_server(self, info: ServerInfo) -> None:
        self._server_info = info
        self._world_list.clear()
        
        if not info.server_dir.exists():
            return
            
        for world in _iter_world_dirs(Path(info.server_dir)):
            item = QListWidgetItem(f"🌍  {world.name}")
            item.setData(Qt.ItemDataRole.UserRole, str(world))
            self._world_list.addItem(item)

    def _open_selected_world(self) -> None:
        item = self._world_list.currentItem()
        if not item:
            QMessageBox.information(self, "Worlds", "Select a world first.")
            return
            
        world_path = item.data(Qt.ItemDataRole.UserRole)
        if world_path and not _open_path(Path(world_path)):
            QMessageBox.warning(self, "Open World", "Could not open selected world folder")

    def _on_world_selected(self) -> None:
        """Enable settings button when a world is selected."""
        self._settings_btn.setEnabled(self._world_list.currentItem() is not None)

    def _on_world_settings(self) -> None:
        """Show world settings dialog."""
        item = self._world_list.currentItem()
        if not item:
            QMessageBox.information(self, "Worlds", "Select a world first.")
            return
        
        world_path = item.data(Qt.ItemDataRole.UserRole)
        if not world_path:
            return
        
        path = Path(world_path)
        
        # Create a simple dialog with options
        dialog = QDialog(self)
        dialog.setWindowTitle(f"World Settings: {path.name}")
        dialog.setMinimumWidth(300)
        
        layout = QVBoxLayout(dialog)
        
        label = QLabel(f"Managing world: {path.name}")
        layout.addWidget(label)
        
        button_layout = QVBoxLayout()
        
        open_btn = QPushButton("Open World Folder")
        open_btn.clicked.connect(lambda: self._open_and_close(path, dialog))
        button_layout.addWidget(open_btn)
        
        export_btn = QPushButton("Export World")
        export_btn.clicked.connect(lambda: self._export_and_close(path, dialog))
        button_layout.addWidget(export_btn)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        dialog.exec()

    def _open_and_close(self, path: Path, dialog: QDialog) -> None:
        """Open world folder and close the dialog."""
        if not _open_path(path):
            QMessageBox.warning(self, "Open World", "Could not open selected world folder")
        dialog.close()

    def _export_and_close(self, path: Path, dialog: QDialog) -> None:
        """Export world (placeholder for future implementation) and close dialog."""
        QMessageBox.information(self, "Export World", f"Export functionality for {path.name} not yet implemented in Qt UI.")
        dialog.close()
