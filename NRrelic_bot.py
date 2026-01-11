import ttkbootstrap as tb
from ttkbootstrap.constants import *
import sys
import json
import os
import threading
import time
import datetime
import pydirectinput
from rapidocr_onnxruntime import RapidOCR
import mss
import numpy as np
import cv2
import keyboard
import unicodedata
import difflib
from tkinter import simpledialog, filedialog, messagebox


def get_resource_path(relative_path):
    """ 获取资源绝对路径，兼容开发环境和打包后的 EXE 环境 """
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# ================= 配置区域 =================

KEYS = {
    'interact': 'f',
    'sell': '3',
    'stop': 'f11'
}

FUZZY_THRESHOLD = 0.7
CORRECTION_THRESHOLD = 0.55

IGNORE_TEXTS = [
    "仅限能使用的",
    "装备时",
    "至游戏版本"
]
# UI 界面锚点
UI_ANCHORS = ["立刻卖出", "移除喜爱", "登记"]


# ================= 调试用：性能分析工具 =================
class Profiler:
    def __init__(self):
        self.records = {}
        self.start_times = {}

    def start(self, tag):
        self.start_times[tag] = time.perf_counter()

    def end(self, tag):
        if tag in self.start_times:
            duration = (time.perf_counter() - self.start_times[tag]) * 1000
            self.records[tag] = duration

    def print_report(self):
        print("\n⚡ [性能分析报告] (单位: ms)")
        total = sum(self.records.values())
        for tag, duration in self.records.items():
            percent = (duration / total * 100) if total > 0 else 0
            indicator = "🔴" if percent > 40 else "🟡" if percent > 20 else "🟢"
            print(f"{indicator} {tag:<15}: {duration:6.1f} ms ({percent:4.1f}%)")
        print(f"⏱️ 总耗时        : {total:6.1f} ms")
        print("-" * 40)


# ================= 工具函数 =================

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
    """
    [核心优化] 智能剪枝 + 全量优选
    既保证速度，又保证 '火属性' 和 '雷属性' 这种高度相似词条不被搞混
    """
    if not ocr_line or len(ocr_line) < 2: return None, 0.0

    # 1. 精确匹配 (最快)
    if ocr_line in library: return ocr_line, 1.0

    best_ratio = 0.0
    best_text = None

    # 预计算特征集合
    ocr_set = set(ocr_line)
    ocr_len = len(ocr_line)

    for item in library:
        # 2. [剪枝] 长度差异过大，直接跳过 (比如 '+1' 和 '攻击力+1')
        if abs(len(item) - ocr_len) > 3:
            continue

        # 3. [剪枝] 字符重合度检查 (Jaccard变体)
        # 如果公共字符连一半都不到，肯定不是同一个词，跳过 difflib 计算
        # 这步能过滤掉 95% 无关词条，极大提升速度
        common_chars = 0
        for char in item:
            if char in ocr_set:
                common_chars += 1
        if common_chars < max(len(item), ocr_len) * 0.5:
            continue

        # 4. 只有很像的才进行精细比对
        ratio = difflib.SequenceMatcher(None, ocr_line, item).ratio()

        # 5. [关键] 记录最高分，但不提前退出！
        # 必须看完所有候选者，防止把 '火属性' 误认为 '雷属性'
        if ratio > best_ratio:
            best_ratio = ratio
            best_text = item

    return best_text, best_ratio


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


# ================= UI 组件 (保持原样) =================

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
        tree.selection_set(tree.get_children()); return "break"

    def load_selection(self, selection_list_ref):
        self.current_selection_ref = selection_list_ref; self.refresh()

    def update_source(self, new_items):
        self.all_items = new_items; self.refresh()

    def filter_left(self, *args):
        self.refresh(self.search_var.get().lower())

    def refresh(self, search=""):
        for t in [self.tree_left, self.tree_right]:
            for x in t.get_children(): t.delete(x)
        for item in self.all_items:
            if item not in self.current_selection_ref and search in item.lower():
                self.tree_left.insert("", END, text=item)
        for item in self.current_selection_ref: self.tree_right.insert("", END, text=item)

    def add_item(self):
        for item in self.tree_left.selection():
            txt = self.tree_left.item(item, "text")
            if txt not in self.current_selection_ref: self.current_selection_ref.append(txt)
        self.refresh(self.search_var.get());
        if self.callback: self.callback()

    def remove_item(self):
        for item in self.tree_right.selection():
            txt = self.tree_right.item(item, "text")
            if txt in self.current_selection_ref: self.current_selection_ref.remove(txt)
        self.refresh(self.search_var.get());
        if self.callback: self.callback()

    def get_list(self):
        return self.current_selection_ref


