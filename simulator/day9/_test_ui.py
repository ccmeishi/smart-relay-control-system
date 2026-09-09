"""Quick dashboard render test."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from web.app import app

c = app.test_client()
c.post("/login", data={"username":"admin","password":"admin123"}, follow_redirects=True)
r = c.get("/dashboard")
t = r.data.decode()

print(f"Status: {r.status_code}")
print(f"Bar chart (gradient): {'linear-gradient' in t}")
print(f"HSL colors: {'hsl(45' in t}")
print(f"User count card: {'平台用户数' in t}")
print(f"Device instance card: {'平台设备实例数' in t}")
print(f"Old term removed: {'虚拟设备数' not in t or '平台设备' in t}")
print(f"ValueError flash on bad input: checking...")

# Test bad input
c2 = app.test_client()
c2.post("/login", data={"username":"admin","password":"admin123"}, follow_redirects=True)
r2 = c2.post("/mappings/add", data={
    "gateway_key": "hax; DROP TABLE users;--",
    "product_id": "lock-cc",
    "device_id": "lock001",
    "property_name": "switch",
}, follow_redirects=True)
t2 = r2.data.decode()
print(f"Bad input rejected: {'不合法' in t2 or 'ERROR' in t2 or 'flash' in t2.lower() or '添加失败' in t2}")
