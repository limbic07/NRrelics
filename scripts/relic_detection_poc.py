"""
遗物状态检测 - 最终完善版 (Final V2)
更新日志：
1. 【优化】亮度采样区域扩大至 65% (BRIGHTNESS_CENTER_RATIO)，避免局部噪点干扰。
2. 【保留】定点图标搜索 (Targeted ROI)，识别非常精准。
3. 【保留】无掩码相关系数匹配 (CCOEFF)，适应性强。
"""

import cv2
import numpy as np
import pyautogui
import keyboard
import time
from pathlib import Path
from typing import Tuple, Optional, Dict, List
from collections import deque

class Config:
    DEBUG_MODE = True

    # 1. ROI 配置
    ROI_START_X_RATIO = 0.46
    ROI_START_Y_RATIO = 0.19
    ROI_WIDTH_RATIO = 0.5
    ROI_HEIGHT_RATIO = 0.49

    # 2. 几何特征
    MIN_CURSOR_AREA = 500
    MAX_CURSOR_AREA = 40000
    SHAPE_ASPECT_RATIO_MIN = 0.85  # 光标是正方形
    SHAPE_ASPECT_RATIO_MAX = 1.15

    # 3. 时域最大值投影参数
    TEMPORAL_FRAME_COUNT = 5  # 缓存帧数（N）
    CANNY_THRESHOLD1 = 30    # Canny低阈值
    CANNY_THRESHOLD2 = 100   # Canny高阈值

    # 4. 亮度配置
    BRIGHTNESS_THRESHOLD = 45
    BRIGHTNESS_CENTER_RATIO = 0.55

    # 5. 匹配阈值
    TEMPLATE_MATCH_THRESHOLD = 0.60
    ICON_SEARCH_RATIO = 0.35