class PresetEditor(tb.Frame):
    def __init__(self, master, all_possible_items, **kwargs):
        super().__init__(master, **kwargs)
        self.presets = [];
        self.current_preset_index = -1;
        self.all_possible_items = all_possible_items
        left_panel = tb.Frame(self, width=220);
        left_panel.pack(side=LEFT, fill=Y, padx=5, pady=5)
        toolbar1 = tb.Frame(left_panel);
        toolbar1.pack(fill=X, pady=2)
        tb.Button(toolbar1, text="+", width=3, command=self.add_preset, bootstyle="success-outline").pack(side=LEFT,
                                                                                                          padx=1)
        tb.Button(toolbar1, text="-", width=3, command=self.del_preset, bootstyle="danger-outline").pack(side=LEFT,
                                                                                                         padx=1)
        tb.Button(toolbar1, text="改名", width=5, command=self.rename_preset, bootstyle="info-outline").pack(side=LEFT,
                                                                                                             padx=1)
        toolbar2 = tb.Frame(left_panel);
        toolbar2.pack(fill=X, pady=2)
        tb.Button(toolbar2, text="导出预设", width=8, command=self.export_presets, bootstyle="secondary-outline").pack(
            side=LEFT, padx=1)
        tb.Button(toolbar2, text="导入预设", width=8, command=self.import_presets, bootstyle="warning-outline").pack(
            side=LEFT, padx=1)
        self.lb_presets = tb.Treeview(left_panel, show="tree", selectmode="browse");
        self.lb_presets.pack(fill=BOTH, expand=True)
        self.lb_presets.bind("<<TreeviewSelect>>", self.on_preset_select)
        self.selector = AttributeSelector(self, self.all_possible_items, "词条库", "当前预设包含的词条 (>=2生效)",
                                          "success")
        self.selector.pack(side=RIGHT, fill=BOTH, expand=True)

    def load_presets(self, presets_data):
        self.presets = presets_data;
        if not self.presets: self.presets.append({"name": "默认预设", "items": []})
        self.refresh_list()
        if self.presets: self.lb_presets.selection_set(self.lb_presets.get_children()[0])

    def refresh_list(self):
        selected = self.lb_presets.selection();
        selected_idx = self.lb_presets.index(selected[0]) if selected else 0
        for item in self.lb_presets.get_children(): self.lb_presets.delete(item)
        for p in self.presets: self.lb_presets.insert("", END, text=f"{p['name']} ({len(p['items'])})")
        children = self.lb_presets.get_children()
        if 0 <= selected_idx < len(children):
            self.lb_presets.selection_set(children[selected_idx])
        elif children:
            self.lb_presets.selection_set(children[0])

    def on_preset_select(self, event):
        selected = self.lb_presets.selection();
        if not selected: return
        idx = self.lb_presets.index(selected[0]);
        self.current_preset_index = idx;
        self.selector.load_selection(self.presets[idx]["items"])

    def add_preset(self):
        if len(self.presets) >= 10: return
        self.presets.append({"name": f"预设 {len(self.presets) + 1}", "items": []});
        self.refresh_list();
        self.lb_presets.selection_set(self.lb_presets.get_children()[-1])

    def del_preset(self):
        if len(self.presets) <= 1: return
        if self.current_preset_index >= 0: del self.presets[self.current_preset_index]; self.refresh_list()

    def rename_preset(self):
        if self.current_preset_index < 0: return
        new_name = simpledialog.askstring("重命名", "请输入预设名称:",
                                          initialvalue=self.presets[self.current_preset_index]["name"])
        if new_name: self.presets[self.current_preset_index]["name"] = new_name; self.refresh_list()

    def export_presets(self):
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")])
        if f:
            try:
                with open(f, "w", encoding="utf-8") as file:
                    json.dump(self.presets, file, ensure_ascii=False, indent=4)
                messagebox.showinfo("成功", f"导出成功")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def import_presets(self):
        f = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
        if f:
            try:
                with open(f, "r", encoding="utf-8") as file:
                    data = json.load(file); self.presets = data; self.refresh_list(); messagebox.showinfo("成功",
                                                                                                          "导入成功")
            except Exception as e:
                messagebox.showerror("错误", str(e))

    def update_source_library(self, new_library):
        self.all_possible_items = new_library; self.selector.update_source(new_library)

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
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            w, h = monitor["width"], monitor["height"]
            roi = {
                "top": monitor["top"] + int(h * 0.2),
                "left": monitor["left"] + int(w * 0.3),
                "width": int(w * 0.4),
                "height": int(h * 0.75)
            }
            img = np.array(sct.grab(roi))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def extract_text_by_color(self, img):
        self.profiler.start("OpenCV处理")

        # [保留图片留证功能] (可按需注释)
        ts = datetime.datetime.now().strftime("%H_%M_%S_%f")
        # cv2.imwrite(f"logs/{ts}_1_raw.jpg", img)

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
        self.profiler.end("OpenCV处理")

        self.profiler.start("OCR识别")
        res_neg, _ = self.ocr(img_neg_bin)
        res_pos, _ = self.ocr(img_pos_bin)
        self.profiler.end("OCR识别")

        list_neg = [normalize_text(line[1]) for line in res_neg] if res_neg else []
        list_pos = [normalize_text(line[1]) for line in res_pos] if res_pos else []
        return list_pos, list_neg

    def validate_item_in_shop(self, mode):
        self.log("正在校验商店选中商品...")
        img = self.get_screen_image()
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

    def wait_for_result_screen(self, timeout=2.5):
        self.profiler.start("等待界面")
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.should_stop:
                self.profiler.end("等待界面")
                return False, None

            img = self.get_screen_image()
            res, _ = self.ocr(img)
            text = "".join([line[1] for line in res]) if res else ""

            is_valid_ui = any(anchor in text for anchor in UI_ANCHORS)

            if is_valid_ui:
                self.profiler.end("等待界面")
                return True, img

            time.sleep(0.05)

        self.profiler.end("等待界面")
        return False, None

    def purchase_loop(self, config):
        self.profiler.start("按键操作(买)")
        # [优化] 极速三连：缩短 duration 和 wait
        self.press(KEYS['interact'], duration=0.02, wait=0.03)
        self.press(KEYS['interact'], duration=0.02, wait=0.03)
        self.press(KEYS['interact'], duration=0.02, wait=0.03)
        self.profiler.end("按键操作(买)")

        success, img = self.wait_for_result_screen(timeout=1.5)
        if not success:
            self.log("❌ 异常：未识别到遗物详情界面 UI，脚本已安全停止。")
            self.should_stop = True
            return

        self.profiler.start("逻辑判定")
        keep, reason, debug_info = self.check_logic(img, config)
        self.profiler.end("逻辑判定")

        self.profiler.start("按键操作(卖/留)")
        if keep:
            self.log(f"√ 保留 | {reason}")
            self.press(KEYS['interact'], duration=0.02, wait=0.1)
        else:
            self.log(f"× 卖出 | {reason}")
            self.press(KEYS['sell'], duration=0.02, wait=0.03)
            self.press(KEYS['interact'], duration=0.02, wait=0.03)
        self.profiler.end("按键操作(卖/留)")

        self.profiler.print_report()

    def check_logic(self, img, config):
        mode = config['mode']
        active_presets = config['presets']
        bad_neg_list = config['bad_neg']

        pos_lines, neg_lines = self.extract_text_by_color(img)

        # print("\n" + "=" * 40)
        # print(f"📸 [OCR 原始识别结果]")
        # print(f"🔵 负面池 (蓝字): {neg_lines}")
        # print(f"⚪ 正面池 (白字): {pos_lines}")
        # print("-" * 40)

        if mode == "deepnight":
            # print(f"💀 [负面检查] 开始比对黑名单...")
            for ocr_line in neg_lines:
                corrected, score = find_best_match_in_library(ocr_line, self.master_library)
                target = corrected if score > CORRECTION_THRESHOLD else ocr_line

                for bad in bad_neg_list:
                    if bad in target:
                        msg = f"致命负面 [{bad}] (来源: {ocr_line} -> {target})"
                        return False, msg, f"❌ {msg}"
            # print(f"✅ 负面检查通过")

        # print(f"✨ [正面标准化] 开始全库纠错...")
        normalized_pos_lines = []
        for ocr_line in pos_lines:
            if len(ocr_line) < 2: continue
            if "情景" in ocr_line: continue

            corrected, score = find_best_match_in_library(ocr_line, self.master_library)
            if score > CORRECTION_THRESHOLD:
                normalized_pos_lines.append(corrected)
                # print(f"   🔹 '{ocr_line}' -> 修正为: '{corrected}' ({score:.2f})")
            else:
                pass
                # print(f"   🔸 '{ocr_line}' -> 无法识别/噪点")

        # print(f"🎯 [预设匹配] 开始匹配 {len(active_presets)} 套方案...")

        for preset in active_presets:
            preset_name = preset['name']
            wanted_items = preset['items']
            match_count = 0
            hits = []

            for line in normalized_pos_lines:
                for wanted in wanted_items:
                    # 必须完全相等才算命中
                    if wanted == line:
                        match_count += 1
                        hits.append(wanted)
                        break

            if match_count >= 2:
                success_msg = f"命中方案[{preset_name}]: {hits}"
                # print(f"🎉 判定保留! {success_msg}")
                return True, success_msg, ""
            else:
                pass
                # print(f"   💨 预设[{preset_name}] 不满足: {match_count}/2 {hits}")

        return False, "不符合任何启用预设", "不满足条件"

    def run(self, config):
        self.log(">>> 3秒后开始校验...")
        time.sleep(3)
        if not self.validate_item_in_shop(config['mode']): return
        self.log(">>> 校验通过，开始循环...")
        while not self.should_stop:
            self.purchase_loop(config)
            time.sleep(0.1)


