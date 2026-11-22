"""
遗物状态检测器
基于relic_detection_poc重构，用于仓库清理功能
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict
from core.utils import get_resource_path, log_debug



# 遗物状态常量
RELIC_STATE_UNKNOWN = "Unknown"
RELIC_STATE_LIGHT = "Light" #有单件售价、可自由操作
RELIC_STATE_DARK_FE = "FE"  #已装备且已收藏
RELIC_STATE_DARK_F = "F"    #仅已收藏
RELIC_STATE_DARK_E = "E"    #仅已装备
RELIC_STATE_DARK_O = "O"    #详情中没有单件售价

# 光标检测参数
CURSOR_ROI_START_X_RATIO = 0.46
CURSOR_ROI_START_Y_RATIO = 0.19
CURSOR_ROI_WIDTH_RATIO = 0.5
CURSOR_ROI_HEIGHT_RATIO = 0.49
CURSOR_MIN_AREA = 500
CURSOR_MAX_AREA = 40000
CURSOR_ASPECT_RATIO_MIN = 0.85
CURSOR_ASPECT_RATIO_MAX = 1.15
CANNY_THRESHOLD1 = 80
CANNY_THRESHOLD2 = 150


class RelicDetector:
    """遗物状态检测器"""

    def __init__(self, icon_cup_path: str = "data/icon_cup.png",
                 icon_bookmark_path: str = "data/icon_bookmark.png",
                 canny_threshold1: int = CANNY_THRESHOLD1,
                 canny_threshold2: int = CANNY_THRESHOLD2):
        """
        初始化遗物检测器

        Args:
            icon_cup_path: 装备图标路径
            icon_bookmark_path: 收藏图标路径
            canny_threshold1: Canny低阈值
            canny_threshold2: Canny高阈值
        """
        # ROI 配置
        self.roi_start_x_ratio = CURSOR_ROI_START_X_RATIO
        self.roi_start_y_ratio = CURSOR_ROI_START_Y_RATIO
        self.roi_width_ratio = CURSOR_ROI_WIDTH_RATIO
        self.roi_height_ratio = CURSOR_ROI_HEIGHT_RATIO

        # 几何特征
        self.min_cursor_area = CURSOR_MIN_AREA
        self.max_cursor_area = CURSOR_MAX_AREA
        self.shape_aspect_ratio_min = CURSOR_ASPECT_RATIO_MIN
        self.shape_aspect_ratio_max = CURSOR_ASPECT_RATIO_MAX

        # Canny边缘检测参数
        self.canny_threshold1 = canny_threshold1
        self.canny_threshold2 = canny_threshold2
        self.experimental_navigation = False
        self.template_match_threshold = 0.60
        self.icon_search_ratio = 0.35

        # 加载模板
        self.template_price = self._load_template("data/icon_sale_currency.png")
        self.template_cup = self._load_template(icon_cup_path)
        self.template_bookmark = self._load_template(icon_bookmark_path)

    def _load_template(self, path: str) -> Optional[np.ndarray]:
        """加载模板图像"""
        # 处理资源路径
        abs_path = get_resource_path(path)
        
        if not Path(abs_path).exists():
            log_debug(f"[警告] 模板不存在: {abs_path}")
            return None

        try:
            img = cv2.imdecode(np.frombuffer(Path(abs_path).read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        except (OSError, cv2.error) as exc:
            log_debug(f"[警告] 模板读取失败: {abs_path}: {exc}")
            return None
        if img is None:
            log_debug(f"[警告] 模板无法解码: {abs_path}")
            return None

        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def detect_cursor(self, image: np.ndarray, scale_x: float = 1.0, scale_y: float = 1.0) -> Tuple[Optional[Tuple], Optional[int]]:
        """
        检测光标位置。顺序清理时已选中的方框只在当前光标之前，
        因此取最下行、同一行最右侧的仓库格子候选。
        呼吸亮度会改变轮廓面积，面积仅用于同一格内选择外框。

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

        # 转换到HSV空间，使用V通道（亮度）
        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]

        # 高斯模糊去噪
        blurred = cv2.GaussianBlur(v_channel, (5, 5), 0)

        # Canny边缘检测
        edges = cv2.Canny(blurred, self.canny_threshold1, self.canny_threshold2)

        # 查找轮廓
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 先识别仓库格子，排除列表外的近似方框。
        # 坐标以 1920x1080 客户区为基准，与仓库导航一致。
        best_cursor = None
        best_score = (-1, -1, -1)
        unit_x, unit_y = w / 1920, h / 1080

        for cnt in contours:
            area = cv2.contourArea(cnt)
            x, y, cw, ch = cv2.boundingRect(cnt)
            asp = float(cw) / ch if ch > 0 else 0

            if area < self.min_cursor_area or area > self.max_cursor_area:
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)

            if len(approx) != 4:
                if not self.experimental_navigation:
                    continue
                # 高亮边框可能与图标边缘粘连；只接受接近完整格子的轮廓。
                if not (0.85 * 92 * unit_x <= cw <= 1.15 * 92 * unit_x
                        and 0.85 * 94 * unit_y <= ch <= 1.15 * 94 * unit_y
                        and area / (cw * ch) >= 0.75):
                    continue

            if not (self.shape_aspect_ratio_min <= asp <= self.shape_aspect_ratio_max):
                continue

            abs_x, abs_y = x + rx, y + ry
            column = round((abs_x / unit_x - 928) / 110)
            row = round((abs_y / unit_y - 209) / 106)
            if not (0 <= column < 8 and 0 <= row < 5):
                continue
            if (abs(abs_x / unit_x - (928 + 110 * column)) > 22
                    or abs(abs_y / unit_y - (209 + 106 * row)) > 22):
                continue

            score = (row, column, area)

            if score > best_score:
                best_score = score
                best_cursor = (abs_x, abs_y, cw, ch)

        if best_cursor:
            return best_cursor, best_cursor[2]

        return None, None

    def detect_state(self, image: np.ndarray, resolution_scale: float = 1.0,
                     scale_x: float = 1.0, scale_y: float = 1.0,
                     cursor_box: Optional[Tuple] = None) -> str:
        """
        检测遗物状态

        Args:
            image: 游戏窗口截图
            resolution_scale: 分辨率缩放因子（当前分辨率 / 基准分辨率）
            scale_x: X轴缩放因子
            scale_y: Y轴缩放因子

        Returns:
            遗物状态: "Light", "FE", "F", "E", "O"
        """
        try:
            if image is None or image.size == 0:
                return RELIC_STATE_UNKNOWN
            if cursor_box is None:
                cursor_box, cursor_width = self.detect_cursor(image, scale_x, scale_y)
            else:
                cursor_width = cursor_box[2]
            if cursor_box is None or not cursor_width:
                return RELIC_STATE_UNKNOWN
            has_price = self._has_sale_price(image)
            if has_price is None:
                return RELIC_STATE_UNKNOWN
            if not has_price:
                return RELIC_STATE_DARK_O
            if self.template_cup is None or self.template_bookmark is None:
                return RELIC_STATE_UNKNOWN
            scale_factor = cursor_width / 92.0
            result = self._detect_detailed_state(image, cursor_box, scale_factor)
            if result.get('state') not in ('Light', 'Dark'):
                return RELIC_STATE_UNKNOWN
        except Exception as exc:
            log_debug(f"[警告] 遗物状态检测失败: {exc}")
            return RELIC_STATE_UNKNOWN

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

    def _has_sale_price(self, image: np.ndarray) -> Optional[bool]:
        """单件售价包含货币图标和数字。详情未加载或两种信号不一致时返回未知。"""
        h, w = image.shape[:2]

        def gray_region(x1, y1, x2, y2):
            region = image[round(y1*h/1080):round(y2*h/1080),
                           round(x1*w/1920):round(x2*w/1920)]
            return cv2.resize(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY), (x2-x1, y2-y1))

        if self.template_price is None:
            return None
        currency = gray_region(928, 893, 965, 931)
        score = cv2.matchTemplate(currency, self.template_price, cv2.TM_CCOEFF_NORMED).max()
        digits = gray_region(991, 897, 1055, 925)
        # 金额右对齐。用笔画相对局部背景的对比度，不依赖遗物图案的明暗。
        has_digits = np.percentile(digits, 96) - np.median(digits) > 26
        if score > 0.55 and has_digits:
            return True
        if score > 0.40 or has_digits:
            return None
        title = gray_region(1074, 773, 1280, 799)
        if np.percentile(title, 96) - np.median(title) > 26:
            return False
        return None

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

        is_equipped, score_cup = self._match_icon(cup_zone, self.template_cup, scale_factor)
        is_favorited, score_mark = self._match_icon(mark_zone, self.template_bookmark, scale_factor)

        if is_equipped is None or is_favorited is None:
            return {'state': RELIC_STATE_UNKNOWN, 'equipped': is_equipped,
                    'favorited': is_favorited, 'brightness': 0}

        return {
            'state': 'Dark' if is_equipped or is_favorited else 'Light',
            'equipped': is_equipped,
            'favorited': is_favorited,
        }

    def _match_icon(self, search_img: np.ndarray, template: np.ndarray, scale: float) -> Tuple[Optional[bool], float]:
        """Match an icon; None means unavailable, False means a completed negative."""
        if (template is None or template.size == 0 or template.ndim != 2
                or search_img is None or search_img.size == 0 or search_img.ndim != 3
                or search_img.shape[2] != 3 or not np.isfinite(scale) or scale <= 0):
            return None, 0.0

        h, w = template.shape[:2]
        scaled_w, scaled_h = w * scale, h * scale
        if not np.isfinite(scaled_w) or not np.isfinite(scaled_h):
            return None, 0.0
        new_w, new_h = int(scaled_w), int(scaled_h)

        if (new_w > search_img.shape[1] or new_h > search_img.shape[0]
                or new_w < 1 or new_h < 1):
            return None, 0.0

        scaled_tpl = cv2.resize(template, (new_w, new_h))
        search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(search_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)

        is_matched = max_val > self.template_match_threshold

        return is_matched, float(max_val)
