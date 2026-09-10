"""E2E test fixtures — start the integrated backend with FakeBridge."""
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent / "backend"
APP_PY = BACKEND_DIR / "app.py"


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def backend():
    """Start integrated backend with DAY102_FORCE_FAKE=1 on a random port.

    yields dict: {base_url, port, proc, bridge_pid}

    bridge_pid is parsed from backend stdout (bridge_runner.py prints
    "[runner] 数据源已启动 pid=NNNN ..."). Used in teardown for precise kill
    as fallback when taskkill /T doesn't reach the bridge.
    """
    port = _free_port()
    env = os.environ.copy()
    env["DAY102_FORCE_FAKE"] = "1"
    env["PORT"] = str(port)
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        [sys.executable, "-u", str(APP_PY)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(BACKEND_DIR),
        env=env,
    )

    # ---- Read stdout in background thread, capture bridge PID ----
    # bridge_runner.py prints: "[runner] 数据源已启动 pid=12345 → fake_bridge.py"
    # NOTE: bridge_runner.watch() can restart the bridge after crash+5s, but
    # we only capture the INITIAL PID. If bridge restarts mid-test, this PID
    # is stale — but that's OK because the PRIMARY kill (taskkill /T) handles
    # any child of Flask regardless of PID. The captured PID is just a fast
    # precise fallback for the common case.
    bridge_pid = None
    pid_capture_event = threading.Event()

    def _stdout_reader():
        nonlocal bridge_pid
        if not proc.stdout:
            return
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            m = re.search(r"pid=(\d+)", line)
            if m:
                bridge_pid = int(m.group(1))
                pid_capture_event.set()
                # Keep reading but stop looking for PID (it appears once)
                break
        # Drain remaining so pipe buffer doesn't fill up and block Flask
        try:
            for _ in proc.stdout:
                pass
        except Exception:
            pass

    reader = threading.Thread(target=_stdout_reader, daemon=True)
    reader.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    ready = False

    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.fail("Backend exited early; check logs/ for details")
        try:
            req = Request(f"{base_url}/api/overview")
            with urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.5)

    if not ready:
        proc.terminate()
        pytest.fail("Backend failed to start within 30s")

    # Wait for bridge PID line to be captured (or timeout 5s)
    pid_capture_event.wait(timeout=5)

    # Give FakeBridge a few seconds to start writing data
    time.sleep(3)

    fixture = {"base_url": base_url, "port": port, "proc": proc, "bridge_pid": bridge_pid}
    if bridge_pid:
        print(f"[e2e] Captured bridge PID: {bridge_pid}")

    yield fixture

    # ---- Teardown: precise kill sequence ----
    # Primary: kill the ENTIRE Flask process tree with /T
    # Fallback: kill bridge directly by captured PID (handles edge cases where
    # /T somehow misses — e.g. if bridge was restarted by watch thread after /T)
    if sys.platform == "win32":
        # Primary kill: Flask + all children via /T
        subprocess.run(
            ["taskkill", "/pid", str(proc.pid), "/T", "/F"],
            capture_output=True, timeout=10,
        )
        # Precise fallback: kill bridge PID we captured
        if bridge_pid:
            subprocess.run(
                ["taskkill", "/pid", str(bridge_pid), "/F"],
                capture_output=True, timeout=5,
            )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
