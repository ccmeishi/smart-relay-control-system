"""继电器硬件抽象: 逻辑状态(0/1) <-> GPIO 电平

逻辑状态为唯一事实来源, GPIO 电平由 RELAY_ACTIVE_LOW 换算,
两条路线 (MQTT / Modbus) 共用, 保证固件切换时行为一致。
"""
from machine import Pin, Timer
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


# ---------- 板载按键 (BOOT/KEY 键 = GPIO9) ----------
_btn_timer = None


def toggle_all():
    """全部继电器一起翻转 (全开<->全关), 返回新的状态"""
    new = 0 if all(_state) else 1
    for i in range(len(_state)):
        _state[i] = new
        _apply(i)
    return new


def attach_button(pin_num=9, on_change=None):
    """绑定板载按键: 每按一次(按下再松开)翻转全部继电器。

    on_change(new_state) 为可选回调, 在定时器中断上下文执行,
    只能做轻量操作, 不要做网络/耗时操作。
    """
    global _btn_timer
    btn = Pin(pin_num, Pin.IN, Pin.PULL_UP)
    last_raw = 1                     # 上次原始电平 (上拉, 松开=1)
    settled = 1                      # 消抖后的稳定电平
    armed = False                    # 已按下, 等待松开触发

    def scan(_t):
        nonlocal last_raw, settled, armed
        raw = btn.value()
        if raw != last_raw:          # 电平抖动中, 等它稳定
            last_raw = raw
            return
        if raw == settled:
            return
        settled = raw
        if raw == 0:                 # 稳定按下
            armed = True
        elif armed:                  # 稳定松开 -> 触发一次翻转
            armed = False
            new = toggle_all()
            print("[relay_hw] 板载按键: 4路 -> %s" % ("开" if new else "关"))
            if on_change:
                on_change(new)

    _btn_timer = Timer(0)
    _btn_timer.init(period=20, mode=Timer.PERIODIC, callback=scan)
