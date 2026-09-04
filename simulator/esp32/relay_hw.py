"""继电器硬件抽象: 逻辑状态(0/1) <-> GPIO 电平, 板载按键扫描

逻辑状态为唯一事实来源, GPIO 电平由 ACTIVE_LOW 换算。
板级接线固定, 常量内置在本文件; 用户可变配置(WiFi/MQTT)在 app_config.py。

按键:
  SW1(IO10) 短按=切继电器1; 长按5秒=请求进入配网模式
  SW2(IO9, 即BOOT键) 短按=切继电器2; 双击=4路全开<->全关
  SW3(IO6) 短按=切继电器3   SW4(IO8) 短按=切继电器4
"""
from machine import Pin, Timer
import time

# ---------- 板级固定接线 ----------
RELAY_PINS = [3, 4, 5, 7]              # 继电器1~4 -> IO3/4/5/7
RELAY_ACTIVE_LOW = False               # 高电平触发 (实测)
BUTTON_MAP = [(10, 0), (9, 1), (6, 2), (8, 3)]   # (按键GPIO, 继电器序号0起)
BUTTON_BOOT_GPIO = 9                   # SW2: 双击切全部
BUTTON_CONFIG_GPIO = 10                # SW1: 长按5秒进配网
CONFIG_LONGPRESS_MS = 5000
DOUBLECLICK_MS = 350

_state = [0] * len(RELAY_PINS)
_pins = []
_config_request = False                # 主循环轮询: SW1 长按5秒置位


def init():
    """初始化 GPIO, 上电时继电器全部置为开"""
    global _pins
    _pins = [Pin(p, Pin.OUT) for p in RELAY_PINS]
    for i in range(len(_pins)):
        _state[i] = 1
        _apply(i)


def _level(on):
    """逻辑开关 -> GPIO 电平"""
    if RELAY_ACTIVE_LOW:
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


def config_requested():
    """主循环调用: SW1 长按5秒请求过配网? (读取并清除)"""
    global _config_request
    if _config_request:
        _config_request = False
        return True
    return False


# ---------- 按键扫描 ----------
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


def attach_buttons(mapping=None, double_ms=DOUBLECLICK_MS):
    """启动按键扫描定时器 (20ms 周期)。

      - 普通键: 松开即切换对应一路
      - SW2(BOOT): 短按切继电器2, double_ms 内双击切全部
      - SW1: 按住 CONFIG_LONGPRESS_MS 毫秒 -> 请求配网模式, 松开不再触发短按
    """
    global _btn_timer
    if mapping is None:
        mapping = BUTTON_MAP
    keys = []
    for gpio, idx in mapping:
        keys.append({
            'gpio': gpio, 'idx': idx,
            'is_boot': gpio == BUTTON_BOOT_GPIO,
            'is_config': gpio == BUTTON_CONFIG_GPIO,
            'pin': Pin(gpio, Pin.IN, Pin.PULL_UP),
            'last_raw': 1, 'settled': 1, 'armed': False,
            'clicks': 0, 't_release': 0,
            't_press': 0, 'long_fired': False,
        })

    def scan(_t):
        global _config_request
        now = time.ticks_ms()
        for k in keys:
            raw = k['pin'].value()
            if raw != k['last_raw']:          # 电平抖动中, 等它稳定
                k['last_raw'] = raw
                continue
            if raw != k['settled']:
                k['settled'] = raw
                if raw == 0:                  # 稳定按下
                    k['armed'] = True
                    k['long_fired'] = False
                    k['t_press'] = now
                else:                         # 稳定松开
                    k['armed'] = False
                    if k['long_fired']:       # 长按已触发, 松开不再短按
                        k['long_fired'] = False
                    elif k['is_boot']:
                        k['clicks'] += 1
                        k['t_release'] = now
                        if k['clicks'] >= 2:  # 双击 -> 全部切换
                            k['clicks'] = 0
                            new = toggle_all()
                            print("[relay_hw] BOOT 双击: 全部 -> %s"
                                  % ("开" if new else "关"))
                    else:
                        new = toggle(k['idx'])
                        print("[relay_hw] SW(IO%d) 短按: 继电器%d -> %s"
                              % (k['gpio'], k['idx'] + 1, "开" if new else "关"))
                continue
            # 电平稳定中
            if raw == 0 and k['is_config'] and k['armed'] and not k['long_fired']:
                if time.ticks_diff(now, k['t_press']) >= CONFIG_LONGPRESS_MS:
                    k['long_fired'] = True
                    _config_request = True
                    print("[relay_hw] SW1 长按5秒: 请求进入配网模式")
            if (k['is_boot'] and k['clicks'] == 1 and raw == 1
                    and time.ticks_diff(now, k['t_release']) > double_ms):
                # BOOT 单击后超时未等到第二次按下 -> 按单击处理
                k['clicks'] = 0
                new = toggle(k['idx'])
                print("[relay_hw] SW(IO%d) 短按: 继电器%d -> %s"
                      % (k['gpio'], k['idx'] + 1, "开" if new else "关"))

    _btn_timer = Timer(0)
    _btn_timer.init(period=20, mode=Timer.PERIODIC, callback=scan)
