import ttkbootstrap as tb
from ttkbootstrap.constants import *
import sys
import json
import os
import threading
import time
import pydirectinput
from rapidocr_onnxruntime import RapidOCR
import mss
import numpy as np
import cv2
import keyboard
import unicodedata
import difflib
import ctypes
from tkinter import simpledialog, filedialog, messagebox
import ctypes
from ctypes import windll, byref, Structure, c_long



# ================= 配置区域 =================
# [开关] 发布时设为 False，开发时设为 True
DEBUG_MODE = True

pydirectinput.PAUSE = 0.0

KEYS = {
    'interact': 'f',
    'sell': '3',
    'stop': 'f11'
}

FUZZY_THRESHOLD = 0.7
CORRECTION_THRESHOLD = 0.55


# ================= 调试工具 =================
class Profiler:
    def __init__(self):
        self.records = {}
        self.start_times = {}

    def start(self, tag):
        if not DEBUG_MODE: return  # 如果不是调试模式，直接跳过
        self.start_times[tag] = time.perf_counter()

    def end(self, tag):
        if not DEBUG_MODE: return
        if tag in self.start_times:
            duration = (time.perf_counter() - self.start_times[tag]) * 1000
            self.records[tag] = duration

    def print_report(self):
        if not DEBUG_MODE: return
        print("\n⚡ [性能分析报告] (单位: ms)")
        total = sum(self.records.values())
        for tag, duration in self.records.items():
            percent = (duration / total * 100) if total > 0 else 0
            indicator = "🔴" if percent > 40 else "🟡" if percent > 20 else "🟢"
            print(f"{indicator} {tag:<15}: {duration:6.1f} ms ({percent:4.1f}%)")
        print(f"⏱️ 总耗时        : {total:6.1f} ms")
        print("-" * 40)

# ================= 窗口管理工具  =================
class WindowMgr:
    """使用 Windows API 检测当前前台窗口"""
    @staticmethod
    def is_game_active():
        try:
            # 获取当前用户正在操作的窗口句柄
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            # 获取窗口标题
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            # 判断标题是否包含游戏名
            return "ELDEN RING NIGHTREIGN" in title
        except:
            return False

    # 获取当前前台窗口的精准坐标
    @staticmethod
    def get_foreground_window_rect():
        try:
            hwnd = windll.user32.GetForegroundWindow()
            rect = RECT()
            windll.user32.GetWindowRect(hwnd, byref(rect))

            # 计算 mss 需要的格式
            width = rect.right - rect.left
            height = rect.bottom - rect.top

            # 过滤无效窗口 (最小化时坐标通常是负数或极小)
            if width <= 0 or height <= 0:
                return None

            return {
                "left": rect.left,
                "top": rect.top,
                "width": width,
                "height": height
            }
        except:
            return None
# ================= 工具函数 =================
def get_resource_path(relative_path):
    """ 获取资源绝对路径 """
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def get_app_config_path():
    """
    获取全局配置文件的绝对路径。
    """
    # 获取系统的 LocalAppData 路径
    local_app_data = os.getenv('LOCALAPPDATA')
    if not local_app_data:
        # 如果获取失败（极少见），回退到用户主目录
        local_app_data = os.path.expanduser("~")

    # 创建软件专属文件夹
    config_dir = os.path.join(local_app_data, "NRrelic_bot")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    return os.path.join(config_dir, "bot_config.json")

def normalize_text(text):
    if not text: return ""
    text = unicodedata.normalize('NFKC', text)
    text = text.replace('【', '[').replace('】', ']').replace('□', '[').replace('■', '[')
    text = text.replace('十', '+')
    text = text.replace('陷人', '陷入')
    text = text.replace('碱', '减')
    text = text.replace('土', '+')
    text = text.replace('+41', '+4').replace('+31', '+3').replace('+21', '+2').replace('+11', '+1')
    text = text.replace(' ', '').replace('\t', '').replace('\r', '').replace('\n', '')
    return text


def is_fuzzy_match(ocr_line, target_line, threshold=FUZZY_THRESHOLD):
    if target_line in ocr_line: return True
    ratio = difflib.SequenceMatcher(None, ocr_line, target_line).ratio()
    return ratio >= threshold


