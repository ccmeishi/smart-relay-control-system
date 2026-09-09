"""Day9 SQLite 数据层 - 设备映射 / 用户角色 / 登录会话 / 设备状态缓存

数据库文件: db/iot_platform.db
四张核心表:
  device_mappings  - 实体设备 key → 虚拟产品/设备/属性 的映射关系 (替代 Day8 硬编码 UP_ROUTING)
  users            - 用户账号 + 角色 (admin / user)
  login_sessions   - 用户登录会话 (在线/离线追踪, 心跳时间)
  device_status    - 实物设备最新状态缓存 (继电器/传感器值, 由 Bridge 上报时同步写入)

init_db.py 在首次运行时自动建表 + 预填充 Day8 的 8 条路由 + 默认 admin 用户.
"""
import sqlite3
import os
import re
import hashlib
from contextlib import contextmanager

# --- 输入白名单正则 ---
_RE_KEY = re.compile(r'^[a-z0-9_]{1,40}$')      # gateway_key: relay1 / temperature
_RE_ID  = re.compile(r'^[a-z0-9-]{1,40}$')       # product_id / device_id: lock-cc / lock001
_RE_PROP = re.compile(r'^[a-z0-9_]{1,40}$')      # property_name: switch / temperature
_RE_DESC = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff ]{0,100}$')  # description: 允许中文
_RE_USER = re.compile(r'^[a-zA-Z0-9_]{3,20}$')    # username
_RE_PASS = re.compile(r'^[\x20-\x7e]{6,64}$')     # password (可打印 ASCII)
_RE_NAME = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]{0,30}$')    # display_name

def _validate(field, value, pattern, label):
    """统一校验入口: 不通过抛 ValueError"""
    if value is None or value == "":
        raise ValueError(f"{label} 不能为空")
    if not pattern.match(str(value)):
        raise ValueError(f"{label} 格式不合法: 仅允许 {pattern.pattern}")
    return str(value)

def _validate_mapping_fields(gateway_key, product_id, device_id, property_name, description=""):
    return (
        _validate("gateway_key", gateway_key, _RE_KEY, "Gateway Key"),
        _validate("product_id", product_id, _RE_ID, "Product ID"),
        _validate("device_id", device_id, _RE_ID, "Device ID"),
        _validate("property_name", property_name, _RE_PROP, "Property Name"),
        _validate("description", description or "", _RE_DESC, "Description"),
    )

# 数据库文件路径: day9/db/iot_platform.db
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
DB_PATH = os.path.join(DB_DIR, "iot_platform.db")

# 确保 db 目录存在
os.makedirs(DB_DIR, exist_ok=True)


# ============================================================
# 基础工具
# ============================================================
@contextmanager
def get_conn():
    """上下文管理器: 自动提交 + 关闭"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def hash_password(pwd: str) -> str:
    """简单 SHA-256 哈希 (开发阶段够用)"""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


# ============================================================
# 初始化 (首次运行建表 + 预填充)
# ============================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS device_mappings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_key TEXT NOT NULL UNIQUE,      -- 网关侧 key: relay1, temperature, human...
    product_id  TEXT NOT NULL,             -- 虚拟产品: lock-cc, sensor-cc...
    device_id   TEXT NOT NULL,             -- 虚拟设备: lock001, sensorcc...
    property_name TEXT NOT NULL,           -- 虚拟属性: switch, temperature...
    description TEXT DEFAULT '',           -- 备注
    enabled     INTEGER DEFAULT 1,         -- 是否启用 (1=启用)
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role         TEXT NOT NULL DEFAULT 'user',  -- 'admin' 或 'user'
    display_name TEXT DEFAULT '',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mappings_gateway_key ON device_mappings(gateway_key);
CREATE INDEX IF NOT EXISTS idx_mappings_product_device ON device_mappings(product_id, device_id);

CREATE TABLE IF NOT EXISTS login_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    username   TEXT NOT NULL,
    ip         TEXT DEFAULT '',
    login_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    logout_at  TIMESTAMP,
    last_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 心跳时间, 用于判断在线/离线
    status     TEXT DEFAULT 'online'                 -- online / offline
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON login_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON login_sessions(status);

CREATE TABLE IF NOT EXISTS device_status (
    gateway_key TEXT PRIMARY KEY,                   -- relay1 / temperature ...
    value       TEXT,                                -- 字符串存储, 展示时按类型解析
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_status_updated ON device_status(updated_at);
"""


