"""Launch the MCP server and the AI dashboard frontend together."""

from __future__ import annotations

import argparse
import os
import signal
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "src" / "ai_dashboard"
ENV_FILE = FRONTEND_DIR / ".env.local"
DEFAULT_FRONTEND_PORT = 3001


def _env_file_has_key(path: Path, key: str) -> bool:
    if not path.exists():
        return False
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(f"{key}="):
                return True
    except OSError:
        return False
    return False


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _find_free_port(host: str, start_port: int, max_tries: int = 30) -> int | None:
    for offset in range(max_tries):
        port = start_port + offset
        if not _is_port_in_use(host, port):
            return port
    return None


def _wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                sock.connect((host, port))
                return True
            except OSError:
                time.sleep(0.2)
    return False


def _start_process(name: str, cmd: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen:
    print(f"[start] {name}: {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(cwd), env=env)


def _terminate_process(name: str, proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    print(f"[stop] {name}")
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _build_frontend_env(mcp_url: str, *, force_mcp_url: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    if force_mcp_url or (
        "MCP_SERVER_URL" not in env and not _env_file_has_key(ENV_FILE, "MCP_SERVER_URL")
    ):
        env["MCP_SERVER_URL"] = mcp_url
    if "AI_DASHBOARD_CONFIG_PATH" not in env and not _env_file_has_key(
        ENV_FILE, "AI_DASHBOARD_CONFIG_PATH"
    ):
        env["AI_DASHBOARD_CONFIG_PATH"] = str(ROOT / "configs" / "ai_dashboard.json")
    return env


def _split_command(command: str) -> list[str]:
    return shlex.split(command, posix=False)


def _resolve_frontend_command(raw_command: str | None) -> list[str] | None:
    if raw_command:
        return _split_command(raw_command)
    npm_path = shutil.which("npm") or shutil.which("npm.cmd") or shutil.which("npm.exe")
    if not npm_path:
        return None
    return [npm_path, "run", "dev"]


def _resolve_next_binary() -> Path | None:
    candidates = [
        FRONTEND_DIR / "node_modules" / ".bin" / "next.cmd",
        FRONTEND_DIR / "node_modules" / ".bin" / "next",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _build_frontend_command(raw_command: str | None, port: int) -> list[str] | None:
    if raw_command:
        return _split_command(raw_command)
    if port == DEFAULT_FRONTEND_PORT:
        return _resolve_frontend_command(None)
    next_bin = _resolve_next_binary()
    if next_bin is not None:
        return [str(next_bin), "dev", "-p", str(port)]
    npm_path = shutil.which("npm") or shutil.which("npm.cmd") or shutil.which("npm.exe")
    if not npm_path:
        return None
    return [npm_path, "run", "dev", "--", "-p", str(port)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the MCP server and AI dashboard frontend together."
    )
    parser.add_argument("--mcp-host", default=os.getenv("MCP_SERVER_HOST", "127.0.0.1"))
    parser.add_argument("--mcp-port", type=int, default=int(os.getenv("MCP_SERVER_PORT", "8000")))
    parser.add_argument("--mcp-transport", default="streamable-http")
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=int(os.getenv("FRONTEND_PORT", str(DEFAULT_FRONTEND_PORT))),
        help="Port for the frontend dev server (default: 3001).",
    )
    parser.add_argument("--no-wait", action="store_true", help="Do not wait for MCP readiness.")
    parser.add_argument(
        "--frontend-cmd",
        default=os.getenv("FRONTEND_CMD"),
        help='Override the frontend command (e.g. "npm run dev").',
    )
    args = parser.parse_args()

    if not FRONTEND_DIR.exists():
        print(f"[error] frontend directory not found: {FRONTEND_DIR}")
        return 2

    mcp_port = args.mcp_port
    if _is_port_in_use(args.mcp_host, mcp_port):
        fallback_port = _find_free_port(args.mcp_host, mcp_port + 1)
        if fallback_port is None:
            print(f"[error] MCP port {mcp_port} is in use and no free port found.")
            return 1
        print(f"[warn] MCP port {mcp_port} is in use; switching to {fallback_port}.")
        mcp_port = fallback_port

    frontend_port = args.frontend_port
    if args.frontend_cmd is None and _is_port_in_use("127.0.0.1", frontend_port):
        fallback_port = _find_free_port("127.0.0.1", frontend_port + 1)
        if fallback_port is None:
            print(f"[error] frontend port {frontend_port} is in use and no free port found.")
            return 1
        print(f"[warn] frontend port {frontend_port} is in use; switching to {fallback_port}.")
        frontend_port = fallback_port

    frontend_cmd = _build_frontend_command(args.frontend_cmd, frontend_port)
    if not frontend_cmd:
        print(
            "[error] npm not found in PATH. Install Node.js or set FRONTEND_CMD/--frontend-cmd."
        )
        return 127

    mcp_url = f"http://{args.mcp_host}:{mcp_port}/mcp"
    mcp_env = os.environ.copy()
    mcp_cmd = [
        sys.executable,
        "-m",
        "operations_dashboard.mcp_server",
        args.mcp_transport,
        "--host",
        args.mcp_host,
        "--port",
        str(mcp_port),
    ]
    mcp_proc = _start_process("mcp", mcp_cmd, ROOT, mcp_env)

    if not args.no_wait:
        ready = _wait_for_port(args.mcp_host, mcp_port, timeout=15)
        if not ready:
            print("[warn] MCP server did not become ready in time; continuing.")

    frontend_env = _build_frontend_env(mcp_url, force_mcp_url=True)
    frontend_proc = _start_process("frontend", frontend_cmd, FRONTEND_DIR, frontend_env)

    exit_code = 0
    try:
        while True:
            mcp_code = mcp_proc.poll()
            frontend_code = frontend_proc.poll()
            if mcp_code is not None or frontend_code is not None:
                exit_code = frontend_code if frontend_code is not None else mcp_code
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        exit_code = 130
    finally:
        _terminate_process("frontend", frontend_proc)
        _terminate_process("mcp", mcp_proc)

    return exit_code if exit_code is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
