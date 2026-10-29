"""滑块验证求解器

实测：极验（GeeTest）滑动拼图一次通过（2026-10-29）。

原理：
1. 缺口定位用 OpenCV（不靠视觉模型），找到拼图块凹槽的左边界
2. 轨迹用贝塞尔 + ease_out + 微抖动
3. 松手前停顿 0.2s —— 这是最关键的人类特征，机器通常拖到位立刻松手
"""
import time
import random
import math
from typing import Optional, Tuple, Dict, Any

import numpy as np
import cv2


def find_gap_x(bar_img: np.ndarray, piece_w: int = 50) -> Optional[int]:
    """从拼图区域找缺口左边界 x（相对该图）

    思路：极验的缺口是一个半透明暗色凹槽。用列方向的梯度能量找突变列。
    返回 None 表示没找到。
    """
    if bar_img is None or bar_img.size == 0:
        return None
    g = cv2.cvtColor(bar_img, cv2.COLOR_RGB2GRAY)
    # 高斯平滑去掉高频噪声
    g = cv2.GaussianBlur(g, (5, 5), 0)
    edges = cv2.Canny(g, 40, 120)

    h, w = edges.shape
    # 每列的边缘强度总和
    col_energy = edges.sum(axis=0) / 255.0
    # 只看右半边（拼图块在左边）
    half = w // 2
    right = col_energy[half:]
    if right.max() <= 0:
        return None

    # 缺口左右边界都是强边缘：找一对间隔≈piece_w 的峰
    thresh = right.max() * 0.55
    peaks = [i for i, v in enumerate(right) if v >= thresh]
    if not peaks:
        return None

    best = None
    best_score = 0
    for p in peaks:
        # 距 p 约 piece_w 处也应有峰（缺口右边界）
        for q in peaks:
            d = abs(q - p)
            if abs(d - piece_w) <= 12:
                score = right[p] + right[q]
                if score > best_score:
                    best_score = score
                    best = p
    return (half + best) if best is not None else (half + peaks[0])


def build_track(distance: float, duration: float = 0.9,
                style: str = "human") -> list:
    """生成拖拽轨迹（相对位移序列）

    style:
      human  - 加速→匀速→减速（默认，最像人）
      linear - 匀速（不要用于滑块）
    """
    d = float(distance)
    steps = max(14, min(70, int(d / 3.2)))

    # 时间权重：前 15% 加速、中段匀速、末 35% 减速
    weights = []
    for i in range(steps):
        t = i / max(1, steps - 1)
        if style == "linear":
            w = 1.0
        else:
            if t < 0.15:
                w = 0.45 + t / 0.15 * 0.8          # 起步加速
            elif t < 0.62:
                w = 1.25                            # 匀速
            else:
                p = (t - 0.62) / 0.38
                w = 1.25 * (1 - p) ** 1.7 + 0.16    # 减速到很慢
        w *= random.uniform(0.9, 1.1)               # 速度扰动
        weights.append(w)

    tot = sum(weights)
    # 归一化到目标距离
    track = []
    acc = 0.0
    for i, w in enumerate(weights):
        step = d * w / tot
        acc += step
        track.append(step)

    # 修正累积误差，最后一步补齐
    diff = d - sum(track)
    track[-1] += diff
    return track


def solve(mouse, cap, bar_region: Tuple[int, int, int, int],
          puzzle_region: Optional[Tuple[int, int, int, int]] = None,
          drag_y: Optional[int] = None,
          piece_w: int = 50, duration: float = 0.9,
          release_delay: float = 0.22, tolerance: int = 1,
          verbose: bool = True) -> Dict[str, Any]:
    """求解滑块验证

    bar_region   : 滑块条区域 (left, top, w, h)，用来定位滑块按钮
    puzzle_region: 拼图区域 (left, top, w, h)，用来找缺口
    drag_y       : 拖动时鼠标的 y（默认取滑块条中线）
    piece_w      : 拼图块宽度（极验约 48-52px）
    release_delay: 松手前停顿，关键参数
    """
    from core.capture import hex_to_rgb  # noqa

    # 1) 找滑块按钮
    bx, by, bw, bh = bar_region
    bar_img = np.array(cap.grab(bar_region))
    # 按钮通常是左侧的深色圆角块
    g = cv2.cvtColor(bar_img, cv2.COLOR_RGB2GRAY)
    # 找最暗的连通区域左边缘
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cols = th.sum(axis=0)
    if cols.max() == 0:
        return {"ok": False, "reason": "找不到滑块按钮"}
    btn_rel_x = int(np.argmax(cols > cols.max() * 0.3))
    btn_x = bx + btn_rel_x + 18        # 按钮中心偏移
    btn_y = drag_y if drag_y is not None else by + bh // 2

    # 2) 找缺口
    if puzzle_region is None:
        # 默认：滑块条上方
        puzzle_region = (bx, by - 160, bw, 150)
    pz_img = np.array(cap.grab(puzzle_region))
    gap_x = find_gap_x(pz_img, piece_w=piece_w)
    if gap_x is None:
        return {"ok": False, "reason": "找不到缺口（derive 失败，建议用 vision 辅助）"}
    target_x = puzzle_region[0] + gap_x + piece_w // 2
    distance = target_x - btn_x

    if verbose:
        print(f"滑块按钮: ({btn_x},{btn_y})  缺口: x={target_x}  距离: {distance}px")

    # 3) 拖
    track = build_track(distance, duration=duration)
    mouse.move_to(btn_x, btn_y, duration=0.35)
    time.sleep(0.08)
    mouse.press()
    time.sleep(0.15)

    cur = btn_x
    total_dt = duration / len(track)
    for i, dx in enumerate(track):
        cur += dx
        # 纵向微漂移（人手特征）
        dy = random.uniform(-0.6, 0.6)
        mouse.move_abs_jitter(cur, btn_y + dy)
        time.sleep(total_dt * random.uniform(0.85, 1.15))
        # 中途偶发微停顿
        if i == len(track) // 2 and random.random() < 0.4:
            time.sleep(random.uniform(0.04, 0.09))

    # 4) 落点微调到整数位置
    mouse.move_to(target_x, btn_y, duration=0.12, jitter=0.2)
    time.sleep(release_delay)
    mouse.release()

    return {
        "ok": True,
        "button": [btn_x, btn_y],
        "target_x": target_x,
        "distance": distance,
        "steps": len(track),
        "duration": duration,
        "release_delay": release_delay,
    }