def find_best_match_in_library(ocr_line, library):
    if not ocr_line or len(ocr_line) < 2: return None, 0.0
    if ocr_line in library: return ocr_line, 1.0

    best_ratio = 0.0
    best_text = None
    ocr_set = set(ocr_line)
    ocr_len = len(ocr_line)

    for item in library:
        item_len = len(item)
        if abs(item_len - ocr_len) > 2:
            continue

        common_chars = 0
        for char in item:
            if char in ocr_set:
                common_chars += 1

        if common_chars < max(item_len, ocr_len) * 0.6:
            continue

        ratio = difflib.SequenceMatcher(None, ocr_line, item).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_text = item

    return best_text, best_ratio

# =========== 定义 RECT 结构体，用于获取窗口坐标 ==========
class RECT(Structure):
    _fields_ = [("left", c_long), ("top", c_long), ("right", c_long), ("bottom", c_long)]

# 开启 DPI 感知 (解决高分屏/缩放导致的截图偏移问题)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    ctypes.windll.user32.SetProcessDPIAware()

# ================= 数据加载 =================

class DataLoader:
    @staticmethod
    def load_txt(filename):
        real_path = get_resource_path(filename)
        if not os.path.exists(real_path):
            print(f"警告: 找不到文件 {real_path}")
            return []
        with open(real_path, 'r', encoding='utf-8') as f:
            lines = set()
            for line in f.readlines():
                clean = normalize_text(line)
                if clean: lines.add(clean)
            return sorted(list(lines))

    @staticmethod
    def get_data():
        return (DataLoader.load_txt("data/normal.txt"),
                DataLoader.load_txt("data/deepnight_pos.txt"),
                DataLoader.load_txt("data/deepnight_neg.txt"))

    @staticmethod
    def get_master_library():
        n = DataLoader.load_txt("data/normal.txt")
        dp = DataLoader.load_txt("data/deepnight_pos.txt")
        dn = DataLoader.load_txt("data/deepnight_neg.txt")
        return sorted(list(set(n + dp + dn)))


# ================= UI 组件 =================

class AttributeSelector(tb.Frame):
    def __init__(self, master, all_items, title_left, title_right, bootstyle="primary", callback=None, **kwargs):
        super().__init__(master, **kwargs)
        self.all_items = all_items if all_items else []
        self.current_selection_ref = []
        self.callback = callback

        container = tb.Frame(self)
        container.pack(fill=BOTH, expand=True, padx=5, pady=5)

        frame_left = tb.Labelframe(container, text=title_left, bootstyle="secondary")
        frame_left.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        self.search_var = tb.StringVar()
        self.search_var.trace("w", self.filter_left)
        tb.Entry(frame_left, textvariable=self.search_var).pack(fill=X, padx=5, pady=5)
        self.tree_left = tb.Treeview(frame_left, show="tree", selectmode="extended")
        self.tree_left.pack(side=LEFT, fill=BOTH, expand=True)
        sb_left = tb.Scrollbar(frame_left, orient="vertical", command=self.tree_left.yview)
        sb_left.pack(side=RIGHT, fill=Y)
        self.tree_left.configure(yscrollcommand=sb_left.set)

        frame_mid = tb.Frame(container)
        frame_mid.pack(side=LEFT, fill=Y, padx=5, pady=50)
        tb.Button(frame_mid, text="添加 >>", command=self.add_item, bootstyle=bootstyle).pack(pady=10)
        tb.Button(frame_mid, text="<< 移除", command=self.remove_item, bootstyle="secondary").pack(pady=10)

        frame_right = tb.Labelframe(container, text=title_right, bootstyle=bootstyle)
        frame_right.pack(side=LEFT, fill=BOTH, expand=True, padx=5)
        self.tree_right = tb.Treeview(frame_right, show="tree", selectmode="extended")
        self.tree_right.pack(side=LEFT, fill=BOTH, expand=True)
        sb_right = tb.Scrollbar(frame_right, orient="vertical", command=self.tree_right.yview)
        sb_right.pack(side=RIGHT, fill=Y)
        self.tree_right.configure(yscrollcommand=sb_right.set)

        self.tree_left.bind("<Control-a>", lambda e: self.select_all(self.tree_left))
        self.tree_right.bind("<Control-a>", lambda e: self.select_all(self.tree_right))

        self.refresh()

    def select_all(self, tree):
        tree.selection_set(tree.get_children())
        return "break"

    def load_selection(self, selection_list_ref):
        self.current_selection_ref = selection_list_ref
        self.refresh()

    def update_source(self, new_items):
        self.all_items = new_items
        self.refresh()

    def filter_left(self, *args):
        self.refresh(self.search_var.get().lower())

    def refresh(self, search=""):
        for t in [self.tree_left, self.tree_right]:
            for x in t.get_children(): t.delete(x)

        for item in self.all_items:
            if item not in self.current_selection_ref and search in item.lower():
                self.tree_left.insert("", END, text=item)

        for item in self.current_selection_ref:
            self.tree_right.insert("", END, text=item)

    def add_item(self):
        for item in self.tree_left.selection():
            txt = self.tree_left.item(item, "text")
            if txt not in self.current_selection_ref:
                self.current_selection_ref.append(txt)
        self.refresh(self.search_var.get())
        if self.callback: self.callback()

    def remove_item(self):
        for item in self.tree_right.selection():
            txt = self.tree_right.item(item, "text")
            if txt in self.current_selection_ref:
                self.current_selection_ref.remove(txt)
        self.refresh(self.search_var.get())
        if self.callback: self.callback()

    def get_list(self):
        return self.current_selection_ref

    def set_list(self, lst):
        valid_items = [normalize_text(i) for i in lst]
        self.current_selection_ref = [i for i in valid_items if i in self.all_items]
        self.refresh()


