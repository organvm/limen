#!/usr/bin/env python3
"""Hermetic regression for local probe server ownership and cleanup."""

from __future__ import annotations

import errno
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CASES = (
    ("runtime", "probe-local-runtime.sh", "LIMEN_PROBE_PORT"),
    ("worker", "probe-local-worker.sh", "LIMEN_WORKER_PROBE_PORT"),
)


def wait_for(predicate: Callable[[], bool], *, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def unused_port(excluded: set[int]) -> int:
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        if port not in excluded:
            excluded.add(port)
            return port


def port_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            return True
    except OSError:
        return False


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except OSError as exc:
        return exc.errno == errno.EPERM
    return True


def terminate_process_group(pgid: int) -> None:
    """Best-effort cleanup that cannot target the test runner's process group."""
    if pgid == os.getpgrp() or not process_group_exists(pgid):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    if wait_for(lambda: not process_group_exists(pgid), timeout=2.0):
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return
    wait_for(lambda: not process_group_exists(pgid), timeout=2.0)


def write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def prepare_fixture(fixture: Path) -> None:
    scripts = fixture / "scripts"
    worker_bin = fixture / "web/worker/node_modules/.bin"
    scripts.mkdir(parents=True)
    (fixture / "web/api").mkdir(parents=True)
    worker_bin.mkdir(parents=True)
    (fixture / "web/worker/node_modules/yaml").mkdir(parents=True)

    for _, script_name, _ in CASES:
        shutil.copy2(ROOT / "scripts" / script_name, scripts / script_name)

    fake_server = fixture / "fake-server.py"
    write_executable(
        fake_server,
        """#!/usr/bin/env python3
import os
import signal
import socket
import sys
from pathlib import Path

port = int(sys.argv[sys.argv.index("--port") + 1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("127.0.0.1", port))
sock.listen()
sock.settimeout(0.2)
Path(os.environ["PROBE_TEST_PID_FILE"]).write_text(f"{os.getpid()} {os.getppid()}\\n")

def stop(_signum, _frame):
    sock.close()
    raise SystemExit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
while True:
    try:
        connection, _ = sock.accept()
    except TimeoutError:
        continue
    connection.close()
""",
    )

    write_executable(
        scripts / "probe-runtime-adapter.py",
        """#!/usr/bin/env python3
import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

if not Path(os.environ["PROBE_TEST_RELEASE_FILE"]).exists():
    raise SystemExit(1)
url = sys.argv[sys.argv.index("--api-url") + 1]
parsed = urlparse(url)
try:
    with socket.create_connection((parsed.hostname, parsed.port), timeout=0.2):
        pass
except OSError:
    raise SystemExit(1)
print("hermetic adapter probe passed")
""",
    )

    write_executable(
        worker_bin / "wrangler",
        """#!/usr/bin/env bash
set -euo pipefail
exec "$REAL_PYTHON" "$FAKE_SERVER" "$@"
""",
    )

    fake_bin = fixture / "bin"
    fake_bin.mkdir()
    write_executable(
        fake_bin / "python3",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-m" && "${2:-}" == "uvicorn" ]]; then
  shift 2
  exec "$REAL_PYTHON" "$FAKE_SERVER" "$@"
fi
exec "$REAL_PYTHON" "$@"
""",
    )


def run_case(fixture: Path, name: str, script_name: str, port_variable: str, port: int) -> None:
    pid_file = fixture / f"{name}.pid"
    release_file = fixture / f"{name}.release"
    temp_dir = fixture / f"{name}-tmp"
    temp_dir.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "FAKE_SERVER": str(fixture / "fake-server.py"),
            "PATH": f"{fixture / 'bin'}:{env['PATH']}",
            "PROBE_TEST_PID_FILE": str(pid_file),
            "PROBE_TEST_RELEASE_FILE": str(release_file),
            "REAL_PYTHON": sys.executable,
            "TMPDIR": str(temp_dir),
            port_variable: str(port),
        }
    )
    process = subprocess.Popen(
        ["bash", str(fixture / "scripts" / script_name)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    output = ""
    try:
        if not wait_for(lambda: pid_file.exists() and port_listening(port)):
            output = process.communicate(timeout=1)[0]
            raise AssertionError(f"{name}: fake server did not become ready\n{output}")

        server_pid, server_parent = (int(value) for value in pid_file.read_text().split())
        assert server_parent == process.pid, (
            f"{name}: listener pid {server_pid} is owned by wrapper pid {server_parent}, not probe pid {process.pid}"
        )

        release_file.touch()
        output = process.communicate(timeout=10)[0]
        assert process.returncode == 0, f"{name}: probe failed with {process.returncode}\n{output}"
        assert wait_for(lambda: not process_exists(server_pid)), f"{name}: server pid {server_pid} survived success"
        assert wait_for(lambda: not port_listening(port)), f"{name}: port {port} still accepts connections"
        assert not process_group_exists(process.pid), f"{name}: probe process group {process.pid} survived success"
    finally:
        terminate_process_group(process.pid)
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def main() -> int:
    used_ports: set[int] = set()
    with tempfile.TemporaryDirectory(prefix="limen-probe-ownership-") as raw_fixture:
        fixture = Path(raw_fixture)
        prepare_fixture(fixture)
        for name, script_name, port_variable in CASES:
            port = unused_port(used_ports)
            run_case(fixture, name, script_name, port_variable, port)
            print(f"PASS {name}: successful probe reaped listener on {port}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