# ================= 主程序入口 =================

class App(tb.Window):
    def __init__(self):
        super().__init__(themename="superhero")
        self.title("NRrelic_bot V1.0")
        self.geometry("1100x850")
        self.norm_pos, self.deep_pos, self.deep_neg = DataLoader.get_data()
        self.logic = None
        self.presets_norm = []
        self.presets_deep = []
        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        top = tb.Frame(self);
        top.pack(fill=X, padx=10, pady=10)
        tb.Label(top, text="选择模式", font=("bold", 12)).pack(side=LEFT)
        self.mode_var = tb.StringVar(value="deepnight")
        rb1 = tb.Radiobutton(top, text="普通遗物", variable=self.mode_var, value="normal", command=self.on_mode_change);
        rb1.pack(side=LEFT, padx=15)
        rb2 = tb.Radiobutton(top, text="深夜遗物", variable=self.mode_var, value="deepnight",
                             command=self.on_mode_change);
        rb2.pack(side=LEFT, padx=15)
        self.nb = tb.Notebook(self);
        self.nb.pack(fill=BOTH, expand=True, padx=10)
        self.tab1 = tb.Frame(self.nb);
        self.nb.add(self.tab1, text="1. 策略预设 (定义多套保留方案)")
        self.ui_presets = PresetEditor(self.tab1, []);
        self.ui_presets.pack(fill=BOTH, expand=True)
        self.tab2 = tb.Frame(self.nb);
        self.nb.add(self.tab2, text="2. 全局致命负面")
        self.ui_neg = AttributeSelector(self.tab2, self.deep_neg, "负面词条", "黑名单(出现即卖)", "danger");
        self.ui_neg.pack(fill=BOTH, expand=True)
        ctrl = tb.Frame(self);
        ctrl.pack(fill=X, padx=20, pady=20)
        self.btn_start = tb.Button(ctrl, text="开始挂机", command=self.start, bootstyle="success");
        self.btn_start.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.btn_stop = tb.Button(ctrl, text="停止 (F11)", command=self.stop, bootstyle="danger", state="disabled");
        self.btn_stop.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.log_text = tb.Text(self, height=8);
        self.log_text.pack(fill=X, padx=20, pady=10)

    def on_mode_change(self):
        mode = self.mode_var.get()
        if mode == "normal":
            self.ui_presets.update_source_library(self.norm_pos);
            self.ui_presets.load_presets(self.presets_norm);
            self.nb.tab(1, state="disabled")
        else:
            self.ui_presets.update_source_library(self.deep_pos);
            self.ui_presets.load_presets(self.presets_deep);
            self.nb.tab(1, state="normal")

    def log(self, msg):
        self.log_text.insert(END, msg + "\n"); self.log_text.see(END)

    def start(self):
        current_presets = self.ui_presets.get_presets()
        if not current_presets: self.log("错误：请至少添加一套预设策略！"); return
        config = {'mode': self.mode_var.get(), 'presets': current_presets, 'bad_neg': self.ui_neg.get_list()}
        self.save_to_json()
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
        self.btn_start.config(state="normal");
        self.btn_stop.config(state="disabled")

    def save_to_json(self):
        mode = self.mode_var.get()
        current_data = self.ui_presets.get_presets()
        if mode == "normal":
            self.presets_norm = current_data
        else:
            self.presets_deep = current_data
        data = {'last_mode': mode, 'presets_norm': self.presets_norm, 'presets_deep': self.presets_deep,
                'bad_neg': self.ui_neg.get_list()}
        with open("bot_config.json", "w", encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def load_config(self):
        self.presets_norm = [{"name": "默认配置", "items": []}]
        self.presets_deep = [{"name": "默认配置", "items": []}]
        if os.path.exists("bot_config.json"):
            try:
                with open("bot_config.json", "r", encoding='utf-8') as f:
                    c = json.load(f)
                    self.presets_norm = c.get('presets_norm', self.presets_norm)
                    self.presets_deep = c.get('presets_deep', self.presets_deep)
                    self.ui_neg.set_list(c.get('bad_neg', []))
                    mode = c.get('last_mode', 'deepnight')
                    self.mode_var.set(mode)
            except:
                pass
        self.on_mode_change()


if __name__ == "__main__":
    App().mainloop()