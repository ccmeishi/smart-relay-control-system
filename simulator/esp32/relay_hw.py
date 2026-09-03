"""继电器硬件抽象: 逻辑状态(0/1) <-> GPIO 电平

逻辑状态为唯一事实来源, GPIO 电平由 RELAY_ACTIVE_LOW 换算,
两条路线 (MQTT / Modbus) 共用, 保证固件切换时行为一致。
"""
from machine import Pin
import config as C

_state = [0] * len(C.RELAY_PINS)
_pins = []


def init():
    """初始化 GPIO, 上电时继电器全部置为开"""
    global _pins
    _pins = [Pin(p, Pin.OUT) for p in C.RELAY_PINS]
    for i in range(len(_pins)):
        _state[i] = 1
        _apply(i)


def _level(on):
    """逻辑开关 -> GPIO 电平"""
    if C.RELAY_ACTIVE_LOW:
        return 0 if on else 1
    return 1 if on else 0


def _apply(i):
    _pins[i].value(_level(_state[i]))


def set(i, on):
    """设置第 i 路 (0起) 逻辑状态: 1=开 0=关"""
    if 0 <= i < len(_state):
        _state[i] = 1 if on else 0
        _apply(i)


def get(i):
    return _state[i]


def states():
    return list(_state)


def count():
    return len(_state)
