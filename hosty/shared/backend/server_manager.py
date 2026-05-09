"""
ServerManager - CRUD operations for server instances.
Handles persistence, creation workflow, and server lifecycle.
"""
import json
import uuid
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from hosty.shared.utils.constants import (
    SERVERS_DIR, CONFIG_FILE, DEFAULT_RAM_MB, DEFAULT_SERVER_PROPERTIES,
    get_required_java_version,
)
from hosty.shared.backend.server_process import ServerProcess
from hosty.shared.backend.config_manager import ConfigManager
from hosty.shared.backend.java_manager import JavaManager
from hosty.shared.backend.download_manager import DownloadManager
from hosty.shared.backend.playit_manager import PlayitManager
from hosty.shared.backend.preferences_manager import PreferencesManager
from hosty.shared.core.events import EventEmitter


class ServerInfo:
    """Data class for server metadata."""
    
    def __init__(self, data: dict):
        self.id: str = data.get("id", str(uuid.uuid4()))
        self.name: str = data.get("name", "Unnamed Server")
        self.mc_version: str = data.get("mc_version", "")
        self.loader_version: str = data.get("loader_version", "")
        self.ram_mb: int = data.get("ram_mb", DEFAULT_RAM_MB)
        self.java_version: int = data.get("java_version", 21)
        self.icon_path: str = data.get("icon_path", "")
        self.created_at: str = data.get("created_at", datetime.now().isoformat())
        self.path: str = data.get("path", "")
        self.autostart: bool = data.get("autostart", False)
    
    @property
    def server_dir(self) -> Path:
        """Get the server directory path."""
        if self.path:
            return Path(self.path)
        return SERVERS_DIR / self.id
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mc_version": self.mc_version,
            "loader_version": self.loader_version,
            "ram_mb": self.ram_mb,
            "java_version": self.java_version,
            "icon_path": self.icon_path,
            "created_at": self.created_at,
            "path": str(self.server_dir),
            "autostart": self.autostart,
        }


