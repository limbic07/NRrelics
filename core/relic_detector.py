"""
遗物状态检测器
基于relic_detection_poc重构，用于仓库清理功能
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict


# 遗物状态常量
RELIC_STATE_LIGHT = "Light"
RELIC_STATE_DARK_FE = "FE"
RELIC_STATE_DARK_F = "F"
RELIC_STATE_DARK_E = "E"
RELIC_STATE_DARK_O = "O"


class RelicDetector:
    """遗物状态检测器"""

    def __init__(self, icon_cup_path: str = "icon_cup.png",
                 icon_bookmark_path: str = "icon_bookmark.png"):
        """
        初始化遗物检测器

        Args:
            icon_cup_path: 装备图标路径
            icon_bookmark_path: 收藏图标路径
        """
        # ROI 配置
        self.roi_start_x_ratio = 0.46
        self.roi_start_y_ratio = 0.19
        self.roi_width_ratio = 0.5
        self.roi_height_ratio = 0.49

        # 几何特征
        self.min_cursor_area = 2000
        self.max_cursor_area = 40000
        self.shape_aspect_ratio_min = 0.85
        self.shape_aspect_ratio_max = 1.15

        # 阈值
        self.canny_threshold1 = 50
        self.canny_threshold2 = 150
        self.brightness_threshold = 50
        self.brightness_center_ratio = 0.65
        self.template_match_threshold = 0.60
        self.icon_search_ratio = 0.35

        # 加载模板
        self.template_cup = self._load_template(icon_cup_path)
        self.template_bookmark = self._load_template(icon_bookmark_path)

    def _load_template(self, path: str) -> Optional[np.ndarray]:
        """加载模板图像"""
        if not Path(path).exists():
            print(f"[警告] 模板不存在: {path}")
            return None

        img = cv2.imread(path)
        if img is None:
            return None

        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def detect_cursor(self, image: np.ndarray) -> Tuple[Optional[Tuple], Optional[int]]:
        """
        检测光标位置

        Returns:
            (cursor_box, cursor_width) 或 (None, None)
        """
        h, w = image.shape[:2]
        rx = int(w * self.roi_start_x_ratio)
        ry = int(h * self.roi_start_y_ratio)
        rw = int(w * self.roi_width_ratio)
        rh = int(h * self.roi_height_ratio)
        rx, ry = max(0, rx), max(0, ry)
        rw, rh = min(w - rx, rw), min(h - ry, rh)

        roi_img = image[ry:ry+rh, rx:rx+rw]
        gray = cv2.cvtColor(roi_img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, self.canny_threshold1, self.canny_threshold2)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_cursor = None
        max_score = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_cursor_area or area > self.max_cursor_area:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
            if len(approx) == 4:
                x, y, cw, ch = cv2.boundingRect(approx)
                asp = float(cw) / ch
                if self.shape_aspect_ratio_min <= asp <= self.shape_aspect_ratio_max:
                    if area > max_score:
                        max_score = area
                        best_cursor = (x + rx, y + ry, cw, ch)

        if best_cursor:
            return best_cursor, best_cursor[2]
        return None, None

    def detect_state(self, image: np.ndarray) -> str:
        """
        检测遗物状态

        Returns:
            遗物状态: "Light", "FE", "F", "E", "O"
        """
        cursor_box, cursor_width = self.detect_cursor(image)

        if cursor_box is None:
            return RELIC_STATE_LIGHT  # 默认返回Light

        # 计算缩放因子
        scale_factor = cursor_width / 92.0

        # 检测详细状态
        result = self._detect_detailed_state(image, cursor_box, scale_factor)

        # 判断状态
        is_equipped = result['equipped']
        is_favorited = result['favorited']
        is_light = result['state'] == 'Light'

        if is_light:
            return RELIC_STATE_LIGHT
        elif is_favorited and is_equipped:
            return RELIC_STATE_DARK_FE
        elif is_favorited:
            return RELIC_STATE_DARK_F
        elif is_equipped:
            return RELIC_STATE_DARK_E
        else:
            return RELIC_STATE_DARK_O

    def _detect_detailed_state(self, image: np.ndarray, cursor_box: Tuple, scale_factor: float) -> Dict:
        """检测详细状态"""
        x, y, w, h = cursor_box
        padding = 2
        roi = image[y+padding : y+h-padding, x+padding : x+w-padding]

        if roi.size == 0:
            return {'state': 'Error', 'equipped': False, 'favorited': False, 'brightness': 0}

        roi_h, roi_w = roi.shape[:2]

        # 1. 定点图标搜索
        ratio = self.icon_search_ratio
        cup_w, cup_h = int(roi_w * ratio), int(roi_h * ratio)
        cup_zone = roi[0:cup_h, 0:cup_w]

        mark_x = int(roi_w * (1 - ratio))
        mark_w = roi_w - mark_x
        mark_h = int(roi_h * ratio)
        mark_zone = roi[0:mark_h, mark_x:roi_w]

        is_equipped, _ = self._match_icon(cup_zone, self.template_cup, scale_factor)
        is_favorited, _ = self._match_icon(mark_zone, self.template_bookmark, scale_factor)

        # 2. 亮度计算
        center_ratio = self.brightness_center_ratio
        offset_ratio = (1.0 - center_ratio) / 2.0

        cx = int(roi_w * offset_ratio)
        cy = int(roi_h * offset_ratio)
        cw = int(roi_w * center_ratio)
        ch = int(roi_h * center_ratio)

        center_roi = roi[cy:cy+ch, cx:cx+cw]

        if center_roi.size > 0:
            hsv = cv2.cvtColor(center_roi, cv2.COLOR_BGR2HSV)
            brightness = np.mean(hsv[:, :, 2])
        else:
            brightness = 0.0

        # 判断状态
        if is_equipped or is_favorited:
            state = 'Dark'
        elif brightness > self.brightness_threshold:
            state = 'Light'
        else:
            state = 'Dark'

        return {
            'state': state,
            'equipped': is_equipped,
            'favorited': is_favorited,
            'brightness': brightness
        }

    def _match_icon(self, search_img: np.ndarray, template: np.ndarray, scale: float) -> Tuple[bool, float]:
        """匹配图标"""
        if template is None or search_img.size == 0:
            return False, 0.0

        h, w = template.shape[:2]
        new_w, new_h = int(w * scale), int(h * scale)
        if new_w > search_img.shape[1] or new_h > search_img.shape[0] or new_w < 1:
            return False, 0.0

        scaled_tpl = cv2.resize(template, (new_w, new_h))
        search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(search_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        return max_val > self.template_match_threshold, float(max_val)
