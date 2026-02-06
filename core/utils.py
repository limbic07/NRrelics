# --- START OF FILE utils.py ---
import sys
import os
import time
import difflib
import unicodedata
import ctypes
from ctypes import windll, byref, Structure, c_long
import cv2
import numpy as np
import mss
from rapidocr_onnxruntime import RapidOCR

# ================= 配置区域 =================
DEBUG_MODE = True

KEYS = {
    'interact': 'f',
    'sell': '3',
    'fav': '2',
    'move_right': 'right',
    'move_left': 'left',
    'move_down': 'down',
    'move_up': 'up',
    'stop': 'f11'
}

FUZZY_THRESHOLD = 0.7
CORRECTION_THRESHOLD = 0.55

SPECIAL_RELIC_NAMES = [
    "头冠的徽章",
    "安定的遗志"
]

# === 视觉参数基准 (基于 2560x1440) ===
REF_SCREEN_HEIGHT = 1440
REF_GRID_WIDTH = 128
REF_GRID_HEIGHT = 128
REF_OFFSET_Y = 3
REF_OFFSET_X = 23


# ================= 路径与基础工具 =================
def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_app_config_path():
    local_app_data = os.getenv('LOCALAPPDATA') or os.path.expanduser("~")
    config_dir = os.path.join(local_app_data, "NRrelic_bot")
    if not os.path.exists(config_dir): os.makedirs(config_dir)
    return os.path.join(config_dir, "bot_config.json")


def get_user_settings_path():
    local_app_data = os.getenv('LOCALAPPDATA') or os.path.expanduser("~")
    config_dir = os.path.join(local_app_data, "NRrelic_bot")
    if not os.path.exists(config_dir): os.makedirs(config_dir)
    return os.path.join(config_dir, "user_settings.json")


def normalize_text(text):
    if not text: return ""
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('【', '[').replace('】', ']').replace('□', '[').replace('■', '[')
    text = text.replace('十', '+').replace('土', '+')
    text = text.replace('陷人', '陷入').replace('碱', '减')
    text = text.replace('+41', '+4').replace('+31', '+3').replace('+21', '+2').replace('+11', '+1')
    text = text.replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '')
    return text


def find_best_match_in_library(ocr_line, library):
    if not ocr_line or len(ocr_line) < 2: return None, 0.0
    if ocr_line in library: return ocr_line, 1.0
    best_ratio = 0.0
    best_text = None
    ocr_set = set(ocr_line)
    ocr_len = len(ocr_line)
    for item in library:
        item_len = len(item)
        if abs(item_len - ocr_len) > 2: continue
        common_chars = 0
        for char in item:
            if char in ocr_set: common_chars += 1
        if common_chars < max(item_len, ocr_len) * 0.6: continue
        ratio = difflib.SequenceMatcher(None, ocr_line, item).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_text = item
    return best_text, best_ratio


# ================= 数据加载 =================
class DataLoader:
    @staticmethod
    def load_txt(filename):
        real_path = get_resource_path(filename)
        if not os.path.exists(real_path): return []
        with open(real_path, 'r', encoding='utf-8') as f:
            lines = set()
            for line in f.readlines():
                clean = normalize_text(line)
                if clean: lines.add(clean)
            return sorted(list(lines))

    @staticmethod
    def get_data():
        return (DataLoader.load_txt("../data/normal.txt"),
                DataLoader.load_txt("../data/deepnight_pos.txt"),
                DataLoader.load_txt("../data/deepnight_neg.txt"))

    @staticmethod
    def get_master_library():
        n = DataLoader.load_txt("../data/normal.txt")
        dp = DataLoader.load_txt("../data/deepnight_pos.txt")
        dn = DataLoader.load_txt("../data/deepnight_neg.txt")
        return sorted(list(set(n + dp + dn)))