class RelicDetector:
    def __init__(self, icon_cup_path: str = "data/icon_cup.png",
                 icon_bookmark_path: str = "data/icon_bookmark.png"):
        self.config = Config()
        print(f"[初始化] 加载模板...")
        self.template_cup = self._load_template_simple(icon_cup_path)
        self.template_bookmark = self._load_template_simple(icon_bookmark_path)

        # 时域最大值投影缓冲区
        self.frame_buffer = deque(maxlen=self.config.TEMPORAL_FRAME_COUNT)

    def _load_template_simple(self, path: str) -> Optional[np.ndarray]:
        if not Path(path).exists():
            print(f"[警告] 模板不存在: {path}")
            return None
        img = cv2.imread(path)
        if img is None: return None
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def detect_cursor(self, image: np.ndarray) -> Tuple[Optional[Tuple], Optional[int], Optional[Tuple]]:
        """
        检测光标位置
        使用时域最大值投影 + Canny边缘检测
        """
        h, w = image.shape[:2]
        rx = int(w * self.config.ROI_START_X_RATIO)
        ry = int(h * self.config.ROI_START_Y_RATIO)
        rw = int(w * self.config.ROI_WIDTH_RATIO)
        rh = int(h * self.config.ROI_HEIGHT_RATIO)
        rx, ry = max(0, rx), max(0, ry)
        rw, rh = min(w - rx, rw), min(h - ry, rh)

        roi_img = image[ry:ry+rh, rx:rx+rw]

        # 转换到HSV空间，使用V通道（亮度）
        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]

        # 添加当前帧到缓冲区
        self.frame_buffer.append(v_channel)

        # 计算时域最大值投影
        if len(self.frame_buffer) > 0:
            max_projection = self._compute_temporal_max_projection()
        else:
            max_projection = v_channel

        # 高斯模糊去噪
        blurred = cv2.GaussianBlur(max_projection, (5, 5), 0)

        # Canny边缘检测
        edges = cv2.Canny(blurred, self.config.CANNY_THRESHOLD1, self.config.CANNY_THRESHOLD2)

        # 形态学处理：连接相邻的边缘
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=2)

        # 查找轮廓
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 从右下角开始寻找光标（优先考虑下方，然后考虑右方）
        best_cursor = None
        max_position_score = -1

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.config.MIN_CURSOR_AREA or area > self.config.MAX_CURSOR_AREA:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4:
                x, y, cw, ch = cv2.boundingRect(approx)
                asp = float(cw) / ch if ch > 0 else 0
                if self.config.SHAPE_ASPECT_RATIO_MIN <= asp <= self.config.SHAPE_ASPECT_RATIO_MAX:
                    position_score = y * 10000 + x
                    if position_score > max_position_score:
                        max_position_score = position_score
                        best_cursor = (x + rx, y + ry, cw, ch)

        if best_cursor:
            return best_cursor, best_cursor[2], (rx, ry)
        return None, None, (rx, ry)

    def _compute_temporal_max_projection(self) -> np.ndarray:
        """
        计算时域最大值投影
        将缓冲区中所有帧沿时间维度求最大值
        """
        if len(self.frame_buffer) == 0:
            return np.zeros((1, 1), dtype=np.uint8)

        # 将所有帧堆叠成3D数组 (height, width, frames)
        frame_stack = np.stack(list(self.frame_buffer), axis=2)

        # 沿时间维度（axis=2）求最大值
        max_projection = np.max(frame_stack, axis=2)

        return max_projection.astype(np.uint8)

    def detect_state(self, image: np.ndarray, cursor_box: Tuple, scale_factor: float) -> Dict:
        x, y, w, h = cursor_box
        padding = 2
        roi = image[y+padding : y+h-padding, x+padding : x+w-padding]
        
        if roi.size == 0: 
            return {'state': 'Error', 'equipped': False, 'favorited': False, 'brightness': 0, 
                    'score_cup': 0, 'score_mark': 0}

        roi_h, roi_w = roi.shape[:2]
        
        # 1. 定点图标搜索
        ratio = self.config.ICON_SEARCH_RATIO
        cup_w, cup_h = int(roi_w * ratio), int(roi_h * ratio)
        cup_zone = roi[0:cup_h, 0:cup_w]
        
        mark_x = int(roi_w * (1 - ratio))
        mark_w = roi_w - mark_x
        mark_h = int(roi_h * ratio)
        mark_zone = roi[0:mark_h, mark_x:roi_w]

        is_equipped, score_cup = self._match_icon(cup_zone, self.template_cup, scale_factor)
        is_favorited, score_mark = self._match_icon(mark_zone, self.template_bookmark, scale_factor)

        # === 2. 亮度计算 (扩大到 65% 区域) ===
        center_ratio = self.config.BRIGHTNESS_CENTER_RATIO
        offset_ratio = (1.0 - center_ratio) / 2.0 # (1 - 0.65) / 2 = 0.175
        
        cx = int(roi_w * offset_ratio)
        cy = int(roi_h * offset_ratio)
        cw = int(roi_w * center_ratio)
        ch = int(roi_h * center_ratio)
        
        center_roi = roi[cy:cy+ch, cx:cx+cw]
        
        # 防止计算区域出错
        if center_roi.size > 0:
            hsv = cv2.cvtColor(center_roi, cv2.COLOR_BGR2HSV)
            brightness = np.mean(hsv[:, :, 2])
        else:
            brightness = 0.0

        if is_equipped or is_favorited:
            state = 'Dark'
        elif brightness > self.config.BRIGHTNESS_THRESHOLD:
            state = 'Light'
        else:
            state = 'Dark'

        # 调试框坐标
        debug_cup_rect = (x + padding, y + padding, cup_w, cup_h)
        debug_mark_rect = (x + padding + mark_x, y + padding, mark_w, mark_h)
        debug_lum_rect = (x + padding + cx, y + padding + cy, cw, ch)

        return {
            'state': state, 'equipped': is_equipped, 'favorited': is_favorited,
            'brightness': brightness, 'score_cup': score_cup, 'score_mark': score_mark,
            'center_rect': debug_lum_rect,
            'debug_cup_rect': debug_cup_rect,
            'debug_mark_rect': debug_mark_rect
        }

    def _match_icon(self, search_img: np.ndarray, template: np.ndarray, scale: float) -> Tuple[bool, float]:
        if template is None or search_img.size == 0: return False, 0.0
        h, w = template.shape[:2]
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w > search_img.shape[1] or new_h > search_img.shape[0] or new_w < 1: 
            return False, 0.0
        
        scaled_tpl = cv2.resize(template, (new_w, new_h))
        search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(search_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return max_val > self.config.TEMPLATE_MATCH_THRESHOLD, float(max_val)

    def process(self, image: np.ndarray) -> Tuple[np.ndarray, Dict]:
        output = image.copy()
        cursor_box, cursor_width, roi_offset = self.detect_cursor(image)

        if roi_offset:
            rx, ry = roi_offset
            rh = int(image.shape[0] * self.config.ROI_HEIGHT_RATIO)
            rw = int(image.shape[1] * self.config.ROI_WIDTH_RATIO)
            cv2.rectangle(output, (rx, ry), (rx+rw, ry+rh), (255, 0, 0), 1)

        if cursor_box is None: return output, {'error': 'Cursor not found'}

        current_scale = cursor_width / 92.0
        result = self.detect_state(image, cursor_box, current_scale)
        
        x, y, w, h = cursor_box
        color = (0, 255, 0) if result['state'] == 'Light' else (0, 0, 255)
        cv2.rectangle(output, (x, y), (x+w, y+h), color, 2)
        
        # === 绘制调试框 ===
        # 1. 亮度框 (黄色，现在是 65% 大小)
        if 'center_rect' in result:
            cx, cy, cw, ch = result['center_rect']
            cv2.rectangle(output, (cx, cy), (cx+cw, cy+ch), (0, 255, 255), 1)
        
        # 2. 搜索框 (紫色)
        if self.config.DEBUG_MODE:
            if 'debug_cup_rect' in result:
                cx, cy, cw, ch = result['debug_cup_rect']
                cv2.rectangle(output, (cx, cy), (cx+cw, cy+ch), (255, 0, 255), 1)
            if 'debug_mark_rect' in result:
                mx, my, mw, mh = result['debug_mark_rect']
                cv2.rectangle(output, (mx, my), (mw, mh) if mw<10 else (mx+mw, my+mh), (255, 0, 255), 1)

        label = result['state']
        if result['equipped']: label += " (E)"
        if result['favorited']: label += " (F)"
        cv2.putText(output, label, (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if self.config.DEBUG_MODE:
            lines = [
                f"Lum: {result['brightness']:.1f}",
                f"Cup: {result['score_cup']:.2f}",
                f"Fav: {result['score_mark']:.2f}",
                f"Scl: {current_scale:.2f}x"
            ]
            panel_y = y + h + 5
            if panel_y + 80 > output.shape[0]: panel_y = y - 80
            cv2.rectangle(output, (x, panel_y), (x+160, panel_y+85), (0,0,0), -1)
            for i, line in enumerate(lines):
                c = (200,200,200)
                if "Lum" in line and result['brightness'] > self.config.BRIGHTNESS_THRESHOLD: c = (0,255,255)
                if ("Cup" in line and result['equipped']) or ("Fav" in line and result['favorited']): c = (0,255,0)
                cv2.putText(output, line, (x+5, panel_y + 20 + i*20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, c, 1)

        return output, result

def main():
    detector = RelicDetector()
    print("等待 F11...")
    keyboard.wait('f11')
    while not keyboard.is_pressed('esc'):
        screenshot = pyautogui.screenshot()
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        out, _ = detector.process(img)
        dh, dw = out.shape[:2]
        scale = 720/dh
        cv2.imshow("Result (Final V2)", cv2.resize(out, (int(dw*scale), int(dh*scale))))
        cv2.waitKey(1)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()