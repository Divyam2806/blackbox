"""
BlackBox FW-Agent & Gazebo Simulation MCP Server.

Provides Model Context Protocol (MCP) tools, resources, and prompts for
controlling Gazebo physics simulation, reading state & telemetry,
and running FW-Agent autonomous test suites.
"""
import os
import sys
import json
import time
import re
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from mcp.server.mcpserver import MCPServer
except (ImportError, ModuleNotFoundError):
    try:
        import sys
        import importlib
        fastmcp_mod = importlib.import_module("mcp.server.fastmcp")
        MCPServer = getattr(fastmcp_mod, "FastMCP", None)
    except Exception:
        MCPServer = None

if MCPServer is None:
    raise ImportError("The 'mcp' Python package is required. Please install it with 'pip install mcp>=1.0.0'.")

try:
    from mcp.server.transport_security import TransportSecuritySettings
except ImportError:
    TransportSecuritySettings = None


def get_sse_app():
    """Return configured Starlette SSE app with remote access enabled."""
    kwargs = {}
    if TransportSecuritySettings is not None:
        kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
    return mcp.sse_app(**kwargs)


mcp = MCPServer("Gazebo-FWAgent-Server")

STATE_FILE = Path(tempfile.gettempdir()) / "gz_mock_state.json"

@mcp.tool()
def start_gazebo_simulation(world_file: str = "worlds/diff_drive.sdf", gui: bool = True) -> Dict[str, Any]:
    """Start Gazebo simulation server with optional GUI visualization."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    exe = "gz"
    cmd = [exe, "sim"]
    if not gui:
        cmd.append("-s")
    cmd.extend(["-r", "-v", "3", world_file])
    
    proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=(os.name == 'nt'))
    time.sleep(1.0)
    return {
        "status": "started",
        "pid": proc.pid,
        "world_file": world_file,
        "gui": gui,
        "backend": "gazebo"
    }

@mcp.tool()
def stop_gazebo_simulation() -> Dict[str, Any]:
    """Stop active Gazebo simulation processes."""
    if os.name == 'nt':
        subprocess.run(["taskkill", "/F", "/IM", "python.exe", "/FI", "WINDOWTITLE eq Gazebo Sim*"], capture_output=True)
    return {"status": "stopped"}

@mcp.tool()
def send_vehicle_speed(speed: float) -> Dict[str, Any]:
    """Publish a linear velocity twist command to vehicle_blue in Gazebo."""
    exe = "gz"
    p = subprocess.run([exe, "topic", "-t", "/model/vehicle_blue/cmd_vel", "-m", "gz.msgs.Twist", "-p", f"linear: {{x: {speed}}}"],
                       capture_output=True, text=True, shell=(os.name == 'nt'))
    return {
        "status": "command_published" if p.returncode == 0 else "failed",
        "cmd_topic": "/model/vehicle_blue/cmd_vel",
        "speed": speed,
        "output": p.stdout.strip() or p.stderr.strip()
    }

@mcp.tool()
def get_gazebo_state() -> Dict[str, Any]:
    """Get current vehicle odometry position and simulation state from Gazebo."""
    exe = "gz"
    p = subprocess.run([exe, "topic", "-e", "-t", "/model/vehicle_blue/odometry", "-n", "1"],
                       capture_output=True, text=True, shell=(os.name == 'nt'))
    
    x = 0.0
    if p.returncode == 0 and "x:" in p.stdout:
        m = re.search(r"\bx:\s*(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", p.stdout)
        if m:
            x = float(m.group(1))

    return {
        "vehicle": "vehicle_blue",
        "position_x": x,
        "position_y": 0.0,
        "position_z": 0.0,
        "raw_odometry": p.stdout.strip()
    }

@mcp.tool()
def list_gazebo_topics() -> List[str]:
    """List all active Gazebo simulation topics."""
    exe = "gz"
    p = subprocess.run([exe, "topic", "-l"], capture_output=True, text=True, shell=(os.name == 'nt'))
    if p.returncode == 0:
        return [line.strip() for line in p.stdout.strip().splitlines() if line.strip()]
    return ["/clock", "/model/vehicle_blue/cmd_vel", "/model/vehicle_blue/odometry"]

@mcp.tool()
def run_fwagent_suite(firmware: str = "firmware_samples/cooling_fan_good", sim_backend: str = "gazebo") -> Dict[str, Any]:
    """Run FW-Agent autonomous test suite against embedded firmware target using specified simulation engine."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["FWAGENT_GZ_WORLD"] = "worlds/diff_drive.sdf"
    env["FWAGENT_GZ_CMD_TOPIC"] = "/model/vehicle_blue/cmd_vel"
    env["FWAGENT_GZ_POSE_TOPIC"] = "/model/vehicle_blue/odometry"
    env["FWAGENT_GZ_REQUIRE"] = "1"

    cmd = [sys.executable, "src/fwagent/cli.py", "run", firmware, "--sim", sim_backend]
    p = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, capture_output=True, text=True)

    return {
        "status": "completed" if p.returncode == 0 else "failed",
        "returncode": p.returncode,
        "stdout": p.stdout[-2000:],
        "stderr": p.stderr[-1000:]
    }

@mcp.resource("gazebo://state")
def get_state_resource() -> str:
    """Resource providing live state of Gazebo simulation."""
    return json.dumps(get_gazebo_state(), indent=2)

@mcp.resource("fwagent://latest_report")
def get_latest_report_resource() -> str:
    """Resource providing findings and verdicts from the latest FW-Agent run."""
    runs_dir = PROJECT_ROOT / "runs"
    if not runs_dir.exists():
        return "No runs available"
    latest_run = max(runs_dir.glob("2026*"), key=lambda p: p.stat().st_mtime, default=None)
    if not latest_run:
        return "No run directories found"
    results_file = latest_run / "results.json"
    if results_file.exists():
        return results_file.read_text()
    return f"Report directory: {latest_run.name}"

if __name__ == "__main__":
    import argparse
    import uvicorn

    default_port = int(os.environ.get("PORT", 8001))

    parser = argparse.ArgumentParser(
        description="BlackBox FW-Agent MCP Server"
    )

    parser.add_argument(
        "--sse",
        action="store_true",
        help="Run in HTTP/SSE transport mode"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address for HTTP/SSE server"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=default_port,
        help=f"Port for HTTP/SSE server (default: {default_port})"
    )

    args = parser.parse_args()

    if args.sse or os.environ.get("RENDER") or "PORT" in os.environ:

        print(
            f"Starting MCP Server in SSE mode on "
            f"http://{args.host}:{args.port}/sse ..."
        )

        app = get_sse_app()

        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def root_status(request):
            return JSONResponse({
                "status": "online",
                "service": "BlackBox FW-Agent & Gazebo Simulation MCP Server",
                "transport": "HTTP/SSE",
                "sse_endpoint": "/sse",
                "messages_endpoint": "/messages",
                "mcp_version": "1.0.0",
                "note": "Connect remote AI agents to /sse endpoint"
            })

        app.routes.append(Route("/", endpoint=root_status, methods=["GET"]))

        uvicorn.run(
            app,
            host=args.host,
            port=args.port
        )

    else:
        mcp.run()

