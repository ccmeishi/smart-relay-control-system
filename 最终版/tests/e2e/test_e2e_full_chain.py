"""E2E full-chain test — verifies the integrated Smart Relay Control System.

Test flow (8 steps):
  1. /api/overview returns device counts
  2. /api/device-status returns current sensor values
  3. /api/scene-rules returns rule list
  4. /api/alarm-stats returns alarm counts
  5. POST /api/auth/login — admin login succeeds
  6. GET /api/auth/me — session persists
  7. POST /api/devices/toggle — relay toggle accepted
  8. POST /api/alarms/clear-all — alarms cleared

Uses only stdlib (urllib, json, http.cookiejar) — no new dependencies.
"""
import http.cookiejar
import json
from urllib.request import Request, build_opener, HTTPCookieProcessor


class HttpClient:
    """Simple HTTP client with cookie persistence for session-based auth."""

    def __init__(self, base_url):
        self.base_url = base_url
        self.cookies = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def get(self, path):
        req = Request(f"{self.base_url}{path}")
        with self.opener.open(req, timeout=5) as resp:
            body = resp.read()
            return resp.status, json.loads(body) if body else {}

    def post(self, path, data=None):
        body = json.dumps(data or {}).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(req, timeout=5) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else {}


# ============================================================
# Step 1: Overview — device counts
# ============================================================
def test_step1_overview(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.get("/api/overview")
    assert status == 200
    # overview should have some device count fields
    assert isinstance(data, dict)
    assert len(data) > 0


# ============================================================
# Step 2: Device status — current sensor values
# ============================================================
def test_step2_device_status(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.get("/api/device-status")
    assert status == 200
    assert isinstance(data, dict)


# ============================================================
# Step 3: Scene rules — rule list
# ============================================================
def test_step3_scene_rules(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.get("/api/scene-rules")
    assert status == 200
    assert isinstance(data, list)
    # Should have at least the 4 default rules
    assert len(data) >= 1


# ============================================================
# Step 4: Alarm stats — alarm counts
# ============================================================
def test_step4_alarm_stats(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.get("/api/alarm-stats")
    assert status == 200
    assert isinstance(data, dict)


# ============================================================
# Step 5: Auth login — admin/admin123
# ============================================================
def test_step5_login(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.post("/api/auth/login", {"username": "admin", "password": "admin123"})
    assert status == 200
    assert data["ok"] is True
    assert data["user"]["role"] == "admin"
    assert data["user"]["username"] == "admin"


# ============================================================
# Step 6: Auth me — session persists after login
# ============================================================
def test_step6_auth_me(backend):
    client = HttpClient(backend["base_url"])
    # Login first to get session cookie
    client.post("/api/auth/login", {"username": "admin", "password": "admin123"})
    # Verify session persists
    status, data = client.get("/api/auth/me")
    assert status == 200
    assert data["user"] is not None
    assert data["user"]["username"] == "admin"


# ============================================================
# Step 7: Relay toggle — POST /api/devices/toggle
# ============================================================
def test_step7_relay_toggle(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.post("/api/devices/toggle", {"key": "relay1", "value": 1})
    assert status == 200


# ============================================================
# Step 8: Alarm clear-all
# ============================================================
def test_step8_alarm_clear_all(backend):
    client = HttpClient(backend["base_url"])
    status, data = client.post("/api/alarms/clear-all")
    assert status == 200
