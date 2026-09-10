"""E2E test fixtures — start the integrated backend with FakeBridge."""
import os
import socket
import subprocess
import sys
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

    yields dict: {base_url, port, proc}
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

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    ready = False

    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", errors="replace") if proc.stdout else ""
            pytest.fail(f"Backend exited early:\n{out}")
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
        try:
            out, _ = proc.communicate(timeout=3)
            print("Backend output:", out.decode("utf-8", errors="replace"))
        except Exception:
            pass
        pytest.fail("Backend failed to start within 30s")

    # Give FakeBridge a few seconds to start writing data
    time.sleep(3)

    yield {"base_url": base_url, "port": port, "proc": proc}

    # ---- Teardown: kill the entire process tree (Flask + bridge subprocess) ----
    # On Windows, proc.terminate() only kills Flask; bridge_runner.start() spawns
    # fake_bridge.py as a subprocess that becomes orphan and holds SQLite WAL lock.
    # Use taskkill /T /F to kill the whole tree by PID.
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/pid", str(proc.pid), "/T", "/F"],
            capture_output=True, timeout=10,
        )
    else:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    # Also sweep any orphan fake_bridge / gateway_bridge processes
    # that might have survived (e.g. from a prior crashed run)
    try:
        import re
        result = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            if "python.exe" in line and (
                "fake_bridge" in line or "gateway_bridge" in line
            ):
                m = re.search(r',(\d+)$', line)
                if m:
                    pid = m.group(1)
                    subprocess.run(
                        ["taskkill", "/pid", pid, "/F"],
                        capture_output=True, timeout=5,
                    )
    except Exception:
        pass
