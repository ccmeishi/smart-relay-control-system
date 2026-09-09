"""Day10 SQLite 数据层 - 设备映射 / 用户角色 / 登录会话 / 设备状态 / 场景规则 / 告警记录

Day9 基础上新增两张表:
  scene_rules    - 场景联动规则 (IF 采集点满足条件 THEN 执行动作)
  alarm_records  - 告警历史 (active/acknowledged/cleared 三态)

数据库文件: db/iot_platform.db
六张核心表:
  device_mappings  - 实体设备 key → 虚拟产品/设备/属性 的映射关系 (替代 Day8 硬编码 UP_ROUTING)
  users            - 用户账号 + 角色 (admin / user)
  login_sessions   - 用户登录会话 (在线/离线追踪, 心跳时间)
  device_status    - 实物设备最新状态缓存 (继电器/传感器值, 由 Bridge 上报时同步写入)
  scene_rules      - 场景联动规则 (温度过高→全关继电器, 有人→开灯...)
  alarm_records    - 告警记录 (规则触发或手动产生, 三态流转)

init_db() 在首次运行时自动建表 + 预填充 Day8 的 8 条路由 + 默认 admin 用户 + 4 条示例场景规则.
"""
import sqlite3
import os
import re
import hashlib
import time
from contextlib import contextmanager

# --- 输入白名单正则 ---
_RE_KEY = re.compile(r'^[a-z0-9_]{1,40}$')      # gateway_key: relay1 / temperature
_RE_ID  = re.compile(r'^[a-z0-9-]{1,40}$')       # product_id / device_id: lock-cc / lock001
_RE_PROP = re.compile(r'^[a-z0-9_]{1,40}$')      # property_name: switch / temperature
_RE_DESC = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff ]{0,100}$')  # description: 允许中文
_RE_USER = re.compile(r'^[a-zA-Z0-9_]{3,20}$')    # username
_RE_PASS = re.compile(r'^[\x20-\x7e]{6,64}$')     # password (可打印 ASCII)
_RE_NAME = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff]{0,30}$')    # display_name
_RE_RULE_NAME = re.compile(r'^[a-zA-Z0-9_\-\u4e00-\u9fff ]{1,50}$')  # 规则名称
_RE_OP = re.compile(r'^(>|<|>=|<=|==|!=)$')       # 运算符
_RE_LEVEL = re.compile(r'^(info|warning|critical)$')  # 告警级别
_RE_ACTION = re.compile(r'^(set_relay|all_relay_off|all_relay_on|send_alarm)$')  # 动作类型

VALID_OPERATORS = (">", "<", ">=", "<=", "==", "!=")
VALID_LEVELS = ("info", "warning", "critical")
VALID_ACTIONS = ("set_relay", "all_relay_off", "all_relay_on", "send_alarm")
VALID_ALARM_STATUS = ("active", "acknowledged", "cleared")

# 动作类型的中文描述 (供模板展示)
ACTION_LABELS = {
    "set_relay":     "设置继电器",
    "all_relay_off": "全关继电器",
    "all_relay_on":  "全开继电器",
    "send_alarm":    "产生告警",
}

LEVEL_LABELS = {
    "info":     "提示",
    "warning":  "警告",
    "critical": "严重",
}

LEVEL_COLORS = {
    "info":     "#3b82f6",
    "warning":  "#f59e0b",
    "critical": "#ef4444",
}


def _validate(field, value, pattern, label):
    """统一校验入口: 不通过抛 ValueError"""
    if value is None or value == "":
        raise ValueError(f"{label} 不能为空")
    if not pattern.match(str(value)):
        raise ValueError(f"{label} 格式不合法: 仅允许 {pattern.pattern}")
    return str(value)