# Day8 硬编码的 8 条路由 → SQLite 预填充数据
DEFAULT_MAPPINGS = [
    # gateway_key, product_id, device_id, property_name, description
    ("relay1",      "lock-cc",    "lock001",   "switch",      "门锁继电器"),
    ("relay2",      "light-cc",   "light001",  "switch",      "灯1继电器"),
    ("relay3",      "light-cc",   "light002",  "switch",      "灯2继电器"),
    ("relay4",      "ac-cc",      "ac001",     "switch",      "空调继电器"),
    ("temperature", "sensor-cc",  "sensorcc",  "temperature", "温度传感器(只读)"),
    ("humidity",    "sensor-cc",  "sensorcc",  "humidity",    "湿度传感器(只读)"),
    ("human",       "human-cc",   "human001",  "detected",    "人体感应(0无人/1有人)"),
    ("smoke",       "smoke-cc",   "smoke001",  "level",       "烟雾浓度(0-100)"),
]

DEFAULT_USERS = [
    # username, password, role, display_name
    ("admin", "admin123", "admin", "管理员"),
    ("user",  "user123",  "user",  "普通用户"),
]


def init_db(force: bool = False) -> None:
    """建表 + 预填充. force=True 则先删库重建."""
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"  [init_db] 已删除旧库")

    with get_conn() as conn:
        conn.executescript(SCHEMA_SQL)

        # 预填充路由 (INSERT OR IGNORE 避免重复)
        conn.executemany(
            """INSERT OR IGNORE INTO device_mappings
               (gateway_key, product_id, device_id, property_name, description)
               VALUES (?, ?, ?, ?, ?)""",
            DEFAULT_MAPPINGS,
        )

        # 预填充用户
        conn.executemany(
            """INSERT OR IGNORE INTO users (username, password_hash, role, display_name)
               VALUES (?, ?, ?, ?)""",
            [(u, hash_password(p), r, n) for u, p, r, n in DEFAULT_USERS],
        )

    print(f"  [init_db] 数据库就绪: {DB_PATH}")


# ============================================================
# 设备映射 CRUD (Bridge + Web 共用)
# ============================================================
def load_routing() -> dict:
    """从 SQLite 加载路由表 → {gateway_key: {product, device, property}}"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT gateway_key, product_id, device_id, property_name FROM device_mappings WHERE enabled=1"
        ).fetchall()
    return {
        r["gateway_key"]: {
            "product": r["product_id"],
            "device": r["device_id"],
            "property": r["property_name"],
        }
        for r in rows
    }


def load_all_mappings() -> list:
    """Web 管理页用: 返回所有映射(含禁用)"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM device_mappings ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def add_mapping(gateway_key, product_id, device_id, property_name, description=""):
    gateway_key, product_id, device_id, property_name, description = _validate_mapping_fields(
        gateway_key, product_id, device_id, property_name, description
    )
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO device_mappings
               (gateway_key, product_id, device_id, property_name, description)
               VALUES (?, ?, ?, ?, ?)""",
            (gateway_key, product_id, device_id, property_name, description),
        )


def update_mapping(mapping_id, gateway_key=None, product_id=None,
                  device_id=None, property_name=None, description=None, enabled=None):
    # 对每个提供的字段做校验
    if gateway_key is not None:
        _validate("gateway_key", gateway_key, _RE_KEY, "Gateway Key")
    if product_id is not None:
        _validate("product_id", product_id, _RE_ID, "Product ID")
    if device_id is not None:
        _validate("device_id", device_id, _RE_ID, "Device ID")
    if property_name is not None:
        _validate("property_name", property_name, _RE_PROP, "Property Name")
    if description is not None:
        _validate("description", description or "", _RE_DESC, "Description")
    fields = []
    values = []
    if gateway_key is not None:
        fields.append("gateway_key=?"); values.append(gateway_key)
    if product_id is not None:
        fields.append("product_id=?"); values.append(product_id)
    if device_id is not None:
        fields.append("device_id=?"); values.append(device_id)
    if property_name is not None:
        fields.append("property_name=?"); values.append(property_name)
    if description is not None:
        fields.append("description=?"); values.append(description)
    if enabled is not None:
        fields.append("enabled=?"); values.append(1 if enabled else 0)
    fields.append("updated_at=CURRENT_TIMESTAMP")
    values.append(mapping_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE device_mappings SET {','.join(fields)} WHERE id=?",
            values,
        )


def delete_mapping(mapping_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM device_mappings WHERE id=?", (mapping_id,))


# ============================================================
# 用户 CRUD (Web 用)
# ============================================================
def authenticate(username, password) -> dict | None:
    """验证登录. 返回 user dict 或 None"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND password_hash=?",
            (username, hash_password(password)),
        ).fetchone()
    return dict(row) if row else None