class PresetEditor(tb.Frame):
    # [修改] 移除了 export_cb 和 import_cb，因为按钮移走了
    def __init__(self, master, all_possible_items, **kwargs):
        super().__init__(master, **kwargs)
        self.presets = []
        self.current_preset_index = -1
        self.all_possible_items = all_possible_items

        left_panel = tb.Frame(self, width=220)
        left_panel.pack(side=LEFT, fill=Y, padx=5, pady=5)

        toolbar1 = tb.Frame(left_panel)
        toolbar1.pack(fill=X, pady=2)
        tb.Button(toolbar1, text="+", width=3, command=self.add_preset, bootstyle="success-outline").pack(side=LEFT,
                                                                                                          padx=1)
        tb.Button(toolbar1, text="-", width=3, command=self.del_preset, bootstyle="danger-outline").pack(side=LEFT,
                                                                                                         padx=1)
        tb.Button(toolbar1, text="改名", width=5, command=self.rename_preset, bootstyle="info-outline").pack(side=LEFT,
                                                                                                             padx=1)

        # [修改] 移除了底部的导入导出按钮栏

        self.lb_presets = tb.Treeview(left_panel, show="tree", selectmode="browse")
        self.lb_presets.pack(fill=BOTH, expand=True)
        self.lb_presets.bind("<<TreeviewSelect>>", self.on_preset_select)

        self.selector = AttributeSelector(
            self,
            self.all_possible_items,
            "词条库",
            "当前预设包含的词条 (>=2生效)",
            "success"
        )
        self.selector.pack(side=RIGHT, fill=BOTH, expand=True)

    def load_presets(self, presets_data):
        self.presets = presets_data
        if not self.presets:
            self.presets.append({"name": "默认预设", "items": []})
        self.refresh_list()
        if self.presets:
            try:
                first_id = self.lb_presets.get_children()[0]
                self.lb_presets.selection_set(first_id)
            except IndexError:
                pass

    def refresh_list(self):
        selected = self.lb_presets.selection()
        selected_idx = self.lb_presets.index(selected[0]) if selected else 0

        for item in self.lb_presets.get_children():
            self.lb_presets.delete(item)

        for p in self.presets:
            count = len(p["items"])
            self.lb_presets.insert("", END, text=f"{p['name']} ({count})")

        children = self.lb_presets.get_children()
        if children:
            if 0 <= selected_idx < len(children):
                self.lb_presets.selection_set(children[selected_idx])
            else:
                self.lb_presets.selection_set(children[0])

    def on_preset_select(self, event):
        selected = self.lb_presets.selection()
        if not selected: return
        idx = self.lb_presets.index(selected[0])
        self.current_preset_index = idx
        self.selector.load_selection(self.presets[idx]["items"])

    def add_preset(self):
        if len(self.presets) >= 10: return
        new_name = f"预设 {len(self.presets) + 1}"
        self.presets.append({"name": new_name, "items": []})
        self.refresh_list()
        children = self.lb_presets.get_children()
        if children:
            self.lb_presets.selection_set(children[-1])

    def del_preset(self):
        if len(self.presets) <= 1: return
        if self.current_preset_index >= 0:
            del self.presets[self.current_preset_index]
            self.refresh_list()

    def rename_preset(self):
        if self.current_preset_index < 0: return
        old_name = self.presets[self.current_preset_index]["name"]
        new_name = simpledialog.askstring("重命名", "请输入预设名称:", initialvalue=old_name)
        if new_name:
            self.presets[self.current_preset_index]["name"] = new_name
            self.refresh_list()

    def update_source_library(self, new_library):
        self.all_possible_items = new_library
        self.selector.update_source(new_library)

    def get_presets(self):
        return self.presets