class ServerManager(EventEmitter):
    """
    Manages all server instances: CRUD, persistence, and process management.
    """
    
    def __init__(self):
        super().__init__()
        self._servers: dict[str, ServerInfo] = {}
        self._processes: dict[str, ServerProcess] = {}
        self._mods_operation_counts: dict[str, int] = {}
        self.java_manager = JavaManager()
        self.download_manager = DownloadManager()
        self.playit_manager = PlayitManager()
        self.preferences = PreferencesManager()
        self._load()
    
    def _load(self):
        """Load servers from persisted JSON."""
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                for entry in data.get("servers", []):
                    info = ServerInfo(entry)
                    self._servers[info.id] = info
            except Exception as e:
                print(f"Failed to load servers: {e}")
    
    def _save(self):
        """Persist servers to JSON."""
        data = {
            "servers": [s.to_dict() for s in self._servers.values()]
        }
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Failed to save servers: {e}")
    
    @property
    def servers(self) -> list[ServerInfo]:
        """Get all servers sorted by creation date."""
        return sorted(self._servers.values(), key=lambda s: s.created_at)
    
    def get_server(self, server_id: str) -> Optional[ServerInfo]:
        """Get a server by ID."""
        return self._servers.get(server_id)
    
    def add_server(self, name: str, mc_version: str, loader_version: str = "",
                   ram_mb: int = DEFAULT_RAM_MB) -> ServerInfo:
        """
        Create and register a new server.
        Does NOT install Fabric — call install_server() separately.
        """
        server_id = str(uuid.uuid4())
        java_ver = get_required_java_version(mc_version)
        
        info = ServerInfo({
            "id": server_id,
            "name": name,
            "mc_version": mc_version,
            "loader_version": loader_version,
            "ram_mb": ram_mb,
            "java_version": java_ver,
            "path": str(SERVERS_DIR / server_id),
        })
        
        # Create server directory
        info.server_dir.mkdir(parents=True, exist_ok=True)
        
        self._servers[server_id] = info
        self._save()
        self.emit_on_main_thread('server-added', server_id)
        
        return info
    
    def rename_server(self, server_id: str, new_name: str):
        """Rename a server."""
        info = self._servers.get(server_id)
        if info:
            info.name = new_name
            self._save()
            self.emit_on_main_thread('server-changed', server_id)
    
    def set_server_icon(self, server_id: str, icon_path: str):
        """Set the icon for a server."""
        info = self._servers.get(server_id)
        if info:
            info.icon_path = icon_path
            self._save()
            self.emit_on_main_thread('server-changed', server_id)

    def get_autostart_server(self) -> Optional[ServerInfo]:
        """Get the server configured to auto-start, if any."""
        for server in self._servers.values():
            if server.autostart:
                return server
        return None

    def set_server_autostart(self, server_id: str, autostart: bool) -> tuple[bool, Optional[str]]:
        """Enable or disable autostart for a server. Returns (success, error_msg)."""
        info = self._servers.get(server_id)
        if not info:
            return False, "Server not found."
            
        if autostart:
            existing = self.get_autostart_server()
            if existing and existing.id != server_id:
                return False, f"Server '{existing.name}' is already configured to start on startup."
                
        info.autostart = autostart
        self._save()
        self.emit_on_main_thread('server-changed', server_id)
        return True, None
    
    def update_server_ram(self, server_id: str, ram_mb: int):
        """Update RAM allocation for a server."""
        info = self._servers.get(server_id)
        if info:
            info.ram_mb = ram_mb
            self._save()
            proc = self._processes.get(server_id)
            if proc:
                proc.ram_mb = ram_mb
            self.emit_on_main_thread('server-changed', server_id)

    def restore_server(self, server_data: dict) -> bool:
        """Restore a previously deleted server metadata entry."""
        try:
            info = ServerInfo(server_data)
        except Exception:
            return False

        if not info.id or info.id in self._servers:
            return False

        self._servers[info.id] = info
        self._save()
        self.emit_on_main_thread('server-added', info.id)
        return True
    
    def delete_server(self, server_id: str, delete_files: bool = True):
        """Delete a server. Optionally delete its files."""
        info = self._servers.get(server_id)
        if not info:
            return

        if self.playit_manager.is_running_for(server_id):
            self.playit_manager.stop()
        
        # Stop if running
        process = self._processes.get(server_id)
        if process and process.is_running:
            process.kill()
        
        if server_id in self._processes:
            del self._processes[server_id]
        
        # Delete files
        if delete_files and info.server_dir.exists():
            shutil.rmtree(info.server_dir, ignore_errors=True)
        
        del self._servers[server_id]
        self._save()
        self.emit_on_main_thread('server-removed', server_id)
    
    def get_process(self, server_id: str) -> Optional[ServerProcess]:
        """Get or create a ServerProcess for a server."""
        info = self._servers.get(server_id)
        if not info:
            return None
        
        if server_id not in self._processes:
            java_path = self.java_manager.get_java_for_mc(info.mc_version)
            if not java_path:
                # Try system java as fallback
                java_path = shutil.which("java")

            config = self.get_config(server_id)
            max_players = 20
            if config:
                config.load()
                max_players = config.get_int("max-players", 20)
            
            self._processes[server_id] = ServerProcess(
                server_dir=str(info.server_dir),
                java_path=java_path or "java",
                ram_mb=info.ram_mb,
                max_players=max_players,
            )
        
        return self._processes[server_id]

    def get_existing_process(self, server_id: str) -> Optional[ServerProcess]:
        """Get an existing ServerProcess without creating a new one."""
        return self._processes.get(server_id)
    
    def get_config(self, server_id: str) -> Optional[ConfigManager]:
        """Get a ConfigManager for a server's server.properties."""
        info = self._servers.get(server_id)
        if not info:
            return None
        return ConfigManager(str(info.server_dir))
    
    def is_any_server_running(self) -> bool:
        """Check if any server is currently running."""
        return any(p.is_running for p in self._processes.values())

    def get_running_server_id(self) -> Optional[str]:
        """Return the server id whose process is running, or None."""
        for server_id, process in self._processes.items():
            if process.is_running:
                return server_id
        return None

    def begin_mod_operation(self, server_id: str) -> None:
        """Mark a server as having an active mod install/update operation."""
        if not server_id:
            return
        count = int(self._mods_operation_counts.get(server_id, 0)) + 1
        self._mods_operation_counts[server_id] = count
        self.emit_on_main_thread("mods-operation-changed", server_id, True, count)

    def end_mod_operation(self, server_id: str) -> None:
        """Clear one active mod install/update operation for a server."""
        if not server_id:
            return
        count = int(self._mods_operation_counts.get(server_id, 0)) - 1
        if count <= 0:
            self._mods_operation_counts.pop(server_id, None)
            count = 0
            active = False
        else:
            self._mods_operation_counts[server_id] = count
            active = True
        self.emit_on_main_thread("mods-operation-changed", server_id, active, count)

    def is_mod_operation_active(self, server_id: str) -> bool:
        """True while any mod install/update operation is active for this server."""
        if not server_id:
            return False
        return int(self._mods_operation_counts.get(server_id, 0)) > 0
        
    def stop_all(self):
        """Stop all running servers."""
        self.playit_manager.stop()
        for server_id, process in self._processes.items():
            if process.is_running:
                process.stop()
                # Wait up to 3 seconds for graceful shutdown, then forcefully kill to prevent orphans
                try:
                    process.process.wait(timeout=3.0)
                except Exception:
                    pass
                process.kill()

    def _configured_level_name(self, server_root: Path) -> str:
        """Read level-name from server.properties, defaulting to world."""
        try:
            cfg = ConfigManager(server_root)
            cfg.load()
            name = cfg.get("level-name", "world").strip()
            return name or "world"
        except Exception:
            return "world"

    def _is_world_dir(self, item: Path, level_name: str) -> bool:
        if not item.is_dir():
            return False

        if (item / "level.dat").exists():
            return True

        if item.name.casefold() == level_name.casefold():
            return True

        markers = (
            "region",
            "data",
            "playerdata",
            "poi",
            "entities",
            "stats",
            "advancements",
            "dimensions",
            "DIM-1",
            "DIM1",
            "session.lock",
            "uid.dat",
        )
        return any((item / marker).exists() for marker in markers)

    def _is_importable_world_dir(self, item: Path) -> bool:
        if not item.is_dir():
            return False
        if not (item / "level.dat").is_file():
            return False

        markers = (
            "region",
            "data",
            "playerdata",
            "poi",
            "entities",
            "stats",
            "advancements",
            "dimensions",
            "DIM-1",
            "DIM1",
            "session.lock",
            "uid.dat",
        )
        return any((item / marker).exists() for marker in markers)

    def _iter_world_dirs(self, server_root: Path) -> list[Path]:
        if not server_root.is_dir():
            return []

        level_name = self._configured_level_name(server_root)
        preferred = server_root / "world"
        if self._is_world_dir(preferred, level_name):
            return [preferred]

        worlds = [item for item in server_root.iterdir() if self._is_world_dir(item, level_name)]
        if not worlds:
            return []

        worlds = sorted(worlds, key=lambda p: p.name.lower())
        return [worlds[0]]

    def _unique_world_destination(self, server_root: Path, name: str) -> Path:
        safe_name = Path(name).name.strip() or "world"
        candidate = server_root / safe_name
        if not candidate.exists():
            return candidate

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        candidate = server_root / f"{safe_name}-{stamp}"
        suffix = 2
        while candidate.exists():
            candidate = server_root / f"{safe_name}-{stamp}-{suffix}"
            suffix += 1
        return candidate

    def create_world_folder(self, server_id: str, name: str, seed: str = "") -> tuple[bool, str]:
        """Create/select a new world folder and configure the server to generate it."""
        info = self.get_server(server_id)
        if not info:
            return False, "Server not found"

        process = self._processes.get(server_id)
        if process and process.is_running:
            return False, "Server is running"

        root = info.server_dir
        world_dir = root / "world"

        try:
            level_name = self._configured_level_name(root)
            for item in root.iterdir():
                if not self._is_world_dir(item, level_name):
                    continue
                if item.resolve() == world_dir.resolve():
                    continue
                if item.exists():
                    shutil.rmtree(item, ignore_errors=True)

            if world_dir.exists():
                shutil.rmtree(world_dir, ignore_errors=True)

            world_dir.mkdir(parents=True, exist_ok=True)
            cfg = ConfigManager(root)
            cfg.load()
            cfg.set_value("level-name", "world")
            cfg.set_value("level-seed", seed.strip())
            cfg.save()
        except Exception as e:
            return False, str(e)

        self.emit_on_main_thread("server-changed", server_id)
        return True, world_dir.name

    def import_world_folder(self, server_id: str, source: str | Path) -> tuple[bool, str]:
        """Copy an existing world folder into a server and select it as level-name."""
        info = self.get_server(server_id)
        if not info:
            return False, "Server not found"

        process = self._processes.get(server_id)
        if process and process.is_running:
            return False, "Server is running"

        src = Path(source).expanduser()
        if not src.is_dir():
            return False, "Selected world folder does not exist"
        if not self._is_importable_world_dir(src):
            return False, "Selected folder does not look like a Minecraft world"

        root = info.server_dir
        dst = root / "world"
        try:
            level_name = self._configured_level_name(root)
            for item in root.iterdir():
                if not self._is_world_dir(item, level_name):
                    continue
                if item.resolve() == dst.resolve():
                    continue
                if item.exists():
                    shutil.rmtree(item, ignore_errors=True)

            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)

            from hosty.shared.utils.nbt_utils import get_world_info
            seed, wtype = get_world_info(src)

            shutil.copytree(src, dst)
            cfg = ConfigManager(root)
            cfg.load()
            cfg.set_value("level-name", "world")
            if seed:
                cfg.set_value("level-seed", seed)
            else:
                cfg.set_value("level-seed", "")
            if wtype:
                cfg.set_value("level-type", wtype)
            cfg.save()
        except Exception as e:
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            return False, str(e)

        self.emit_on_main_thread("server-changed", server_id)
        return True, dst.name

    def export_world_zip(self, server_id: str, world: str | Path, destination: str | Path) -> tuple[bool, str]:
        """Export one world folder to a zip archive."""
        info = self.get_server(server_id)
        if not info:
            return False, "Server not found"

        world_path = Path(world)
        if not world_path.is_absolute():
            world_path = info.server_dir / world_path
        if not world_path.is_dir():
            return False, "World folder does not exist"

        try:
            world_path.resolve().relative_to(info.server_dir.resolve())
        except ValueError:
            return False, "World folder is outside this server"

        dest = Path(destination).expanduser()
        if dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for item in world_path.rglob("*"):
                    if not item.is_file():
                        continue
                    arc = Path(world_path.name) / item.relative_to(world_path)
                    zf.write(item, arcname=str(arc).replace("\\", "/"))
        except Exception as e:
            return False, str(e)

        return True, str(dest)

    def create_world_backup(self, server_id: str, auto: bool = False) -> tuple[bool, str]:
        """Create a zip backup containing world folders only."""
        info = self.get_server(server_id)
        if not info:
            return False, "Server not found"

        process = self._processes.get(server_id)
        if process and process.is_running:
            return False, "Server is running"

        root = info.server_dir
        if not root.exists():
            return False, "Server directory does not exist"

        worlds = self._iter_world_dirs(root)
        if not worlds:
            return False, "No world folder found"

        backups_dir = root / "hosty-backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        prefix = "hosty-auto-backup" if auto else "hosty-backup"
        backup_path = backups_dir / f"{prefix}-{stamp}.zip"

        try:
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                world_dir = worlds[0]
                for item in world_dir.rglob("*"):
                    if not item.is_file():
                        continue
                    arc = item.relative_to(root)
                    zf.write(item, arcname=str(arc).replace("\\", "/"))
        except Exception as e:
            return False, str(e)

        return True, backup_path.name
