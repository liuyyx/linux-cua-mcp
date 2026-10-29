"""内核级输入层：贝塞尔平滑移动、拟人点击、拖拽。

原理：写 /dev/uinput，应用层无法区分真假输入（绕过 XTest 过滤）。
坐标读取用 Xlib，位移用 REL 事件（ABS 在部分 X server 上无效）。
"""
import time
import math
import random
from evdev import UInput, ecodes as e
from Xlib import display as xdisplay


class Mouse:
    def __init__(self, name="cua-mouse"):
        self.ui = UInput({
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE],
            e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL],
        }, name=name, version=0x1)
        self.d = xdisplay.Display()
        self.root = self.d.screen().root
        time.sleep(0.15)          # 等 X 注册设备

    # ---------- 基础 ----------
    def pos(self):
        p = self.d.screen().root.query_pointer()
        return p.root_x, p.root_y

    def _rel(self, dx, dy):
        if abs(dx) >= 0.5:
            self.ui.write(e.EV_REL, e.REL_X, int(round(dx)))
        if abs(dy) >= 0.5:
            self.ui.write(e.EV_REL, e.REL_Y, int(round(dy)))
        self.ui.syn()

    def _correct(self, tx, ty):
        """落点校正（warp 是绝对定位，一次到位）"""
        self.root.warp_pointer(int(round(tx)), int(round(ty)))
        self.d.sync()
        return True

    # ---------- 平滑移动 ----------
    def move_to(self, x, y, duration=0.55, curve=0.28, jitter=0.9,
                ease="smooth", pause_chance=0.25):
        """贝塞尔曲线 + 变速 + 拟人抖动

        x, y       : 目标屏幕坐标
        duration   : 秒，太长像动画，太短像瞬移。0.4-0.9 最像人
        curve      : 0 = 直线, 0.5 = 明显弧线
        jitter     : 抖动像素幅度
        ease       : smooth(默认) / linear / ease_out
        pause_chance: 中段随机微停顿的概率
        """
        x0, y0 = self.pos()
        dist = math.hypot(x - x0, y - y0)
        if dist < 2:
            self._correct(x, y)
            return

        # 两个控制点，各自垂直偏移，方向一致但幅度不同
        nx, ny = -(y - y0), (x - x0)
        norm = math.hypot(nx, ny) or 1
        nx, ny = nx / norm, ny / norm
        sign = random.choice([-1, 1])
        off1 = dist * curve * sign * random.uniform(0.55, 0.95)
        off2 = dist * curve * sign * random.uniform(0.30, 0.70)

        cx1 = x0 + (x - x0) * 0.33 + nx * off1
        cy1 = y0 + (y - y0) * 0.33 + ny * off1
        cx2 = x0 + (x - x0) * 0.67 + nx * off2
        cy2 = y0 + (y - y0) * 0.67 + ny * off2

        steps = max(14, min(90, int(dist / 10)))
        base_dt = duration / steps

        px, py = x0, y0
        paused = False
        for i in range(1, steps + 1):
            t = i / steps
            if ease == "linear":
                te = t
            elif ease == "ease_out":
                te = 1 - (1 - t) ** 3
            else:
                te = 0.5 - 0.5 * math.cos(math.pi * t)

            u = 1 - te
            bx = u**3 * x0 + 3 * u**2 * te * cx1 + 3 * u * te**2 * cx2 + te**3 * x
            by = u**3 * y0 + 3 * u**2 * te * cy1 + 3 * u * te**2 * cy2 + te**3 * y

            # 越接近终点抖动越小
            jf = jitter * (1 - te * 0.65)
            tx = bx + random.uniform(-jf, jf)
            ty = by + random.uniform(-jf, jf)

            self.root.warp_pointer(int(round(tx)), int(round(ty)))
            self.d.sync()
            px, py = tx, ty

            # 速度扰动
            dt = base_dt * random.uniform(0.82, 1.18)
            # 中段偶发微停顿（拟人特征）
            if not paused and 0.35 < t < 0.7 and random.random() < pause_chance / 10:
                dt += random.uniform(0.05, 0.11)
                paused = True
            time.sleep(dt)

        self._correct(x, y)

    # ---------- 点击 ----------
    def click(self, x=None, y=None, button=e.BTN_LEFT, n=1, move=True, duration=0.55):
        if x is not None and y is not None:
            if move:
                self.move_to(x, y, duration=duration)
            else:
                self.root.warp_pointer(int(round(x)), int(round(y)))
                self.d.sync()
                time.sleep(0.03)
        for i in range(n):
            press = random.uniform(0.05, 0.095)
            gap = random.uniform(0.07, 0.13)
            self.ui.write(e.EV_KEY, button, 1)
            self.ui.syn()
            time.sleep(press)
            self.ui.write(e.EV_KEY, button, 0)
            self.ui.syn()
            if i < n - 1:
                time.sleep(gap)

    # ---------- 按下/松开（拖拽用）----------
    def press(self, button=e.BTN_LEFT):
        self.ui.write(e.EV_KEY, button, 1)
        self.ui.syn()

    def release(self, button=e.BTN_LEFT):
        self.ui.write(e.EV_KEY, button, 0)
        self.ui.syn()

    def move_abs_jitter(self, x, y, jitter=0.0):
        """绝对定位 + 可选抖动（拖拽过程用）"""
        if jitter:
            x += random.uniform(-jitter, jitter)
            y += random.uniform(-jitter, jitter)
        self.root.warp_pointer(int(round(x)), int(round(y)))
        self.d.sync()

    def double_click(self, x=None, y=None):
        self.click(x, y, n=2)

    def right_click(self, x=None, y=None):
        self.click(x, y, button=e.BTN_RIGHT)

    # ---------- 拖拽 ----------
    def drag(self, x1, y1, x2, y2, duration=1.0, hold=0.12, release_delay=0.18):
        """按住 → 平滑拖到目标 → 停一下 → 松开

        release_delay: 松手前的停顿，滑块验证的关键（机器特征是没有这一下）
        """
        self.move_to(x1, y1, duration=0.4)
        time.sleep(0.08)

        self.ui.write(e.EV_KEY, e.BTN_LEFT, 1)
        self.ui.syn()
        time.sleep(hold)

        self.move_to(x2, y2, duration=duration, curve=0.06, jitter=0.4,
                     ease="ease_out", pause_chance=0.6)

        time.sleep(release_delay)
        self.ui.write(e.EV_KEY, e.BTN_LEFT, 0)
        self.ui.syn()

    # ---------- 滚轮 ----------
    def scroll(self, clicks, direction=1):
        """direction: 1=下, -1=上"""
        for _ in range(abs(clicks)):
            self.ui.write(e.EV_REL, e.REL_WHEEL, direction)
            self.ui.syn()
            time.sleep(random.uniform(0.02, 0.05))

    def close(self):
        try:
            self.ui.close()
        except Exception:
            pass


