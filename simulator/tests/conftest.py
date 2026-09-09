"""pytest 配置和共享 fixture

提供：
- slave_server：启动一个真实的 modbus_slave_sim 从站进程，yield host/port/unit_id
- modbus_client：返回一个已连上从站的 pymodbus ModbusTcpClient
- mqtt_broker：起一个 amqtt broker（127.0.0.1:随机端口），yield host/port
- bridge_under_test：起一个 gateway_bridge 进程（指向本地 broker），yield bridge
- unique_port：分配一个空闲 TCP 端口
"""
import asyncio
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest


# modbus_slave_sim.py 路径
SLAVE_SCRIPT = (
    Path(__file__).resolve().parent.parent / "tools" / "modbus_slave_sim.py"
)


def _free_port() -> int:
    """分配一个空闲 TCP 端口"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def free_port():
    return _free_port()


@pytest.fixture
def slave_server(free_port):
    """启动一个真实的 modbus_slave_sim 从站进程

    返回：dict {host, port, unit_id, proc}
    测试结束后自动 kill。
    """
    port = free_port
    unit_id = 7
    proc = subprocess.Popen(
        [sys.executable, str(SLAVE_SCRIPT), str(port), str(unit_id)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(SLAVE_SCRIPT.parent),
    )
    # 等从站 listen，轮询连接
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.05)
    else:
        proc.terminate()
        raise RuntimeError(f"Modbus 从站 {port} 启动超时")
    # 多等一会让 drift 线程稳定
    time.sleep(0.1)

    info = {"host": "127.0.0.1", "port": port, "unit_id": unit_id, "proc": proc}
    try:
        yield info
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _import_pymodbus_client():
    """pymodbus 3.x 的 ModbusTcpClient 在 pymodbus.client 中"""
    from pymodbus.client import ModbusTcpClient  # type: ignore
    return ModbusTcpClient


@pytest.fixture
def modbus_client_factory(slave_server):
    """返回一个工厂函数：unit_id -> 已连上的 ModbusTcpClient

    用法：
        c = modbus_client_factory(unit_id=slave_server["unit_id"])
        rr = c.read_holding_registers(0, 4, slave=unit_id)
    """
    ModbusTcpClient = _import_pymodbus_client()
    clients = []

    def _make(unit_id):
        c = ModbusTcpClient(slave_server["host"], slave_server["port"], timeout=2)
        assert c.connect(), f"无法连接到 127.0.0.1:{slave_server['port']}"
        clients.append(c)
        return c

    yield _make
    for c in clients:
        try:
            c.close()
        except Exception:
            pass


# ============================================================
# MQTT broker + gateway_bridge 端到端测试 fixture
# ============================================================

TOOLS_DIR = SLAVE_SCRIPT.parent  # simulator/tools/


def _run_broker_in_thread(port: int, ready_event: threading.Event, stop_event: threading.Event):
    """在新线程里跑 amqtt broker 直到 stop_event 触发"""
    from amqtt.broker import Broker

    config = {
        "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{port}"}},
        "plugins": {
            "amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True},
        },
    }
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    broker = Broker(config, loop=loop)
    try:
        loop.run_until_complete(broker.start())
        ready_event.set()
        # 阻塞到 stop_event
        while not stop_event.is_set():
            loop.run_until_complete(asyncio.sleep(0.1))
        loop.run_until_complete(broker.shutdown())
    finally:
        loop.close()


@pytest.fixture
def mqtt_broker(free_port):
    """起一个 amqtt broker，yield {"host", "port"}"""
    port = free_port
    ready = threading.Event()
    stop = threading.Event()
    t = threading.Thread(
        target=_run_broker_in_thread, args=(port, ready, stop), daemon=True
    )
    t.start()
    if not ready.wait(timeout=5.0):
        stop.set()
        raise RuntimeError(f"amqtt broker {port} 启动超时")
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                break
        except OSError:
            time.sleep(0.05)
    else:
        stop.set()
        raise RuntimeError(f"broker {port} 端口不可连接")
    try:
        yield {"host": "127.0.0.1", "port": port}
    finally:
        stop.set()
        t.join(timeout=5)


def _run_bridge_in_thread(
    broker_host: str,
    broker_port: int,
    ready_event: threading.Event,
    stop_event: threading.Event,
):
    """在新线程里跑 gateway_bridge.py 直到 stop_event 触发

    通过 monkey-patch 让 bridge 指向本地 broker
    """
    # 删掉旧模块确保 monkey patch 生效
    sys.modules.pop("gateway_bridge", None)
    sys.path.insert(0, str(TOOLS_DIR))
    import gateway_bridge as gb

    # 把 MQTT 连接参数改成指向本地 broker
    gb.MQTT_HOST = broker_host
    gb.MQTT_PORT = broker_port
    gb.MQTT_USER = ""
    gb.MQTT_PASS = ""
    import random
    gb.BRIDGE_CLIENT_ID = f"bridge-test-{random.randint(0, 999999)}"

    import paho.mqtt.client as mqtt_client_mod
    client = mqtt_client_mod.Client(
        client_id=gb.BRIDGE_CLIENT_ID,
        clean_session=True,
    )
    if gb.MQTT_USER:
        client.username_pw_set(gb.MQTT_USER, gb.MQTT_PASS)
    client.on_connect = gb.on_connect
    client.on_message = gb.on_message

    try:
        client.connect(gb.MQTT_HOST, gb.MQTT_PORT, keepalive=60)
    except Exception:
        ready_event.set()  # 让主线程不等了
        return
    gb._BRIDGE_PUBLISHER = client
    ready_event.set()
    client.loop_start()
    while not stop_event.is_set():
        time.sleep(0.1)
    try:
        client.loop_stop()
        client.disconnect()
    except Exception:
        pass


@pytest.fixture
def bridge_under_test(mqtt_broker):
    """起一个 monkey-patched gateway_bridge，指向 mqtt_broker

    yield 之后自动停止。
    """
    ready = threading.Event()
    stop = threading.Event()
    t = threading.Thread(
        target=_run_bridge_in_thread,
        args=(mqtt_broker["host"], mqtt_broker["port"], ready, stop),
        daemon=True,
    )
    t.start()
    if not ready.wait(timeout=10.0):
        stop.set()
        raise RuntimeError("bridge 启动超时")
    # 多给 bridge 时间连 broker + 订阅 topic
    time.sleep(1.5)
    try:
        yield {"broker": mqtt_broker, "thread": t}
    finally:
        stop.set()
        t.join(timeout=5)