def _validate_mapping_fields(gateway_key, product_id, device_id, property_name, description=""):
    gateway_key = _validate("gateway_key", gateway_key, _RE_KEY, "Gateway Key")
    product_id = _validate("product_id", product_id, _RE_ID, "Product ID")
    device_id = _validate("device_id", device_id, _RE_ID, "Device ID")
    property_name = _validate("property_name", property_name, _RE_PROP, "Property Name")
    if description:  # description 可选: 空字符串合法, 非空才校验格式
        description = _validate("description", description, _RE_DESC, "Description")
    return gateway_key, product_id, device_id, property_name, description


# 数据库文件路径: day10/db/iot_platform.db
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")
DB_PATH = os.path.join(DB_DIR, "iot_platform.db")

# ESP32 网关配置文件路径 (MQTT/WiFi/采集点都在这里统一配置)
GATEWAY_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "esp32_firmware", "config.json"
)

# 确保 db 目录存在
os.makedirs(DB_DIR, exist_ok=True)


def load_gateway_config():
    """统一从 esp32_firmware/config.json 读取 MQTT + WiFi + 网关凭据.

    返回 dict: {
        mqtt_host, mqtt_port, mqtt_user, mqtt_pass,
        product_id, device_id, wifi_ssid, wifi_pass
    }
    """
    import json
    with open(GATEWAY_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return {
        "mqtt_host": cfg.get("mqtt_host", "localhost"),
        "mqtt_port": int(cfg.get("mqtt_port", 1883)),
        "mqtt_user": cfg.get("mqtt_user", ""),
        "mqtt_pass": cfg.get("mqtt_pass", ""),
        "product_id": cfg.get("product_id", ""),
        "device_id": cfg.get("device_id", ""),
        "wifi_ssid": cfg.get("wifi_ssid", ""),
        "wifi_pass": cfg.get("wifi_pass", ""),
    }


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

-- ===== Day10 新增: 场景联动规则表 =====
CREATE TABLE IF NOT EXISTS scene_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,                   -- 规则名称 (如 "高温自动断电")
    description     TEXT DEFAULT '',                 -- 规则描述
    trigger_key     TEXT NOT NULL,                   -- 触发采集点: temperature / human / smoke...
    trigger_operator TEXT NOT NULL,                  -- 运算符: > < >= <= == !=
    trigger_value   TEXT NOT NULL,                  -- 阈值 (字符串存储, 比较时转 float)
    action_type     TEXT NOT NULL,                   -- 动作类型: set_relay / all_relay_off / all_relay_on / send_alarm
    action_target   TEXT DEFAULT '',                 -- 动作目标: set_relay 时为 relay1/relay2...
    action_value    TEXT DEFAULT '',                  -- 动作值: set_relay 时为 0/1
    alarm_level     TEXT DEFAULT 'warning',           -- 触发时产生的告警级别: info/warning/critical
    enabled         INTEGER DEFAULT 1,               -- 是否启用
    cooldown_sec    INTEGER DEFAULT 60,              -- 冷却时间(秒), 避免频繁触发
    last_triggered  TIMESTAMP,                       -- 上次触发时间 (NULL=未触发过)
    trigger_count   INTEGER DEFAULT 0,               -- 累计触发次数
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rules_trigger_key ON scene_rules(trigger_key);
CREATE INDEX IF NOT EXISTS idx_rules_enabled ON scene_rules(enabled);

-- ===== Day10 新增: 告警记录表 =====
CREATE TABLE IF NOT EXISTS alarm_records (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id         INTEGER,                         -- 关联的规则 ID (NULL=手动产生)
    rule_name       TEXT DEFAULT '',                 -- 规则名称快照 (规则可能被删, 保留历史)
    source_key      TEXT DEFAULT '',                 -- 触发的采集点 (如 temperature)
    source_value    TEXT DEFAULT '',                 -- 触发时的值
    level           TEXT NOT NULL DEFAULT 'warning', -- info / warning / critical
    message         TEXT DEFAULT '',                 -- 告警描述 (人类可读)
    status          TEXT DEFAULT 'active',           -- active / acknowledged / cleared
    triggered_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged_at TIMESTAMP,                       -- 确认时间
    acknowledged_by TEXT DEFAULT ''                  -- 确认人 username
);

CREATE INDEX IF NOT EXISTS idx_alarms_status ON alarm_records(status);
CREATE INDEX IF NOT EXISTS idx_alarms_level ON alarm_records(level);
CREATE INDEX IF NOT EXISTS idx_alarms_triggered ON alarm_records(triggered_at);
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

# Day10 示例场景规则 (4 条, 覆盖典型联动场景)
DEFAULT_SCENE_RULES = [
    # name, description, trigger_key, operator, value, action_type, target, action_value, alarm_level, cooldown_sec
    ("高温自动断电",   "温度超过 35C 时, 全部继电器断电保护",
     "temperature", ">", "35", "all_relay_off", "", "", "critical", 60),
    ("烟雾告警联动",   "烟雾浓度超过 50 时, 全部继电器断电 + 严重告警",
     "smoke", ">", "50", "all_relay_off", "", "", "critical", 30),
    ("有人自动开灯",   "人体感应检测到有人时, 自动打开灯1继电器",
     "human", "==", "1", "set_relay", "relay2", "1", "info", 10),
    ("无人自动关灯",   "人体感应无人时, 自动关闭灯1继电器 (节能)",
     "human", "==", "0", "set_relay", "relay2", "0", "info", 10),
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

        # 预填充示例场景规则 (Day10 新增)
        # scene_rules 表无 UNIQUE 约束 (允许同名规则), 用 COUNT 判断是否已填充
        rule_count = conn.execute("SELECT COUNT(*) as c FROM scene_rules").fetchone()
        if rule_count and rule_count["c"] == 0:
            conn.executemany(
                """INSERT INTO scene_rules
                   (name, description, trigger_key, trigger_operator, trigger_value,
                    action_type, action_target, action_value, alarm_level, cooldown_sec)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                DEFAULT_SCENE_RULES,
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
    if gateway_key is not None:
        _validate("gateway_key", gateway_key, _RE_KEY, "Gateway Key")
    if product_id is not None:
        _validate("product_id", product_id, _RE_ID, "Product ID")
    if device_id is not None:
        _validate("device_id", device_id, _RE_ID, "Device ID")
    if property_name is not None:
        _validate("property_name", property_name, _RE_PROP, "Property Name")
    if description:
        _validate("description", description, _RE_DESC, "Description")
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
    _validate("username", username, _RE_USER, "用户名")
    _validate("password", password, _RE_PASS, "密码")
    if display_name:
        _validate("display_name", display_name, _RE_NAME, "显示名")
    if role not in ("admin", "user"):
        raise ValueError(f"非法角色 '{role}', 只允许 'admin' 或 'user'")
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, display_name) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, display_name),
        )


def update_user_role(user_id, role):
    if role not in ("admin", "user"):
        raise ValueError(f"非法角色 '{role}', 只允许 'admin' 或 'user'")
    with get_conn() as conn:
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))


def delete_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))


def reset_password(user_id, new_password):
    _validate("password", new_password, _RE_PASS, "密码")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), user_id),
        )


# ============================================================
# 登录会话 (在线/离线追踪)
# ============================================================
def kick_user_sessions(user_id, keep_session_id=None):
    """同一用户新登录时, 把该用户所有旧的 online session 置为 offline."""
    with get_conn() as conn:
        if keep_session_id is not None:
            conn.execute(
                "UPDATE login_sessions SET status='offline', logout_at=CURRENT_TIMESTAMP "
                "WHERE user_id=? AND status='online' AND id!=?",
                (user_id, keep_session_id),
            )
        else:
            conn.execute(
                "UPDATE login_sessions SET status='offline', logout_at=CURRENT_TIMESTAMP "
                "WHERE user_id=? AND status='online'",
                (user_id,),
            )


def start_session(user_id, username, ip=""):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO login_sessions (user_id, username, ip, status) VALUES (?, ?, ?, 'online')",
            (user_id, username, ip),
        )
        return cur.lastrowid


def end_session(session_id):
    with get_conn() as conn:
        conn.execute(
            "UPDATE login_sessions SET status='offline', logout_at=CURRENT_TIMESTAMP WHERE id=?",
            (session_id,),
        )


def touch_session(session_id):
    if not session_id:
        return
    with get_conn() as conn:
        conn.execute(
            "UPDATE login_sessions SET last_seen=CURRENT_TIMESTAMP WHERE id=?",
            (session_id,),
        )


def list_online_users():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, user_id, username, ip, login_at, last_seen, status
               FROM login_sessions
               WHERE status='online'
                 AND last_seen > datetime('now', '-5 minutes')
               ORDER BY last_seen DESC"""
        ).fetchall()
    conn2 = sqlite3.connect(DB_PATH)
    conn2.execute(
        "UPDATE login_sessions SET status='offline' WHERE status='online' AND last_seen <= datetime('now', '-5 minutes')"
    )
    conn2.commit()
    conn2.close()
    return [dict(r) for r in rows]


def list_recent_sessions(limit=20):
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
    with get_conn() as conn:
        row = conn.execute(
            "SELECT gateway_key, value, updated_at FROM device_status WHERE gateway_key=?",
            (gateway_key,),
        ).fetchone()
    return dict(row) if row else None


def get_device_status_all():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT gateway_key, value, updated_at FROM device_status"
        ).fetchall()
    return {r["gateway_key"]: {"value": r["value"], "updated_at": r["updated_at"]} for r in rows}


# ============================================================
# Day10 新增: 场景规则 CRUD + 评估引擎
# ============================================================
def _compare(value, operator, threshold):
    """通用比较: 支持数值和字符串比较.
    运算符: > < >= <= == !=
    """
    try:
        v = float(value)
        t = float(threshold)
    except (ValueError, TypeError):
        v = str(value)
        t = str(threshold)
        if operator == "==":
            return v == t
        if operator == "!=":
            return v != t
        return False
    if operator == ">":  return v > t
    if operator == "<":  return v < t
    if operator == ">=": return v >= t
    if operator == "<=": return v <= t
    if operator == "==": return v == t
    if operator == "!=": return v != t
    return False


def _validate_rule_fields(name, trigger_key, trigger_operator, trigger_value,
                          action_type, action_target="", action_value="",
                          alarm_level="warning", cooldown_sec=60, description=""):
    """场景规则字段统一校验"""
    name = _validate("name", name, _RE_RULE_NAME, "规则名称")
    trigger_key = _validate("trigger_key", trigger_key, _RE_KEY, "触发采集点")
    if trigger_operator not in VALID_OPERATORS:
        raise ValueError(f"运算符不合法, 只允许 {VALID_OPERATORS}")
    if trigger_value is None or str(trigger_value).strip() == "":
        raise ValueError("阈值不能为空")
    trigger_value = str(trigger_value).strip()
    if action_type not in VALID_ACTIONS:
        raise ValueError(f"动作类型不合法, 只允许 {VALID_ACTIONS}")
    if alarm_level not in VALID_LEVELS:
        raise ValueError(f"告警级别不合法, 只允许 {VALID_LEVELS}")
    try:
        cooldown_sec = max(0, int(cooldown_sec))
    except (ValueError, TypeError):
        cooldown_sec = 60
    if action_target:
        _validate("action_target", action_target, _RE_KEY, "动作目标")
    if action_value:
        # action_value 允许数字或简单字符串
        action_value = str(action_value).strip()
    if description:
        description = _validate("description", description, _RE_DESC, "描述")
    return (name, description, trigger_key, trigger_operator, trigger_value,
            action_type, action_target, action_value, alarm_level, cooldown_sec)


def list_scene_rules(enabled_only: bool = False) -> list:
    """返回所有场景规则 (含禁用), enabled_only=True 只返回启用的"""
    with get_conn() as conn:
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM scene_rules WHERE enabled=1 ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scene_rules ORDER BY id"
            ).fetchall()
    return [dict(r) for r in rows]


