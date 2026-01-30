# --- START OF FILE bot_merchant.py ---
import time
import pydirectinput
import cv2
import utils


class MerchantBot:
    def __init__(self, log_func):
        self.log = log_func
        self.should_stop = False
        self.profiler = utils.Profiler()
        self.master_library = utils.DataLoader.get_master_library()
        self.vision = utils.VisionTool()

    def press(self, key, duration=0.03, wait=0.05):
        if self.should_stop: return
        pydirectinput.keyDown(key)
        time.sleep(duration)
        pydirectinput.keyUp(key)
        time.sleep(wait)

    def validate_item_in_shop(self, mode):
        self.log("正在校验商店选中商品...")
        img = self.vision.get_screen_image()
        if img is None:
            self.log("❌ 错误：无法获取游戏截图")
            return False

        pos, neg = self.vision.extract_text_by_color(img, use_crop=False)
        text = "".join(pos) + "".join(neg)
        has_stone = "原石" in text
        has_deep = "暗淡" in text

        if mode == "deepnight":
            if has_stone and has_deep: return True
        else:
            if has_stone and not has_deep: return True
        self.log(f"校验失败。模式:{mode}")
        return False

    def check_logic(self, pos_lines, neg_lines, config):
        mode = config['mode']
        active_presets = config['presets']
        bad_neg_list = config['bad_neg']

        if not pos_lines and not neg_lines:
            return False, "异常：OCR为空", "", "", "", True

        clean_neg_lines = []
        if mode == "deepnight":
            for ocr_line in neg_lines:
                corrected, score = utils.find_best_match_in_library(ocr_line, self.master_library)
                target = corrected if score > utils.CORRECTION_THRESHOLD else ocr_line
                clean_neg_lines.append(target)

        clean_pos_lines = []
        for ocr_line in pos_lines:
            if len(ocr_line) < 2 or "情景" in ocr_line: continue
            corrected, score = utils.find_best_match_in_library(ocr_line, self.master_library)
            if score > utils.CORRECTION_THRESHOLD:
                clean_pos_lines.append(corrected)

        if not clean_pos_lines:
            return False, "异常：无词条", "", "", "", True

        pos_str = " | ".join(clean_pos_lines)
        neg_str = " | ".join(clean_neg_lines)

        if mode == "deepnight":
            for target in clean_neg_lines:
                for bad in bad_neg_list:
                    if bad in target:
                        return False, f"致命负面 [{bad}]", "", pos_str, neg_str, False

        for preset in active_presets:
            wanted_items = preset['items']
            match_count = 0
            for line in clean_pos_lines:
                if line in wanted_items: match_count += 1
            if match_count >= 2:
                return True, f"命中[{preset['name']}]", "", pos_str, neg_str, False

        return False, "不符合预设", "", pos_str, neg_str, False

    def run(self, config):
        self.log(">>> 3秒后开始...")
        time.sleep(3)
        if not self.validate_item_in_shop(config['mode']): return
        self.log(">>> 开始循环...")

        while not self.should_stop:
            if not utils.WindowMgr.is_game_active():
                time.sleep(1)
                continue

            self.profiler.start("Buy")
            self.press(utils.KEYS['interact'], 0.02, 0.15)
            self.press(utils.KEYS['interact'], 0.02, 0.3)
            self.press(utils.KEYS['interact'], 0.02, 0.2)
            self.profiler.end("Buy")

            img = self.vision.get_screen_image()
            pos, neg = self.vision.extract_text_by_color(img, use_crop=True)
            keep, reason, _, pos_str, neg_str, is_fatal = self.check_logic(pos, neg, config)

            if is_fatal:
                self.log(f"🛑 {reason}")
                self.should_stop = True
                break

            self.log(f"📝 {pos_str}" + (f" | ⚠️ {neg_str}" if neg_str else ""))

            if keep:
                self.log(f"√ 保留 | {reason}")
                self.press(utils.KEYS['interact'], 0.02, 0.1)
            else:
                self.log(f"× 卖出 | {reason}")
                self.press(utils.KEYS['sell'], 0.02, 0.1)
                self.press(utils.KEYS['interact'], 0.02, 0.1)

            time.sleep(0.05)