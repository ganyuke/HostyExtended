import sys
import subprocess
from pathlib import Path

class HostyWinUIApp:
    """Launcher for the WinUI 3 Application frontend."""
    
    def run(self, argv: list[str]) -> int:
        # Path to the WinUI 3 .csproj
        project_dir = Path(__file__).parent / "winui_ui"
        csproj = project_dir / "winui_ui.csproj"
        
        if not csproj.exists():
            print(f"Error: WinUI project not found at {csproj}", file=sys.stderr)
            return 1
            
        print("Launching Hosty WinUI 3 Application...", flush=True)
        try:
            # We use dotnet run so it builds if necessary and launches the app.
            # In a distributed production environment, you would launch the built .exe directly.
            result = subprocess.run(["dotnet", "run", "--project", str(csproj)])
            return result.returncode
        except FileNotFoundError:
            print("Error: 'dotnet' command not found. Ensure the .NET SDK is installed.", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            return 130
        except Exception as e:
            print(f"Failed to launch WinUI app: {e}", file=sys.stderr)
            return 1