def add_scene_rule(name, trigger_key, trigger_operator, trigger_value,
                   action_type, action_target="", action_value="",
                   alarm_level="warning", cooldown_sec=60, description=""):
    """新增场景规则. 字段在入库前做正则校验."""
    (name, description, trigger_key, trigger_operator, trigger_value,
     action_type, action_target, action_value, alarm_level, cooldown_sec
     ) = _validate_rule_fields(
        name, trigger_key, trigger_operator, trigger_value,
        action_type, action_target, action_value,
        alarm_level, cooldown_sec, description
    )
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scene_rules
               (name, description, trigger_key, trigger_operator, trigger_value,
                action_type, action_target, action_value, alarm_level, cooldown_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, description, trigger_key, trigger_operator, trigger_value,
             action_type, action_target, action_value, alarm_level, cooldown_sec),
        )


def update_scene_rule(rule_id, **kwargs):
    """更新场景规则. 只更新传入的字段, 全部做正则校验."""
    fields = []
    values = []
    if "name" in kwargs:
        kwargs["name"] = _validate("name", kwargs["name"], _RE_RULE_NAME, "规则名称")
        fields.append("name=?"); values.append(kwargs["name"])
    if "description" in kwargs and kwargs["description"]:
        kwargs["description"] = _validate("description", kwargs["description"], _RE_DESC, "描述")
        fields.append("description=?"); values.append(kwargs["description"])
    if "trigger_key" in kwargs:
        kwargs["trigger_key"] = _validate("trigger_key", kwargs["trigger_key"], _RE_KEY, "触发采集点")
        fields.append("trigger_key=?"); values.append(kwargs["trigger_key"])
    if "trigger_operator" in kwargs:
        if kwargs["trigger_operator"] not in VALID_OPERATORS:
            raise ValueError(f"运算符不合法, 只允许 {VALID_OPERATORS}")
        fields.append("trigger_operator=?"); values.append(kwargs["trigger_operator"])
    if "trigger_value" in kwargs:
        if str(kwargs["trigger_value"]).strip() == "":
            raise ValueError("阈值不能为空")
        fields.append("trigger_value=?"); values.append(str(kwargs["trigger_value"]).strip())
    if "action_type" in kwargs:
        if kwargs["action_type"] not in VALID_ACTIONS:
            raise ValueError(f"动作类型不合法, 只允许 {VALID_ACTIONS}")
        fields.append("action_type=?"); values.append(kwargs["action_type"])
    if "action_target" in kwargs and kwargs["action_target"]:
        kwargs["action_target"] = _validate("action_target", kwargs["action_target"], _RE_KEY, "动作目标")
        fields.append("action_target=?"); values.append(kwargs["action_target"])
    if "action_value" in kwargs and kwargs["action_value"]:
        fields.append("action_value=?"); values.append(str(kwargs["action_value"]).strip())
    if "alarm_level" in kwargs:
        if kwargs["alarm_level"] not in VALID_LEVELS:
            raise ValueError(f"告警级别不合法, 只允许 {VALID_LEVELS}")
        fields.append("alarm_level=?"); values.append(kwargs["alarm_level"])
    if "cooldown_sec" in kwargs:
        try:
            kwargs["cooldown_sec"] = max(0, int(kwargs["cooldown_sec"]))
        except (ValueError, TypeError):
            kwargs["cooldown_sec"] = 60
        fields.append("cooldown_sec=?"); values.append(kwargs["cooldown_sec"])
    if "enabled" in kwargs:
        fields.append("enabled=?"); values.append(1 if kwargs["enabled"] else 0)
    if not fields:
        return
    fields.append("updated_at=CURRENT_TIMESTAMP")
    values.append(rule_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE scene_rules SET {','.join(fields)} WHERE id=?",
            values,
        )