def list_users() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, username, role, display_name, created_at FROM users ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def add_user(username, password, role="user", display_name=""):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, display_name),
        )


def update_user_role(user_id, role):
    with get_conn() as conn:
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))


def delete_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))


def reset_password(user_id, new_password):
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), user_id),
        )


# ============================================================
# 登录会话 (在线/离线追踪)
# ============================================================
def start_session(user_id, username, ip=""):
    """登录时调用. 返回 session_id"""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO login_sessions (user_id, username, ip, status) VALUES (?, ?, ?, 'online')",
            (user_id, username, ip),
        )
        return cur.lastrowid


def end_session(session_id):
    """登出时调用. 标记为 offline"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE login_sessions SET status='offline', logout_at=CURRENT_TIMESTAMP WHERE id=?",
            (session_id,),
        )


def touch_session(session_id):
    """心跳: 更新 last_seen 时间戳, 每次请求时调用"""
    if not session_id:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE login_sessions SET last_seen=CURRENT_TIMESTAMP WHERE id=?",
            (session_id,),
        )


def list_online_users():
    """返回在线用户列表 (status='online' 且 last_seen 在 5 分钟内)"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, user_id, username, ip, login_at, last_seen, status
               FROM login_sessions
               WHERE status='online'
                 AND last_seen > datetime('now', '-5 minutes')
               ORDER BY last_seen DESC"""
        ).fetchall()
    # 顺便清理超时 session 的 status (防止永远 online)
    conn2 = sqlite3.connect(DB_PATH)
    conn2.execute(
        "UPDATE login_sessions SET status='offline' WHERE status='online' AND last_seen <= datetime('now', '-5 minutes')"
    )
    conn2.commit()
    conn2.close()
    return [dict(r) for r in rows]


def list_recent_sessions(limit=20):
    """最近登录记录 (含已离线), 用于历史表"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT s.id, s.user_id, s.username, s.ip, s.login_at, s.logout_at,
                      s.last_seen, s.status, u.display_name
               FROM login_sessions s
               LEFT JOIN users u ON s.user_id = u.id
               ORDER BY s.login_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_online_count():
    """当前在线用户数 (status='online' 且 last_seen 在 5 分钟内)"""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as c FROM login_sessions
               WHERE status='online' AND last_seen > datetime('now', '-5 minutes')"""
        ).fetchone()
    return row["c"] if row else 0


# ============================================================
# 设备状态缓存 (实物最新值)
# ============================================================
def update_device_status(gateway_key, value):
    """Bridge 收到网关上报时调用, 更新实物状态缓存"""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO device_status (gateway_key, value, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(gateway_key) DO UPDATE SET
                 value=excluded.value,
                 updated_at=CURRENT_TIMESTAMP""",
            (gateway_key, str(value)),
        )


def get_device_status(gateway_key):
    """获取单个采集点最新值"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT gateway_key, value, updated_at FROM device_status WHERE gateway_key=?",
            (gateway_key,),
        ).fetchone()
    return dict(row) if row else None


def get_device_status_all():
    """获取所有采集点最新值 → {gateway_key: {value, updated_at}}"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT gateway_key, value, updated_at FROM device_status"
        ).fetchall()
    return {r["gateway_key"]: {"value": r["value"], "updated_at": r["updated_at"]} for r in rows}


# ============================================================
# 快速自检: python db.py  会建库 + 打印当前路由
# ============================================================
if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    init_db(force=force)
    print("\n当前路由表:")
    for k, v in load_routing().items():
        print(f"  {k:15s} → {v['product']:12s}/{v['device']:10s} ({v['property']})")
    print("\n当前用户:")
    for u in list_users():
        print(f"  {u['username']:10s} role={u['role']:6s} display={u['display_name']}")
    print(f"\n在线用户: {get_online_count()}")
    print("\n设备状态缓存:")
    for k, v in get_device_status_all().items():
        print(f"  {k:15s} = {v['value']:10s} ({v['updated_at']})")