class Keyboard:
    """ASCII 键盘（中文请用 xdotool 或 fcitx DBus）"""
    MAP = {
        **{c: getattr(e, f"KEY_{c.upper()}") for c in "abcdefghijklmnopqrstuvwxyz"},
        **{str(i): getattr(e, f"KEY_{i}") for i in range(10)},
        " ": e.KEY_SPACE, ".": e.KEY_DOT, ",": e.KEY_COMMA, "-": e.KEY_MINUS,
        "/": e.KEY_SLASH, ";": e.KEY_SEMICOLON, "'": e.KEY_APOSTROPHE,
        "=": e.KEY_EQUAL, "[": e.KEY_LEFTBRACE, "]": e.KEY_RIGHTBRACE,
    }
    SHIFTED = {
        "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6",
        "&": "7", "*": "8", "(": "9", ")": "0", "_": "-", "+": "=",
        ":": ";", '"': "'", "?": "/", "<": ",", ">": ".", "{": "[", "}": "]",
    }

    def __init__(self, name="cua-kbd"):
        codes = list(set(self.MAP.values())) + [
            e.KEY_LEFTSHIFT, e.KEY_LEFTCTRL, e.KEY_LEFTALT, e.KEY_ENTER,
            e.KEY_ESC, e.KEY_TAB, e.KEY_BACKSPACE, e.KEY_DELETE,
            e.KEY_UP, e.KEY_DOWN, e.KEY_LEFT, e.KEY_RIGHT, e.KEY_HOME, e.KEY_END,
        ]
        self.ui = UInput({e.EV_KEY: codes}, name=name, version=0x1)
        time.sleep(0.15)

    def _tap(self, code, shift=False):
        if shift:
            self.ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
            self.ui.syn()
        self.ui.write(e.EV_KEY, code, 1)
        self.ui.syn()
        time.sleep(random.uniform(0.015, 0.035))
        self.ui.write(e.EV_KEY, code, 0)
        self.ui.syn()
        if shift:
            self.ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
            self.ui.syn()
        time.sleep(random.uniform(0.025, 0.06))

    def type(self, text, wpm=320):
        """逐字符输入，带节奏（wpm 约等于每分钟字符数）"""
        base = 60.0 / max(60, wpm)
        for ch in text:
            if ch.isupper():
                code = self.MAP.get(ch.lower())
                if code:
                    self._tap(code, shift=True)
            elif ch in self.MAP:
                self._tap(self.MAP[ch])
            elif ch in self.SHIFTED:
                code = self.MAP.get(self.SHIFTED[ch])
                if code:
                    self._tap(code, shift=True)
            elif ch == "\n":
                self._tap(e.KEY_ENTER)
            time.sleep(random.uniform(base * 0.5, base * 1.6))

    def key(self, name):
        m = {"enter": e.KEY_ENTER, "esc": e.KEY_ESC, "tab": e.KEY_TAB,
             "backspace": e.KEY_BACKSPACE, "delete": e.KEY_DELETE,
             "up": e.KEY_UP, "down": e.KEY_DOWN, "left": e.KEY_LEFT,
             "right": e.KEY_RIGHT, "home": e.KEY_HOME, "end": e.KEY_END}
        code = m.get(name.lower())
        if code:
            self._tap(code)

    def combo(self, *names):
        """如 combo('ctrl','c')"""
        codes = []
        for n in names:
            n = n.lower()
            if n in ("ctrl", "control"):
                codes.append(e.KEY_LEFTCTRL)
            elif n == "shift":
                codes.append(e.KEY_LEFTSHIFT)
            elif n == "alt":
                codes.append(e.KEY_LEFTALT)
            elif n in self.MAP:
                codes.append(self.MAP[n])
        for c in codes:
            self.ui.write(e.EV_KEY, c, 1)
        self.ui.syn()
        time.sleep(0.03)
        for c in reversed(codes):
            self.ui.write(e.EV_KEY, c, 0)
        self.ui.syn()

    def close(self):
        try:
            self.ui.close()
        except Exception:
            pass