def delete_scene_rule(rule_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM scene_rules WHERE id=?", (rule_id,))


def evaluate_scene_rules(gateway_key, value) -> list:
    """评估某采集点变化时, 所有匹配的场景规则.

    返回需要执行的动作列表, 每项:
      {
        rule_id, rule_name, action_type, action_target, action_value,
        alarm_level, source_key, source_value, cooldown_sec
      }

    内部处理冷却逻辑: 在 cooldown_sec 内的规则不重复触发.
    触发后会更新 last_triggered + trigger_count.
    """
    now_ts = time.time()
    actions = []
    with get_conn() as conn:
        # 查所有启用的、trigger_key 匹配的规则
        rows = conn.execute(
            "SELECT * FROM scene_rules WHERE enabled=1 AND trigger_key=?",
            (gateway_key,),
        ).fetchall()
        rules = [dict(r) for r in rows]

        for rule in rules:
            # 冷却检查: last_triggered 在 cooldown_sec 内 → 跳过
            if rule["last_triggered"]:
                # SQLite TIMESTAMP 用 UTC, 转成 epoch 比较
                lt_str = rule["last_triggered"]
                try:
                    # 格式: YYYY-MM-DD HH:MM:SS (UTC)
                    lt_struct = time.strptime(lt_str, "%Y-%m-%d %H:%M:%S")
                    lt_epoch = time.mktime(time.gmtime()) - (time.mktime(time.localtime()) - time.mktime(time.gmtime()))
                    # 更简单: 直接用 datetime
                    import datetime
                    dt = datetime.datetime.strptime(lt_str, "%Y-%m-%d %H:%M:%S")
                    # SQLite CURRENT_TIMESTAMP 是 UTC, 这里按 UTC 解析
                    lt_epoch = (dt - datetime.datetime(1970, 1, 1)).total_seconds()
                    elapsed = now_ts - lt_epoch
                    if elapsed < rule["cooldown_sec"]:
                        continue  # 在冷却期内, 跳过
                except Exception:
                    pass  # 解析失败不阻塞, 放行

            # 评估条件
            if not _compare(value, rule["trigger_operator"], rule["trigger_value"]):
                continue

            # 命中 → 更新 last_triggered + trigger_count
            conn.execute(
                """UPDATE scene_rules
                   SET last_triggered=CURRENT_TIMESTAMP, trigger_count=trigger_count+1
                   WHERE id=?""",
                (rule["id"],),
            )

            actions.append({
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "action_type": rule["action_type"],
                "action_target": rule["action_target"],
                "action_value": rule["action_value"],
                "alarm_level": rule["alarm_level"],
                "source_key": gateway_key,
                "source_value": str(value),
                "cooldown_sec": rule["cooldown_sec"],
            })

    return actions


# ============================================================
# Day10 新增: 告警记录 CRUD
# ============================================================
def create_alarm(rule_id=None, rule_name="", source_key="", source_value="",
                 level="warning", message=""):
    """产生一条告警记录 (规则触发或手动产生).

    level: info / warning / critical
    """
    if level not in VALID_LEVELS:
        raise ValueError(f"告警级别不合法, 只允许 {VALID_LEVELS}")
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO alarm_records
               (rule_id, rule_name, source_key, source_value, level, message, status)
               VALUES (?, ?, ?, ?, ?, ?, 'active')""",
            (rule_id, rule_name, source_key, source_value, level, message),
        )
        return cur.lastrowid


def list_alarms(status=None, level=None, limit=100) -> list:
    """查询告警记录. 可按 status/level 过滤."""
    sql = "SELECT * FROM alarm_records"
    conditions = []
    params = []
    if status:
        if status not in VALID_ALARM_STATUS:
            raise ValueError(f"告警状态不合法, 只允许 {VALID_ALARM_STATUS}")
        conditions.append("status=?")
        params.append(status)
    if level:
        if level not in VALID_LEVELS:
            raise ValueError(f"告警级别不合法, 只允许 {VALID_LEVELS}")
        conditions.append("level=?")
        params.append(level)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY triggered_at DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_active_alarms(limit=50) -> list:
    """返回所有 active 告警 (按时间倒序)"""
    return list_alarms(status="active", limit=limit)


def acknowledge_alarm(alarm_id, username=""):
    """确认告警 (active → acknowledged)"""
    with get_conn() as conn:
        conn.execute(
            """UPDATE alarm_records
               SET status='acknowledged', acknowledged_at=CURRENT_TIMESTAMP, acknowledged_by=?
               WHERE id=? AND status='active'""",
            (username, alarm_id),
        )


def clear_alarm(alarm_id):
    """清除告警 (acknowledged → cleared, 或 active → cleared)"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE alarm_records SET status='cleared' WHERE id=?",
            (alarm_id,),
        )