# ================= 自动化逻辑核心 =================

class BotLogic:
    def __init__(self, log_func):
        self.log = log_func
        self.should_stop = False
        self.profiler = Profiler()
        self.master_library = DataLoader.get_master_library()
        if not os.path.exists("logs"): os.makedirs("logs")
        try:
            self.ocr = RapidOCR()
            self.log("OCR 引擎初始化成功")
        except:
            self.log("错误: OCR 初始化失败")

    def press(self, key, duration=0.03, wait=0.05):
        if self.should_stop: return
        pydirectinput.keyDown(key)
        time.sleep(duration)
        pydirectinput.keyUp(key)
        time.sleep(wait)

    def get_screen_image(self):
        """
        动态截取当前游戏窗口
        无论在哪个显示器，无论全屏还是窗口化，都能精准截图
        """
        with mss.mss() as sct:
            # 1. 尝试获取游戏窗口坐标
            game_rect = None

            # 只有当游戏在前台时，才去获取它的坐标
            if WindowMgr.is_game_active():
                game_rect = WindowMgr.get_foreground_window_rect()

            # 2. 决定截图区域
            if game_rect:
                # 找到游戏窗口！
                monitor = game_rect
            else:
                return None

            # 3. 执行截图
            try:
                img = np.array(sct.grab(monitor))
            except Exception as e:
                # 极少数情况(如窗口最小化/坐标溢出)会导致 grab 报错
                # print(f"截图失败: {e}")
                return None

                # 4. 格式转换
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def extract_text_by_color(self, img):
        if img is None: return
        # 1. 图像处理 (OpenCV)
        self.profiler.start("OpenCV预处理")
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower_blue = np.array([90, 50, 50])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)
        kernel = np.ones((2, 2), np.uint8)
        mask_blue = cv2.dilate(mask_blue, kernel, iterations=1)
        mask_white = cv2.bitwise_not(mask_blue)

        img_neg = cv2.bitwise_and(img, img, mask=mask_blue)
        _, img_neg_bin = cv2.threshold(cv2.cvtColor(img_neg, cv2.COLOR_BGR2GRAY), 10, 255, cv2.THRESH_BINARY)
        img_pos = cv2.bitwise_and(img, img, mask=mask_white)
        _, img_pos_bin = cv2.threshold(cv2.cvtColor(img_pos, cv2.COLOR_BGR2GRAY), 50, 255, cv2.THRESH_BINARY)
        self.profiler.end("OpenCV预处理")

        # 2. OCR 推理 (这是大头)
        self.profiler.start("RapidOCR推理")
        res_neg, _ = self.ocr(img_neg_bin)
        res_pos, _ = self.ocr(img_pos_bin)
        self.profiler.end("RapidOCR推理")

        list_neg = [normalize_text(line[1]) for line in res_neg] if res_neg else []
        list_pos = [normalize_text(line[1]) for line in res_pos] if res_pos else []
        return list_pos, list_neg

    def validate_item_in_shop(self, mode):
        self.log("正在校验商店选中商品...")
        img = self.get_screen_image()
        if img is None: return False
        res, _ = self.ocr(img)
        text = "".join([line[1] for line in res]) if res else ""
        has_stone = "原石" in text
        has_deep = "暗淡" in text
        if mode == "deepnight":
            if has_stone and has_deep: return True
        else:
            if has_stone and not has_deep: return True
        self.log(f"校验失败。模式:{mode}。")
        return False

    def purchase_loop(self, config):
        # 焦点检测：如果当前前台窗口不是游戏，立即停止
        if not WindowMgr.is_game_active():
            self.log("🛑 警告：游戏失去焦点 (检测到切屏)，脚本自动停止。")
            self.should_stop = True
            return
        self.profiler.start("按键操作(买)")
        self.press(KEYS['interact'], duration=0.02, wait=0.15)
        self.press(KEYS['interact'], duration=0.02, wait=0.3)
        self.press(KEYS['interact'], duration=0.02, wait=0.2)
        self.profiler.end("按键操作(买)")

        self.profiler.start("截取图片")
        img = self.get_screen_image()
        self.profiler.end("截取图片")

        self.profiler.start("逻辑判定")
        keep, reason, debug_info, pos_str, neg_str, is_fatal = self.check_logic(img, config)
        self.profiler.end("逻辑判定")
        # 致命错误熔断
        if is_fatal:
            self.log(f"🛑 {reason}")
            self.should_stop = True
            return

        #  在界面打印清洗后的识别结果
        self.log(f"📝 正面: {pos_str}")
        if neg_str:
            self.log(f"⚠️ 负面: {neg_str}")

        self.profiler.start("按键操作(卖/留)")
        if keep:
            self.log(f"√ 保留 | {reason}")
            self.press(KEYS['interact'], duration=0.02, wait=0.1)
        else:
            self.log(f"× 卖出 | {reason}")
            self.press(KEYS['sell'], duration=0.02, wait=0.1)
            self.press(KEYS['interact'], duration=0.02, wait=0.1)
        self.profiler.end("按键操作(卖/留)")

        self.profiler.print_report()

    def check_logic(self, img, config):
        mode = config['mode']
        active_presets = config['presets']
        bad_neg_list = config['bad_neg']

        # 1. 提取文本
        pos_lines, neg_lines = self.extract_text_by_color(img)

        # 如果纠错前就全是空的，说明画面异常
        if not pos_lines and not neg_lines:
            return False, "异常：OCR为空(画面异常/遮挡)", "", "", "", True

        # 2. 清洗纠错
        clean_neg_lines = []
        if mode == "deepnight":
            for ocr_line in neg_lines:
                corrected, score = find_best_match_in_library(ocr_line, self.master_library)
                target = corrected if score > CORRECTION_THRESHOLD else ocr_line
                clean_neg_lines.append(target)

        clean_pos_lines = []
        for ocr_line in pos_lines:
            if len(ocr_line) < 2: continue
            if "情景" in ocr_line: continue

            corrected, score = find_best_match_in_library(ocr_line, self.master_library)
            if score > CORRECTION_THRESHOLD:
                clean_pos_lines.append(corrected)

        # 再次熔断：如果清洗后正面词条为空，也视为异常
        if not clean_pos_lines:
            return False, "异常：无词条识别", "", "", "", True

        pos_str_display = " | ".join(clean_pos_lines)
        neg_str_display = " | ".join(clean_neg_lines)

        # 3. 负面检查
        if mode == "deepnight":
            for target in clean_neg_lines:
                for bad in bad_neg_list:
                    if bad in target:
                        return False, f"致命负面 [{bad}]", "", pos_str_display, neg_str_display, False

        # 4. 正面检查
        for preset in active_presets:
            preset_name = preset['name']
            wanted_items = preset['items']
            match_count = 0
            hits = []

            for line in clean_pos_lines:
                for wanted in wanted_items:
                    if wanted == line:
                        match_count += 1
                        hits.append(wanted)
                        break

            if match_count >= 2:
                return True, f"命中方案[{preset_name}]: {hits}", "", pos_str_display, neg_str_display, False

        return False, "不符合任何启用预设", "", pos_str_display, neg_str_display, False

    def run(self, config):
        self.log(">>> 3秒后开始校验...")
        time.sleep(3)
        if not self.validate_item_in_shop(config['mode']): return
        self.log(">>> 校验通过，开始循环...")
        while not self.should_stop:
            self.purchase_loop(config)
            time.sleep(0.2)

        # ================= 主程序入口 =================