# ================= 性能分析 =================
class Profiler:
    def __init__(self):
        self.records = {}
        self.start_times = {}

    def start(self, tag):
        if not DEBUG_MODE: return
        self.start_times[tag] = time.perf_counter()

    def end(self, tag):
        if not DEBUG_MODE: return
        if tag in self.start_times:
            duration = (time.perf_counter() - self.start_times[tag]) * 1000
            self.records[tag] = duration

    def print_report(self):
        if not DEBUG_MODE: return
        print("\n⚡ [Perf] (ms): ", end="")
        for tag, duration in self.records.items():
            print(f"{tag}:{duration:.1f} ", end="")
        print("")


# ================= 窗口管理 =================
class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]


class WindowMgr:
    @staticmethod
    def is_game_active():
        try:
            hwnd = windll.user32.GetForegroundWindow()
            length = windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            return "ELDEN RING NIGHTREIGN" in buff.value
        except:
            return False

    @staticmethod
    def get_foreground_window_rect():
        try:
            hwnd = windll.user32.GetForegroundWindow()
            return WindowMgr._get_rect_from_hwnd(hwnd)
        except:
            return None

    @staticmethod
    def get_game_rect():
        try:
            hwnd = windll.user32.FindWindowW(None, "ELDEN RING NIGHTREIGN")
            if hwnd == 0: return None
            return WindowMgr._get_rect_from_hwnd(hwnd)
        except:
            return None

    @staticmethod
    def _get_rect_from_hwnd(hwnd):
        try:
            rect = RECT()
            windll.user32.GetWindowRect(hwnd, byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0: return None
            return {"left": rect.left, "top": rect.top, "width": width, "height": height, "height_val": height}
        except:
            return None


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    ctypes.windll.user32.SetProcessDPIAware()


# ================= 视觉核心 =================
class VisionTool:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VisionTool, cls).__new__(cls)
            cls._instance.ocr = RapidOCR()
            cls._instance._init_scale()
            cls._instance.tpl_cursor = cls._instance._load_and_scale_tpl("data/tpl_cursor.png")
            cls._instance.tpl_lock = cls._instance._load_and_scale_tpl("data/tpl_lock.png")
            cls._instance.tpl_equip = cls._instance._load_and_scale_tpl("data/tpl_equip.png")
        return cls._instance

    def _init_scale(self):
        try:
            rect = WindowMgr.get_game_rect()
            if rect:
                current_h = rect['height_val']
                print(f"检测到游戏窗口高度: {current_h} (缩放基准)")
            else:
                current_h = windll.user32.GetSystemMetrics(1)
                print(f"未检测到游戏，使用屏幕高度: {current_h}")
            self.scale_factor = current_h / REF_SCREEN_HEIGHT
        except:
            self.scale_factor = 1.0

    def _load_and_scale_tpl(self, path):
        full_path = get_resource_path(path)
        if os.path.exists(full_path):
            img = cv2.imread(full_path, 0)
            if self.scale_factor != 1.0 and img is not None:
                new_w = int(img.shape[1] * self.scale_factor)
                new_h = int(img.shape[0] * self.scale_factor)
                if new_w > 0 and new_h > 0:
                    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return img
        return None

    def get_screen_image(self):
        with mss.mss() as sct:
            game_rect = WindowMgr.get_game_rect()
            if game_rect:
                try:
                    monitor = {"left": game_rect["left"], "top": game_rect["top"], "width": game_rect["width"],
                               "height": game_rect["height"]}
                    img = np.array(sct.grab(monitor))
                    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                except:
                    pass
        return None

    def extract_text_by_color(self, img, use_crop=True):
        if img is None: return [], []
        if use_crop:
            h, w = img.shape[:2]
            roi = img[int(h * 0.35):, :]
        else:
            roi = img
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([90, 50, 50])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        kernel = np.ones((2, 2), np.uint8)
        mask_blue = cv2.dilate(mask_blue, kernel, iterations=1)
        mask_white = cv2.bitwise_not(mask_blue)
        img_neg = cv2.bitwise_and(roi, roi, mask=mask_blue)
        _, img_neg_bin = cv2.threshold(cv2.cvtColor(img_neg, cv2.COLOR_BGR2GRAY), 10, 255, cv2.THRESH_BINARY)
        img_pos = cv2.bitwise_and(roi, roi, mask=mask_white)
        _, img_pos_bin = cv2.threshold(cv2.cvtColor(img_pos, cv2.COLOR_BGR2GRAY), 50, 255, cv2.THRESH_BINARY)
        res_neg, _ = self.ocr(img_neg_bin)
        res_pos, _ = self.ocr(img_pos_bin)
        list_neg = [normalize_text(line[1]) for line in res_neg] if res_neg else []
        list_pos = [normalize_text(line[1]) for line in res_pos] if res_pos else []
        return list_pos, list_neg

    def detect_selection_status(self, img):
        if self.tpl_cursor is None: return False, False, False, False

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 1. 找光标 (改进版：找所有光标，选右下角那个)
        right_half = gray[:, int(w * 0.4):]  # 只看右半屏

        # 匹配模板
        res = cv2.matchTemplate(right_half, self.tpl_cursor, cv2.TM_CCOEFF_NORMED)

        # 阈值过滤，找出所有候选点
        threshold = 0.65
        loc = np.where(res >= threshold)

        # loc[0] 是 y 坐标数组, loc[1] 是 x 坐标数组
        if len(loc[0]) == 0:
            return False, False, False, False

        # 将 (y, x) 坐标打包并排序
        # 排序规则：先按 Y 轴(行)降序，再按 X 轴(列)降序
        # 这样列表第一个元素就是最下面、最右边的光标（最新的光标）
        points = list(zip(loc[1], loc[0]))
        points.sort(key=lambda p: (p[1], p[0]), reverse=True)

        # 取第一个点作为真正的光标
        match_x, match_y = points[0]

        # 还原到全屏坐标
        cursor_x = match_x + int(w * 0.4)
        cursor_y = match_y

        # 2. 计算格子 ROI (保持不变)
        roi_w = int(REF_GRID_WIDTH * self.scale_factor)
        roi_h = int(REF_GRID_HEIGHT * self.scale_factor)
        offset_y = int(REF_OFFSET_Y * self.scale_factor)
        offset_x = int(REF_OFFSET_X * self.scale_factor)

        item_x = cursor_x + offset_x
        item_y = cursor_y + offset_y

        x1, y1 = max(0, item_x), max(0, item_y)
        x2, y2 = min(w, item_x + roi_w), min(h, item_y + roi_h)

        if x2 <= x1 or y2 <= y1: return True, False, False, False

        item_roi = gray[y1:y2, x1:x2]
        current_roi_h, current_roi_w = item_roi.shape

        # 3. 找图标
        is_equipped = False
        is_favorited = False

        half_w = int(current_roi_w * 0.5)
        half_h = int(current_roi_h * 0.5)

        if self.tpl_equip is not None:
            equip_area = item_roi[0:half_h, 0:half_w]
            if equip_area.shape[0] > self.tpl_equip.shape[0] and equip_area.shape[1] > self.tpl_equip.shape[1]:
                res_e = cv2.matchTemplate(equip_area, self.tpl_equip, cv2.TM_CCOEFF_NORMED)
                # 使用 np.where 检查是否有任何点超过阈值，比 minMaxLoc 更稳
                if np.any(res_e >= 0.70): is_equipped = True

        if self.tpl_lock is not None:
            lock_area = item_roi[0:half_h, half_w:current_roi_w]
            if lock_area.shape[0] > self.tpl_lock.shape[0] and lock_area.shape[1] > self.tpl_lock.shape[1]:
                res_l = cv2.matchTemplate(lock_area, self.tpl_lock, cv2.TM_CCOEFF_NORMED)
                if np.any(res_l >= 0.70): is_favorited = True

        # 4. 亮度检测
        center_ratio = 0.6
        center_w = int(current_roi_w * center_ratio)
        center_h = int(current_roi_h * center_ratio)
        rel_x = int((current_roi_w - center_w) / 2)
        rel_y = int((current_roi_h - center_h) / 2)
        center_roi = item_roi[rel_y:rel_y + center_h, rel_x:rel_x + center_w]

        brightness = np.mean(center_roi) if center_roi.size > 0 else 0.0
        is_dark = brightness < 50.0

        return True, is_equipped, is_favorited, is_dark