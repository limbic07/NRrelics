"""
遗物状态检测器
基于relic_detection_poc重构，用于仓库清理功能
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict
from collections import deque


# 遗物状态常量
RELIC_STATE_LIGHT = "Light"
RELIC_STATE_DARK_FE = "FE"
RELIC_STATE_DARK_F = "F"
RELIC_STATE_DARK_E = "E"
RELIC_STATE_DARK_O = "O"

# 光标检测参数
CURSOR_ROI_START_X_RATIO = 0.46
CURSOR_ROI_START_Y_RATIO = 0.19
CURSOR_ROI_WIDTH_RATIO = 0.5
CURSOR_ROI_HEIGHT_RATIO = 0.49
CURSOR_MIN_AREA = 500
CURSOR_MAX_AREA = 40000
CURSOR_ASPECT_RATIO_MIN = 0.8
CURSOR_ASPECT_RATIO_MAX = 1.2
CANNY_THRESHOLD1 = 80
CANNY_THRESHOLD2 = 150
TEMPORAL_FRAME_COUNT = 5


class RelicDetector:
    """遗物状态检测器"""

    def __init__(self, icon_cup_path: str = "data/icon_cup.png",
                 icon_bookmark_path: str = "data/icon_bookmark.png",
                 temporal_frame_count: int = TEMPORAL_FRAME_COUNT,
                 canny_threshold1: int = CANNY_THRESHOLD1,
                 canny_threshold2: int = CANNY_THRESHOLD2):
        """
        初始化遗物检测器

        Args:
            icon_cup_path: 装备图标路径
            icon_bookmark_path: 收藏图标路径
            temporal_frame_count: 时域最大值投影的帧缓存数量（N）
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

        # 时域最大值投影参数
        self.temporal_frame_count = temporal_frame_count
        self.frame_buffer = deque(maxlen=temporal_frame_count)

        # Canny边缘检测参数
        self.canny_threshold1 = canny_threshold1
        self.canny_threshold2 = canny_threshold2
        self.brightness_threshold = 45
        self.brightness_center_ratio = 0.55
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

    def detect_cursor(self, image: np.ndarray, scale_x: float = 1.0, scale_y: float = 1.0) -> Tuple[Optional[Tuple], Optional[int]]:
        """
        检测光标位置（从右下角开始寻找，避免误识别已选中的遗物）
        使用时域最大值投影 + Canny边缘检测

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

        # 保存原始 ROI 图像
        cv2.imwrite("debug_01_roi_original.png", roi_img)
        print(f"[光标检测] 已保存原始 ROI: debug_01_roi_original.png")

        # 转换到HSV空间，使用V通道（亮度）
        hsv = cv2.cvtColor(roi_img, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]

        # 保存 V 通道
        cv2.imwrite("debug_02_v_channel.png", v_channel)
        print(f"[光标检测] 已保存 V 通道: debug_02_v_channel.png")

        # 添加当前帧到缓冲区
        self.frame_buffer.append(v_channel)

        # 计算时域最大值投影
        if len(self.frame_buffer) > 0:
            max_projection = self._compute_temporal_max_projection()
        else:
            max_projection = v_channel

        # 保存时域最大值投影图像
        cv2.imwrite("debug_03_temporal_max_projection.png", max_projection)
        print(f"[光标检测] 已保存时域最大值投影: debug_03_temporal_max_projection.png")
        print(f"[光标检测] 帧缓冲区大小: {len(self.frame_buffer)}")

        # 高斯模糊去噪
        blurred = cv2.GaussianBlur(max_projection, (5, 5), 0)
        cv2.imwrite("debug_04_blurred.png", blurred)
        print(f"[光标检测] 已保存高斯模糊: debug_04_blurred.png")

        # Canny边缘检测
        edges = cv2.Canny(blurred, self.canny_threshold1, self.canny_threshold2)
        cv2.imwrite("debug_05_edges_canny.png", edges)
        print(f"[光标检测] 已保存 Canny 边缘: debug_05_edges_canny.png (阈值: {self.canny_threshold1}, {self.canny_threshold2})")

        # 直接使用 Canny 边缘检测结果，不进行膨胀操作
        # 查找轮廓
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        print(f"[光标检测] ROI: ({rx},{ry}) 大小: {rw}x{rh}, 找到 {len(contours)} 个轮廓")

        # 从右下角开始寻找光标（优先考虑下方，然后考虑右方）
        best_cursor = None
        max_position_score = -1  # 位置得分：优先Y坐标（下），然后X坐标（右）

        for i, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            x, y, cw, ch = cv2.boundingRect(cnt)
            asp = float(cw) / ch if ch > 0 else 0

            print(f"  轮廓{i}: 面积={area:.0f}, 位置=({x},{y}), 尺寸={cw}x{ch}, 宽高比={asp:.2f}")

            if area < self.min_cursor_area or area > self.max_cursor_area:
                print(f"    → 面积不符合 ({self.min_cursor_area}-{self.max_cursor_area})")
                continue

            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)

            if len(approx) != 4:
                print(f"    → 不是四边形 (顶点数={len(approx)})")
                continue

            if not (self.shape_aspect_ratio_min <= asp <= self.shape_aspect_ratio_max):
                print(f"    → 宽高比不符合 ({self.shape_aspect_ratio_min}-{self.shape_aspect_ratio_max})")
                continue

            position_score = y * 10000 + x
            print(f"    → ✓ 有效候选，位置得分={position_score}")

            if position_score > max_position_score:
                max_position_score = position_score
                best_cursor = (x + rx, y + ry, cw, ch)

        if best_cursor:
            print(f"[光标检测] ✓ 检测到光标: 位置({best_cursor[0]}, {best_cursor[1]}), 尺寸({best_cursor[2]}x{best_cursor[3]})")

            # 保存带有检测结果的可视化图像
            vis_img = cv2.cvtColor(max_projection, cv2.COLOR_GRAY2BGR)
            x, y, cw, ch = best_cursor[0] - rx, best_cursor[1] - ry, best_cursor[2], best_cursor[3]
            cv2.rectangle(vis_img, (x, y), (x + cw, y + ch), (0, 255, 0), 2)
            cv2.putText(vis_img, f"Cursor: {cw}x{ch}", (x, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            cv2.imwrite("debug_06_cursor_detected.png", vis_img)
            print(f"[光标检测] 已保存检测结果: debug_06_cursor_detected.png")

            return best_cursor, best_cursor[2]

        print(f"[光标检测] ✗ 未检测到光标")

        # 保存所有候选的可视化图像
        vis_img = cv2.cvtColor(max_projection, cv2.COLOR_GRAY2BGR)
        for i, cnt in enumerate(contours):
            x, y, cw, ch = cv2.boundingRect(cnt)
            cv2.rectangle(vis_img, (x, y), (x + cw, y + ch), (0, 0, 255), 1)
        cv2.imwrite("debug_07_all_contours.png", vis_img)
        print(f"[光标检测] 已保存所有轮廓: debug_07_all_contours.png")

        return None, None

    def _compute_temporal_max_projection(self) -> np.ndarray:
        """
        计算时域最大值投影
        将缓冲区中所有帧沿时间维度求最大值

        Returns:
            最大值投影图像
        """
        if len(self.frame_buffer) == 0:
            return np.zeros((1, 1), dtype=np.uint8)

        # 将所有帧堆叠成3D数组 (height, width, frames)
        frame_stack = np.stack(list(self.frame_buffer), axis=2)

        # 沿时间维度（axis=2）求最大值
        max_projection = np.max(frame_stack, axis=2)

        return max_projection.astype(np.uint8)

    def detect_state(self, image: np.ndarray, resolution_scale: float = 1.0, scale_x: float = 1.0, scale_y: float = 1.0) -> str:
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
        cursor_box, cursor_width = self.detect_cursor(image, scale_x, scale_y)

        if cursor_box is None:
            print("[调试] 未检测到光标，返回 Light 状态")
            return RELIC_STATE_LIGHT  # 默认返回Light

        # 使用光标宽度计算缩放因子（回归之前的方式）
        scale_factor = cursor_width / 92.0 if cursor_width else 1.0

        print(f"[调试] 光标宽度: {cursor_width}, 计算缩放因子: {scale_factor:.4f}")

        # 检测详细状态
        result = self._detect_detailed_state(image, cursor_box, scale_factor)

        print(f"[调试] 状态检测结果: state={result['state']}, equipped={result['equipped']}, favorited={result['favorited']}, brightness={result['brightness']:.2f}")

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

        print(f"[状态检测] 光标框: ({x},{y}) 尺寸: {w}x{h}")

        if roi.size == 0:
            print(f"[状态检测] ✗ ROI为空")
            return {'state': 'Error', 'equipped': False, 'favorited': False, 'brightness': 0}

        roi_h, roi_w = roi.shape[:2]
        print(f"[状态检测] ROI尺寸: {roi_w}x{roi_h}")

        # 1. 定点图标搜索
        ratio = self.icon_search_ratio
        cup_w, cup_h = int(roi_w * ratio), int(roi_h * ratio)
        cup_zone = roi[0:cup_h, 0:cup_w]

        mark_x = int(roi_w * (1 - ratio))
        mark_w = roi_w - mark_x
        mark_h = int(roi_h * ratio)
        mark_zone = roi[0:mark_h, mark_x:roi_w]

        print(f"[状态检测] 装备图标区域: {cup_w}x{cup_h}, 收藏图标区域: {mark_w}x{mark_h}")

        is_equipped, score_cup = self._match_icon(cup_zone, self.template_cup, scale_factor, "装备")
        is_favorited, score_mark = self._match_icon(mark_zone, self.template_bookmark, scale_factor, "收藏")

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

        print(f"[状态检测] 亮度: {brightness:.1f} (阈值: {self.brightness_threshold})")

        # 判断状态
        if is_equipped or is_favorited:
            state = 'Dark'
        elif brightness > self.brightness_threshold:
            state = 'Light'
        else:
            state = 'Dark'

        print(f"[状态检测] 最终状态: {state}, 装备: {is_equipped}, 收藏: {is_favorited}")

        return {
            'state': state,
            'equipped': is_equipped,
            'favorited': is_favorited,
            'brightness': brightness
        }

    def _match_icon(self, search_img: np.ndarray, template: np.ndarray, scale: float, icon_name: str = "") -> Tuple[bool, float]:
        """匹配图标"""
        if template is None or search_img.size == 0:
            print(f"[图标匹配] {icon_name}: 模板或搜索区域为空")
            return False, 0.0

        h, w = template.shape[:2]
        new_w, new_h = int(w * scale), int(h * scale)

        print(f"[图标匹配] {icon_name}: 原始模板尺寸={w}x{h}, 缩放因子={scale:.4f}, 缩放后={new_w}x{new_h}, 搜索区域={search_img.shape[1]}x{search_img.shape[0]}")

        if new_w > search_img.shape[1] or new_h > search_img.shape[0] or new_w < 1:
            print(f"[图标匹配] {icon_name}: ✗ 缩放后尺寸不合法")
            return False, 0.0

        scaled_tpl = cv2.resize(template, (new_w, new_h))
        search_gray = cv2.cvtColor(search_img, cv2.COLOR_BGR2GRAY)
        res = cv2.matchTemplate(search_gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)

        is_matched = max_val > self.template_match_threshold

        print(f"[图标匹配] {icon_name}: 匹配度={max_val:.4f}, 阈值={self.template_match_threshold}, 结果={'✓ 匹配' if is_matched else '✗ 不匹配'}")

        return is_matched, float(max_val)
