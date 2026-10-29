"""纯 OpenCV 的 UI 元素检测（不依赖 torch/YOLO）

适用：扁平化 UI、工具栏按钮、图标按钮——那些"没有文字标签"的控件。
速度：1080p 约 30-80ms（比 YOLO 更快，但泛化能力弱一些）

原理：
1. 灰度 + 自适应边缘（Canny）
2. 形态学闭运算把按钮边框连起来
3. 找轮廓 → 按矩形度/面积/宽高比筛选
4. 合并被切碎的相邻框
"""
import time
import cv2
import numpy as np
from typing import List, Dict, Any, Tuple


def detect_boxes(img: np.ndarray,
                 min_w: int = 12, min_h: int = 12,
                 max_w: int = 800, max_h: int = 600,
                 min_area: int = 200,
                 merge_gap: int = 6,
                 offset: Tuple[int, int] = (0, 0)) -> Tuple[List[Dict[str, Any]], float]:
    """检测可能的可点击元素

    返回 (boxes, elapsed_ms)
    boxes: [{'bbox':[x,y,w,h], 'center':[cx,cy], 'area':int, 'score':float}]
           坐标已加上 offset（屏幕绝对坐标）
    """
    t0 = time.time()
    ox, oy = offset
    if img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # 1) 边缘
    edges = cv2.Canny(gray, 30, 90)
    # 2) 闭运算连接断开的边框
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    # 3) 轮廓
    contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    raw = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < min_w or h < min_h or w > max_w or h > max_h:
            continue
        area = w * h
        if area < min_area:
            continue
        # 矩形度：轮廓面积 / 外接矩形面积
        ca = cv2.contourArea(c)
        rectness = ca / area if area else 0
        if rectness < 0.45:
            continue
        # 宽高比过滤（排除细长线）
        ar = w / max(1, h)
        if ar > 12 or ar < 0.08:
            continue
        raw.append([x, y, w, h, rectness])

    # 4) 合并重叠/相邻框
    merged = []
    used = [False] * len(raw)
    for i, a in enumerate(raw):
        if used[i]:
            continue
        x1, y1, w1, h1, s1 = a
        for j in range(i + 1, len(raw)):
            if used[j]:
                continue
            x2, y2, w2, h2, s2 = raw[j]
            # 包含关系或高度重叠
            if (x1 <= x2 and y1 <= y2 and x1 + w1 >= x2 + w2 and y1 + h1 >= y2 + h2):
                used[j] = True
            elif abs(x1 - x2) < merge_gap and abs(y1 - y2) < merge_gap and \
                 abs(w1 - w2) < merge_gap and abs(h1 - h2) < merge_gap:
                used[j] = True
            else:
                # 水平紧邻且同高（常见于分段按钮）
                if abs(y1 - y2) < 3 and abs(h1 - h2) < 3 and abs((x1 + w1) - x2) < 3:
                    x1, w1 = min(x1, x2), max(x1 + w1, x2 + w2) - min(x1, x2)
                    used[j] = True
        used[i] = True
        merged.append([x1, y1, w1, h1, s1])

    out = []
    for x, y, w, h, s in merged:
        out.append({
            "bbox": [int(x) + ox, int(y) + oy, int(w), int(h)],
            "center": [int(x + w / 2) + ox, int(y + h / 2) + oy],
            "area": int(w * h),
            "score": round(float(s), 2),
        })
    # 按位置排序（从上到下、从左到右）
    out.sort(key=lambda e: (e["bbox"][1] // 20, e["bbox"][0]))
    return out, (time.time() - t0) * 1000


def to_points(boxes: List[Dict[str, Any]], color=(0, 150, 255)) -> List[Dict[str, Any]]:
    """转成 capture.annotate 能用的点列表"""
    return [{
        "x": b["center"][0], "y": b["center"][1],
        "label": str(i + 1),
        "bbox": b["bbox"],
        "color": color,
    } for i, b in enumerate(boxes)]