def acknowledge_all_alarms(username=""):
    """一键确认所有 active 告警"""
    with get_conn() as conn:
        conn.execute(
            """UPDATE alarm_records
               SET status='acknowledged', acknowledged_at=CURRENT_TIMESTAMP, acknowledged_by=?
               WHERE status='active'""",
            (username,),
        )


def clear_all_alarms():
    """一键清除所有告警 (active + acknowledged → cleared)"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE alarm_records SET status='cleared' WHERE status IN ('active', 'acknowledged')"
        )


def get_alarm_stats() -> dict:
    """告警统计 (供看板): 各级别 + 各状态数量"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT level, status, COUNT(*) as cnt
               FROM alarm_records
               GROUP BY level, status"""
        ).fetchall()
    stats = {
        "total": 0,
        "active": 0,
        "acknowledged": 0,
        "cleared": 0,
        "info": 0,
        "warning": 0,
        "critical": 0,
        "active_critical": 0,  # 未确认的严重告警 (重点指标)
    }
    for r in rows:
        lvl = r["level"]
        st = r["status"]
        cnt = r["cnt"]
        stats["total"] += cnt
        if st in stats:
            stats[st] += cnt
        if lvl in stats:
            stats[lvl] += cnt
        if st == "active" and lvl == "critical":
            stats["active_critical"] += cnt
    return stats


def get_scene_rule_stats() -> dict:
    """场景规则统计 (供看板)"""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT enabled, COUNT(*) as cnt,
                      COALESCE(SUM(trigger_count), 0) as total_triggers
               FROM scene_rules GROUP BY enabled"""
        ).fetchall()
    stats = {"total": 0, "enabled": 0, "disabled": 0, "total_triggers": 0}
    for r in rows:
        cnt = r["cnt"]
        stats["total"] += cnt
        if r["enabled"]:
            stats["enabled"] += cnt
        else:
            stats["disabled"] += cnt
        stats["total_triggers"] += r["total_triggers"]
    return stats


# ============================================================
# 快速自检: python db.py  会建库 + 打印当前路由 + 场景规则
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
    print("\n场景规则:")
    for r in list_scene_rules():
        status = "启用" if r["enabled"] else "禁用"
        print(f"  [{r['id']}] {r['name']:20s} {status}  "
              f"IF {r['trigger_key']} {r['trigger_operator']} {r['trigger_value']} "
              f"THEN {r['action_type']}({r['action_target']},{r['action_value']}) "
              f"[触发 {r['trigger_count']} 次]")
    print("\n告警统计:")
    stats = get_alarm_stats()
    print(f"  总计 {stats['total']} 条: active={stats['active']} "
          f"ack={stats['acknowledged']} cleared={stats['cleared']}")
    print(f"  级别: info={stats['info']} warning={stats['warning']} critical={stats['critical']}")
