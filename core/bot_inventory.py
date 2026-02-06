# --- START OF FILE bot_inventory.py ---
import time
import os
import cv2
import numpy as np
import pydirectinput
import utils


class InventoryBot:
    def __init__(self, log_func):
        self.log = log_func
        self.should_stop = False
        self.vision = utils.VisionTool()
        self.master_library = utils.DataLoader.get_master_library()
        self.stats = {'scanned': 0, 'locked': 0, 'marked': 0, 'skipped': 0}

        self.anchor1_sig = None
        self.anchor2_sig = None

        self.debug_dir = "../logs/debug_screenshots"
        if not os.path.exists(self.debug_dir):
            os.makedirs(self.debug_dir)

    def press(self, key, wait=0.1):
        if self.should_stop: return
        pydirectinput.press(key)
        time.sleep(wait)

    def get_item_signature(self, img):
        pos, neg = self.vision.extract_text_by_color(img, use_crop=True)
        signature = "".join(pos) + "".join(neg)
        return signature, pos, neg

    def _save_debug_snapshot(self, img, idx, status_tuple, ocr_text):
        found_cursor, is_equipped, is_favorited, is_dark = status_tuple
        debug_img = img.copy()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        scale = self.vision.scale_factor

        right_half = gray[:, int(w * 0.4):]
        res = cv2.matchTemplate(right_half, self.vision.tpl_cursor, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= 0.65:
            cursor_x = max_loc[0] + int(w * 0.4)
            cursor_y = max_loc[1]
            cur_w, cur_h = self.vision.tpl_cursor.shape[::-1]
            cv2.rectangle(debug_img, (cursor_x, cursor_y), (cursor_x + cur_w, cursor_y + cur_h), (0, 255, 0), 2)

            roi_w = int(utils.REF_GRID_WIDTH * scale)
            roi_h = int(utils.REF_GRID_HEIGHT * scale)
            off_x = int(utils.REF_OFFSET_X * scale)
            off_y = int(utils.REF_OFFSET_Y * scale)
            item_x = cursor_x + off_x
            item_y = cursor_y + off_y

            cv2.rectangle(debug_img, (item_x, item_y), (item_x + roi_w, item_y + roi_h), (255, 0, 0), 2)

            x1, y1 = max(0, item_x), max(0, item_y)
            x2, y2 = min(w, item_x + roi_w), min(h, item_y + roi_h)

            bright_val = 0
            equip_score = 0.0
            fav_score = 0.0

            if x2 > x1 and y2 > y1:
                item_roi = gray[y1:y2, x1:x2]
                curr_h, curr_w = item_roi.shape
                c_w, c_h = int(curr_w * 0.6), int(curr_h * 0.6)
                cx, cy = int((curr_w - c_w) / 2), int((curr_h - c_h) / 2)
                center_roi = item_roi[cy:cy + c_h, cx:cx + c_w]
                if center_roi.size > 0: bright_val = np.mean(center_roi)
                real_cx, real_cy = x1 + cx, y1 + cy
                cv2.rectangle(debug_img, (real_cx, real_cy), (real_cx + c_w, real_cy + c_h), (255, 0, 255), 1)

                half_w, half_h = int(curr_w * 0.5), int(curr_h * 0.5)
                if self.vision.tpl_equip is not None:
                    e_area = item_roi[0:half_h, 0:half_w]
                    if e_area.shape[0] > self.vision.tpl_equip.shape[0]:
                        equip_score = \
                        cv2.minMaxLoc(cv2.matchTemplate(e_area, self.vision.tpl_equip, cv2.TM_CCOEFF_NORMED))[1]
                if self.vision.tpl_lock is not None:
                    l_area = item_roi[0:half_h, half_w:curr_w]
                    if l_area.shape[0] > self.vision.tpl_lock.shape[0]:
                        fav_score = \
                        cv2.minMaxLoc(cv2.matchTemplate(l_area, self.vision.tpl_lock, cv2.TM_CCOEFF_NORMED))[1]

            info_text = [
                f"IDX: {idx}",
                f"Brightness: {bright_val:.1f} (IsDark: {is_dark})",
                f"EquipScore: {equip_score:.2f} (IsEquip: {is_equipped})",
                f"FavScore:   {fav_score:.2f} (IsFav: {is_favorited})",
                f"OCR: {ocr_text[:30]}..."
            ]
            y_start = item_y + roi_h + 20
            for line in info_text:
                cv2.putText(debug_img, line, (item_x - 50, y_start), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                y_start += 25

        filename = os.path.join(self.debug_dir, f"item_{idx:03d}.png")
        cv2.imwrite(filename, debug_img)

    def run(self, config):
        relic_type = config.get('mode', 'deepnight')
        strategy = config.get('inv_strategy', 'lock_only')
        self.log(f"===== 🐞 调试模式启动 =====")
        self.log(">>> 请选中【第一个】遗物，3秒后开始...")
        time.sleep(3)

        processed_count = 0
        consecutive_fails = 0

        while not self.should_stop:
            if not utils.WindowMgr.is_game_active():
                time.sleep(1)
                continue

            img = self.vision.get_screen_image()
            found_cursor, is_equipped, is_favorited, is_dark = self.vision.detect_selection_status(img)

            if not found_cursor:
                self.log("⚠️ 未找到光标...")
                self._save_debug_snapshot(img, processed_count, (False, False, False, False), "NO CURSOR")
                consecutive_fails += 1
                if consecutive_fails > 5: break
                time.sleep(0.5)
                continue
            consecutive_fails = 0

            curr_sig, pos, neg = self.get_item_signature(img)
            full_text_preview = ("|".join(pos) + "|" + "".join(neg))
            self._save_debug_snapshot(img, processed_count, (found_cursor, is_equipped, is_favorited, is_dark),
                                      full_text_preview)

            self.log(f"--- 物品 [{processed_count}] ---")
            self.log(f"🔍 视觉: 装备={is_equipped}, 收藏={is_favorited}, 暗淡={is_dark}")

            move_needed = self._process_item(is_equipped, is_favorited, is_dark, pos, neg, config, processed_count)

            if move_needed:
                self.log("➡️ 向右移动")
                self.press(utils.KEYS['move_right'])
            else:
                self.log("⏹️ 原地操作")

            processed_count += 1
            time.sleep(1.0)

        self.log("调试结束。")

    def _process_item(self, is_equipped, is_favorited, is_dark, pos, neg, config, idx):
        strategy = config.get('inv_strategy', 'lock_only')
        unfav_invalid = config.get('unfav_invalid', False)

        if is_equipped: return True
        if is_dark and not is_favorited: return True

        clean_pos_lines = []
        for line in pos:
            if len(line) < 2 or "情景" in line: continue
            corrected, score = utils.find_best_match_in_library(line, self.master_library)
            if score > utils.CORRECTION_THRESHOLD: clean_pos_lines.append(corrected)

        clean_neg_lines = []
        if config['mode'] == "deepnight":
            for line in neg:
                corrected, score = utils.find_best_match_in_library(line, self.master_library)
                target = corrected if score > utils.CORRECTION_THRESHOLD else line
                clean_neg_lines.append(target)

        all_text = pos + neg
        for line in all_text:
            match_name, score = utils.find_best_match_in_library(line, utils.SPECIAL_RELIC_NAMES)
            if score > 0.65: return True

        is_valid, _ = self._check_rules_cleaned(clean_pos_lines, clean_neg_lines, config)

        if is_valid:
            if not is_favorited:
                self.press(utils.KEYS['fav'])
                self.stats['locked'] += 1
            return True
        else:
            if is_favorited:
                if unfav_invalid:
                    self.press(utils.KEYS['fav'])
                    self.stats['locked'] -= 1
                    return True
                else:
                    return True
            else:
                if strategy == 'batch_sell':
                    self.press(utils.KEYS['interact'])
                    self.stats['marked'] += 1
                    return False
                else:
                    return True

    def _check_rules_cleaned(self, clean_pos, clean_neg, config):
        mode = config['mode']
        active_presets = config['presets']
        bad_neg_list = config['bad_neg']
        if mode == "deepnight":
            for target in clean_neg:
                for bad in bad_neg_list:
                    if bad in target: return False, ""
        for preset in active_presets:
            wanted = preset['items']
            match_count = 0
            for line in clean_pos:
                if line in wanted: match_count += 1
            if match_count >= 2: return True, ""
        return False, ""

    def _establish_anchors(self):
        pass

    def _verify_double_anchor(self):
        pass

    def _finish_job(self, s):
        pass