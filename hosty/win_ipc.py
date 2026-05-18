import sys
import json
import threading
import logging
import time
from typing import Any, Dict, Optional

from hosty.shared.backend.server_manager import ServerManager
from hosty.shared.backend.server_process import ServerProcess
from hosty.shared.core.events import set_main_thread_dispatcher

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logging.basicConfig(filename='win_ipc.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s %(message)s')

class WinIPCBackend:
    def __init__(self):
        self.server_manager = ServerManager()
        self.stdout_lock = threading.Lock()
        self._output_handlers: dict[str, int] = {}  # server_id -> handler_id
        self._psutil_processes: dict[str, Any] = {}  # server_id -> psutil.Process
        
        # Dispatch events from ServerManager back to stdout as JSON events
        set_main_thread_dispatcher(self.dispatch_event)
        
        # Subscribe to server manager events
        self.server_manager.connect('server-added', lambda m, sid: self.send_event('server-added', sid))
        self.server_manager.connect('server-removed', lambda m, sid: self.send_event('server-removed', sid))
        self.server_manager.connect('server-changed', lambda m, sid: self.send_event('server-changed', sid))
        
    def dispatch_event(self, callback, *args, **kwargs):
        # In stdin/stdout IPC, we don't have a UI event loop, so we just run it directly.
        # But we must be careful about thread safety.
        try:
            callback(*args, **kwargs)
        except Exception as e:
            logging.error(f"Event dispatch error: {e}")

    def send_response(self, req_id: Any, result: Any = None, error: str = None):
        msg = {"id": req_id}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        self._write_msg(msg)

    def send_event(self, event_name: str, data: Any):
        msg = {"event": event_name, "data": data}
        self._write_msg(msg)

    def _write_msg(self, msg: Dict):
        try:
            line = json.dumps(msg)
            with self.stdout_lock:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
        except Exception as e:
            logging.error(f"Error writing to stdout: {e}")

    def _attach_console_output(self, server_id: str, proc: ServerProcess):
        """Attach to a server process's output-received signal and forward lines as events."""
        # Detach any existing handler for this server
        self._detach_console_output(server_id)
        
        def on_output(process, text):
            self.send_event("console-output", {"server_id": server_id, "text": text})
        
        handler_id = proc.connect('output-received', on_output)
        self._output_handlers[server_id] = handler_id
    
    def _detach_console_output(self, server_id: str):
        """Detach console output handler for a server."""
        if server_id in self._output_handlers:
            proc = self.server_manager.get_existing_process(server_id)
            if proc:
                try:
                    proc.disconnect(self._output_handlers[server_id])
                except Exception:
                    pass
            del self._output_handlers[server_id]

    def handle_request(self, req: Dict):
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})
        
        logging.debug(f"Received request: {method} {params}")
        
        try:
            if method == "get_servers":
                servers = [s.to_dict() for s in self.server_manager.servers]
                self.send_response(req_id, result=servers)
            
            elif method == "get_versions":
                # Each request already runs in its own thread, so we can fetch synchronously.
                try:
                    game_vers = self.server_manager.download_manager.fetch_game_versions()
                    loader_vers = self.server_manager.download_manager.fetch_loader_versions()
                    self.send_response(req_id, result={"game_versions": game_vers, "loader_versions": loader_vers})
                except Exception as e:
                    self.send_response(req_id, error=f"Failed to fetch versions: {e}")
            
            elif method == "get_server_info":
                sid = params.get("server_id")
                info = self.server_manager.get_server(sid)
                self.send_response(req_id, result=info.to_dict() if info else None)
                
            elif method == "install_server":
                name = params.get("name")
                mc_version = params.get("mc_version")
                loader_version = params.get("loader_version", "")
                ram_mb = params.get("ram_mb", 4096)
                
                # We need to run the heavy installation in a thread
                def _install_task():
                    try:
                        self.send_event("install-progress", {"progress": 0.1, "message": "Creating server profile..."})
                        info = self.server_manager.add_server(name, mc_version, loader_version, ram_mb)
                        
                        java_ver = info.java_version
                        java_mgr = self.server_manager.java_manager
                        dl_mgr = self.server_manager.download_manager
                        
                        if not java_mgr.is_java_available(java_ver):
                            self.send_event("install-progress", {"progress": 0.2, "message": f"Downloading Java {java_ver}..."})
                            success, msg = java_mgr.download_jre_sync(java_ver)
                            if not success:
                                raise Exception(f"Failed to download JRE: {msg}")
                                
                        self.send_event("install-progress", {"progress": 0.4, "message": "Downloading Fabric installer..."})
                        installer_path = dl_mgr.download_installer()
                        if not installer_path:
                            raise Exception("Failed to download Fabric installer")
                            
                        self.send_event("install-progress", {"progress": 0.6, "message": "Downloading Minecraft server..."})
                        success, msg = dl_mgr.download_server_jar(mc_version, str(info.server_dir))
                        if not success:
                            raise Exception(f"Failed to download server.jar: {msg}")
                            
                        self.send_event("install-progress", {"progress": 0.8, "message": "Installing Fabric server..."})
                        java_path = java_mgr.get_java_path(java_ver) or java_mgr.get_java_for_mc(mc_version) or "java"
                        success, msg = dl_mgr.install_fabric_server(
                            java_path=java_path,
                            installer_jar=installer_path,
                            mc_version=mc_version,
                            server_dir=str(info.server_dir),
                            loader_version=loader_version if loader_version else None
                        )
                        if not success:
                            raise Exception(f"Fabric installation failed: {msg}")
                            
                        from hosty.shared.backend.config_manager import ConfigManager
                        config = ConfigManager(str(info.server_dir))
                        config.load()
                        config.set_eula(True)
                        config.save()
                        
                        self.send_event("install-progress", {"progress": 1.0, "message": "Done!"})
                        self.send_event("install-complete", {"server_id": info.id})
                    except Exception as e:
                        self.send_event("install-error", {"error": str(e)})
                        
                threading.Thread(target=_install_task, daemon=True).start()
                self.send_response(req_id, result=True)
                
            elif method == "rename_server":
                self.server_manager.rename_server(params.get("server_id"), params.get("new_name"))
                self.send_response(req_id, result=True)
                
            elif method == "delete_server":
                sid = params.get("server_id")
                self._detach_console_output(sid)
                self.server_manager.delete_server(sid, delete_files=params.get("delete_files", False))
                self.send_response(req_id, result=True)
                
            elif method == "start_server":
                sid = params.get("server_id")
                proc = self.server_manager.get_process(sid)
                if proc:
                    # Attach console output streaming before starting
                    self._attach_console_output(sid, proc)
                    
                    # Also watch for status changes
                    def on_status(process, status):
                        self.send_event("server-status", {"server_id": sid, "status": status})
                    proc.connect('status-changed', on_status)
                    
                    proc.start()
                    self.send_response(req_id, result=True)
                else:
                    self.send_response(req_id, error="Process not found")
                    
            elif method == "stop_server":
                sid = params.get("server_id")
                proc = self.server_manager.get_process(sid)
                if proc:
                    proc.stop()
                    self.send_response(req_id, result=True)
                else:
                    self.send_response(req_id, error="Process not found")
            
            elif method == "send_command":
                sid = params.get("server_id")
                command = params.get("command", "")
                proc = self.server_manager.get_existing_process(sid)
                if proc and proc.is_running:
                    proc.send_command(command)
                    self.send_response(req_id, result=True)
                else:
                    self.send_response(req_id, error="Server is not running")
            
            elif method == "get_console_log":
                sid = params.get("server_id")
                proc = self.server_manager.get_existing_process(sid)
                if proc:
                    # Also attach output if not already
                    if sid not in self._output_handlers:
                        self._attach_console_output(sid, proc)
                    self.send_response(req_id, result={"log": proc.log_history})
                else:
                    self.send_response(req_id, result={"log": []})
            
            elif method == "update_ram":
                sid = params.get("server_id")
                ram_mb = params.get("ram_mb", 2048)
                self.server_manager.update_server_ram(sid, ram_mb)
                self.send_response(req_id, result=True)
            
            elif method == "get_runtime_state":
                sid = params.get("server_id")
                proc = self.server_manager.get_existing_process(sid)
                if proc and proc.is_running:
                    state = {
                        "is_running": True,
                        "status": proc.status,
                        "pid": proc.pid,
                        "cpu_percent": 0.0,
                        "ram_mb": 0.0,
                        "player_count": proc.player_count,
                        "max_players": proc.max_players,
                    }
                    
                    # Get real CPU/RAM via psutil if available
                    if HAS_PSUTIL and proc.pid:
                        try:
                            ps = self._psutil_processes.get(sid)
                            if ps is None or ps.pid != proc.pid:
                                ps = psutil.Process(proc.pid)
                                self._psutil_processes[sid] = ps
                            
                            cpu_count = psutil.cpu_count() or 1
                            raw_cpu = ps.cpu_percent(interval=None)
                            state["cpu_percent"] = round(raw_cpu / cpu_count, 1)
                            
                            mem = ps.memory_info()
                            state["ram_mb"] = round(mem.rss / (1024 * 1024), 1)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            self._psutil_processes.pop(sid, None)
                    
                    self.send_response(req_id, result=state)
                else:
                    # Cleanup psutil cache
                    self._psutil_processes.pop(sid, None)
                    self.send_response(req_id, result={
                        "is_running": False,
                        "status": "stopped",
                        "player_count": 0,
                        "max_players": 0,
                    })
                    
            elif method == "ping":
                self.send_response(req_id, result="pong")
                
            else:
                self.send_response(req_id, error=f"Unknown method: {method}")
                
        except Exception as e:
            logging.exception("Error handling request")
            self.send_response(req_id, error=str(e))

    def run(self):
        logging.info("WinIPCBackend started")
        # Send a ready event
        self.send_event("ready", None)
        
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                # Handle in a thread so we don't block the stdin reader
                threading.Thread(target=self.handle_request, args=(req,), daemon=True).start()
            except json.JSONDecodeError:
                logging.error(f"Invalid JSON: {line}")
            except Exception as e:
                logging.error(f"Error reading line: {e}")

if __name__ == "__main__":
    backend = WinIPCBackend()
    backend.run()