class App(tb.Window):
    def __init__(self):
        super().__init__(themename="superhero")
        self.title("NRrelic_bot V1.2.1")
        self.geometry("1100x850")
        #  设置运行时的窗口图标
        try:
            icon_path = get_resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            print(f"图标加载失败: {e}")  # 防止图标丢失导致程序打不开

        self.norm_pos, self.deep_pos, self.deep_neg = DataLoader.get_data()
        self.logic = None

        self.presets_norm = []
        self.presets_deep = []

        self.setup_ui()
        self.load_config()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_ui(self):
        top = tb.Frame(self);
        top.pack(fill=X, padx=10, pady=10)

        # 左侧：模式选择
        tb.Label(top, text="模式", font=("bold", 12)).pack(side=LEFT)
        self.mode_var = tb.StringVar(value="deepnight")
        rb1 = tb.Radiobutton(top, text="普通遗物", variable=self.mode_var, value="normal", command=self.on_mode_change);
        rb1.pack(side=LEFT, padx=10)
        rb2 = tb.Radiobutton(top, text="深夜遗物", variable=self.mode_var, value="deepnight",
                             command=self.on_mode_change)
        rb2.pack(side=LEFT, padx=10)

        # [修改] 右侧：全局配置按钮
        tb.Button(top, text="导出配置", width=8, command=self.export_full_config, bootstyle="secondary-outline").pack(
            side=RIGHT, padx=5)
        tb.Button(top, text="导入配置", width=8, command=self.import_full_config, bootstyle="warning-outline").pack(
            side=RIGHT, padx=5)

        self.nb = tb.Notebook(self)
        self.nb.pack(fill=BOTH, expand=True, padx=10)

        self.tab1 = tb.Frame(self.nb)
        self.nb.add(self.tab1, text="1. 策略预设")
        self.ui_presets = PresetEditor(self.tab1, [])
        self.ui_presets.pack(fill=BOTH, expand=True)

        self.tab2 = tb.Frame(self.nb)
        self.nb.add(self.tab2, text="2. 全局致命负面")
        self.ui_neg = AttributeSelector(self.tab2, self.deep_neg, "负面词条", "黑名单(出现即卖)", "danger")
        self.ui_neg.pack(fill=BOTH, expand=True)

        ctrl = tb.Frame(self)
        ctrl.pack(fill=X, padx=20, pady=20)
        self.btn_start = tb.Button(ctrl, text="开始挂机", command=self.start, bootstyle="success");
        self.btn_start.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.btn_stop = tb.Button(ctrl, text="停止 (F11)", command=self.stop, bootstyle="danger", state="disabled");
        self.btn_stop.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.log_text = tb.Text(self, height=8)
        self.log_text.pack(fill=X, padx=20, pady=10)

    def on_mode_change(self):
        mode = self.mode_var.get()
        if mode == "normal":
            self.ui_presets.update_source_library(self.norm_pos)
            self.ui_presets.load_presets(self.presets_norm)
            self.nb.tab(1, state="disabled")
        else:
            self.ui_presets.update_source_library(self.deep_pos)
            self.ui_presets.load_presets(self.presets_deep)
            self.nb.tab(1, state="normal")

    def log(self, msg):
        self.log_text.insert(END, msg + "\n")
        self.log_text.see(END)

    def start(self):
        current_presets = self.ui_presets.get_presets()
        if not current_presets: self.log("错误：请至少添加一套预设策略！"); return

        self.save_to_json()

        config = {
            'mode': self.mode_var.get(),
            'presets': current_presets,
            'bad_neg': self.ui_neg.get_list()
        }

        self.logic = BotLogic(self.log)
        t = threading.Thread(target=self.logic.run, args=(config,))
        t.daemon = True;
        t.start()

        threading.Thread(target=self.monitor_keys, daemon=True).start()
        self.btn_start.config(state="disabled");
        self.btn_stop.config(state="normal")

    def monitor_keys(self):
        while self.logic and not self.logic.should_stop:
            if keyboard.is_pressed('f11'): self.stop(); break
            time.sleep(0.1)

    def stop(self):
        if self.logic: self.logic.should_stop = True
        self.log("🛑 已接收停止指令 (F11/按钮)，正在结束当前循环...")
        self.btn_start.config(state="normal");
        self.btn_stop.config(state="disabled")

    def save_to_json(self):
        mode = self.mode_var.get()
        current_presets = self.ui_presets.get_presets()
        if mode == "normal":
            self.presets_norm = current_presets
        else:
            self.presets_deep = current_presets

        data = {
            'last_mode': mode,
            'presets_norm': self.presets_norm,
            'presets_deep': self.presets_deep,
            'bad_neg': self.ui_neg.get_list()
        }

        config_path = get_app_config_path()
        try:
            with open(config_path, "w", encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            # print(f"配置已保存至: {config_path}") # 调试用
        except Exception as e:
            messagebox.showerror("保存失败", f"无法保存配置文件：\n{e}")

    def export_full_config(self):
        self.save_to_json()  # 先存到内存和本地
        data = {
            'last_mode': self.mode_var.get(),
            'presets_norm': self.presets_norm,
            'presets_deep': self.presets_deep,
            'bad_neg': self.ui_neg.get_list()
        }
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Config", "*.json")],
            title="导出完整配置"
        )
        if filename:
            try:
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                messagebox.showinfo("成功", f"配置已导出到:\n{filename}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {e}")

    def import_full_config(self):
        """导入配置 (智能识别旧版/新版，支持取消)"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON Config", "*.json"), ("All Files", "*.*")],
            title="导入配置"
        )
        if not filename: return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                c = json.load(f)

            # --- 情况 A: 导入的是旧版预设文件 (列表格式) ---
            if isinstance(c, list):
                # 获取当前界面选中的模式名称
                curr_mode_val = self.mode_var.get()
                curr_mode_name = "普通遗物" if curr_mode_val == "normal" else "深夜遗物"

                # 使用 askyesnocancel，增加取消选项
                choice = messagebox.askyesnocancel(
                    "导入旧版预设",
                    f"检测到旧版预设文件（不含模式信息）。\n\n"
                    f"当前界面选择的是【{curr_mode_name}】。\n"
                    f"点击【是】导入到【{curr_mode_name}】模式。\n"
                    f"点击【否】反转导入到另一模式。\n"
                    f"点击【取消】中止操作。",
                    icon='warning'
                )

                # [逻辑判断]
                if choice is None:
                    return  # 用户点击了取消或X，直接中止

                # choice为True(是) -> 当前模式；choice为False(否) -> 反转模式
                target_mode = curr_mode_val if choice else ("deepnight" if curr_mode_val == "normal" else "normal")

                if target_mode == "normal":
                    self.presets_norm = c
                    if self.mode_var.get() != "normal": self.mode_var.set("normal")
                else:
                    self.presets_deep = c
                    if self.mode_var.get() != "deepnight": self.mode_var.set("deepnight")

                self.on_mode_change()  # 刷新界面

                target_name = "普通遗物" if target_mode == "normal" else "深夜遗物"
                messagebox.showinfo("成功", f"旧版预设已成功导入到【{target_name}】模式！")
                return

            # --- 情况 B: 导入的是新版完整配置 (字典格式) ---

            self.presets_norm = c.get('presets_norm', [{"name": "默认配置", "items": []}])
            self.presets_deep = c.get('presets_deep', [{"name": "默认配置", "items": []}])

            loaded_neg = c.get('bad_neg', [])
            self.ui_neg.set_list(loaded_neg)

            mode = c.get('last_mode', 'deepnight')
            self.mode_var.set(mode)

            self.on_mode_change()

            messagebox.showinfo("成功", "完整配置导入成功！")

        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {e}")

    def load_config(self):

        # 默认初始化为空列表，稍后填充
        self.presets_norm = []
        self.presets_deep = []
        saved_neg_list = []

        config_path = get_app_config_path()  #

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding='utf-8') as f:
                    c = json.load(f)

                    # 读取配置，如果不存在则使用新的默认列表
                    self.presets_norm = c.get('presets_norm', [{"name": "默认配置", "items": []}])
                    self.presets_deep = c.get('presets_deep', [{"name": "默认配置", "items": []}])

                    saved_neg_list = c.get('bad_neg', [])
                    self.mode_var.set(c.get('last_mode', 'deepnight'))
            except Exception as e:
                print(f"配置文件加载警告: {e}")

        # 双重保险：如果读取失败导致仍为空，初始化默认值
        if not self.presets_norm:
            self.presets_norm = [{"name": "默认配置", "items": []}]
        if not self.presets_deep:
            self.presets_deep = [{"name": "默认配置", "items": []}]

        self.ui_neg.set_list(saved_neg_list)
        self.on_mode_change()

    def on_close(self):
        self.stop()
        self.save_to_json()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()