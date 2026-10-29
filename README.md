# linux-cua-mcp

Linux 桌面操控 MCP Server —— 平滑移动、内核级点击、滑块验证、区域截图 + 网格坐标。

## 为什么不用 xdotool / pyautogui

它们走 XTest / XSendEvent，**浏览器和 Electron 应用会忽略这些合成事件**——表现为"光标动了，但界面没反应"。

本项目：
- **移动**：Xlib `warp_pointer` 绝对定位（精确，0 误差，0.1ms/次）
- **点击/拖拽/键盘**：写 `/dev/uinput`，创建真实 HID 设备，应用无法区分

两者分工是实测出来的结论：X server 的鼠标加速让 REL 相对位移**非线性**（实测 50→27px、100→100px、200→301px），所以贝塞尔轨迹必须用绝对坐标走。

## 能力

| 工具 | 说明 |
|---|---|
| `screenshot` | 全屏/区域截图，可叠网格（绝对坐标）、标点 |
| `get_cursor_position` / `get_screen_size` | 光标与屏幕信息 |
| `move_to` | 贝塞尔曲线 + 变速 + 拟人抖动，落点 0 误差 |
| `click` / `drag` / `scroll` | 内核级点击、拖拽、滚轮 |
| `type_text` / `press_key` / `hotkey` | ASCII 键盘输入（带节奏） |
| `do_sequence` | 一次调用执行多步动作链 |

## 实测

**极验（GeeTest）滑动拼图 2/2 通过**，含全自动缺口检测。

成功的五个要素：
1. 内核级注入（检测不到 XTest 特征）
2. 贝塞尔曲线（不是完美直线）
3. ease_out 变速（前段加速、尾段减速）
4. **松手前停顿 0.2s**（机器通常拖到位立刻松手，这是最明显的机器特征）
5. 微抖动（±0.6px 纵向漂移）

## 安装

```bash
python3 -m venv venv
venv/bin/pip install evdev mss pillow numpy opencv-python-headless python-xlib fastmcp
```

`/dev/uinput` 需要可写：

```bash
ls -l /dev/uinput
# crw------- 时：
echo 'KERNEL=="uinput", MODE="0666"' | sudo -S -p '' tee /etc/udev/rules.d/99-uinput.rules
sudo -S -p '' udevadm control --reload && sudo -S -p '' udevadm trigger
```

## 接入 Hermes

```bash
hermes mcp add linux-cua \
  --command "/path/to/venv/bin/python" \
  --env DISPLAY=:0 XAUTHORITY=$HOME/.Xauthority \
  --args /path/to/mcp_server.py
```

## 用法示例

```python
from core.input import Mouse
from core.capture import Capture
from core import slider

m, c = Mouse(), Capture()

# 平滑移动 + 点击
m.click(500, 300, duration=0.6)

# 截图带网格（绝对坐标）
img = c.draw_grid(c.grab((200, 150, 800, 600)), step=50, major=100, offset=(200, 150))

# 多步
m.move_to(100, 100)
m.drag(100, 100, 400, 500)

# 滑块验证
slider.solve(m, c, bar_region=(820, 455, 290, 55), puzzle_region=(820, 285, 260, 155))
```

## 已知限制

- 中文输入未内置（evdev keymap 只有 ASCII），用 `xdotool type` 走 fcitx
- 缺口检测是通用 Canny 方案，非极验专用；面对特殊样式的验证码需要调 `piece_w`
- 高 DPI / 多屏未适配（当前按单屏 1920×1080 计算）

## License

MIT
