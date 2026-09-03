"""继电器硬件抽象: 逻辑状态(0/1) <-> GPIO 电平

逻辑状态为唯一事实来源, GPIO 电平由 RELAY_ACTIVE_LOW 换算,
两条路线 (MQTT / Modbus) 共用, 保证固件切换时行为一致。
"""
from machine import Pin, Timer
import time
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


# ---------- 板载按键 ----------
_btn_timer = None


def toggle(idx):
    """切换单路, 返回新状态"""
    new = 0 if _state[idx] else 1
    _state[idx] = new
    _apply(idx)
    return new


def toggle_all():
    """全部继电器一起翻转 (全开<->全关), 返回新的状态"""
    new = 0 if all(_state) else 1
    for i in range(len(_state)):
        _state[i] = new
        _apply(i)
    return new


def attach_buttons(mapping, double_ms=350):
    """绑定板载按键。

    mapping: [(gpio, relay_idx), ...]  按键 GPIO -> 继电器序号(0起)
      - 普通键: 短按(按下再松开)即切换对应一路
      - BOOT 键(C.BUTTON_BOOT_GPIO): 短按切对应一路;
        double_ms 内连按两次 = 双击, 切换全部
    """
    global _btn_timer
    keys = []
    for gpio, idx in mapping:
        keys.append({
            'gpio': gpio, 'idx': idx, 'is_boot': gpio == C.BUTTON_BOOT_GPIO,
            'pin': Pin(gpio, Pin.IN, Pin.PULL_UP),
            'last_raw': 1, 'settled': 1, 'armed': False,
            'clicks': 0, 't_release': 0,
        })

    def scan(_t):
        now = time.ticks_ms()
        for k in keys:
            raw = k['pin'].value()
            if raw != k['last_raw']:          # 电平抖动中, 等它稳定
                k['last_raw'] = raw
                continue
            if raw == k['settled']:
                # BOOT 单击后超时未等到第二次按下 -> 按单击处理
                if (k['is_boot'] and k['clicks'] == 1 and raw == 1
                        and time.ticks_diff(now, k['t_release']) > double_ms):
                    k['clicks'] = 0
                    new = toggle(k['idx'])
                    print("[relay_hw] SW(GPIO%d) 短按: 继电器%d -> %s"
                          % (k['gpio'], k['idx'] + 1, "开" if new else "关"))
                continue
            k['settled'] = raw
            if raw == 0:                      # 稳定按下
                k['armed'] = True
            elif k['armed']:                  # 稳定松开 = 一次点击
                k['armed'] = False
                if k['is_boot']:
                    k['clicks'] += 1
                    k['t_release'] = now
                    if k['clicks'] >= 2:      # 双击 -> 全部切换
                        k['clicks'] = 0
                        new = toggle_all()
                        print("[relay_hw] BOOT 双击: 4路 -> %s"
                              % ("开" if new else "关"))
                else:
                    new = toggle(k['idx'])
                    print("[relay_hw] SW(GPIO%d) 短按: 继电器%d -> %s"
                          % (k['gpio'], k['idx'] + 1, "开" if new else "关"))

    _btn_timer = Timer(0)
    _btn_timer.init(period=20, mode=Timer.PERIODIC, callback=scan)
