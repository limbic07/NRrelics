"""仓库清理的顺序导航证据；正常流程只使用每轮已有的一张截图。"""

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class NavigationCheck:
    confirmed: bool
    box: tuple
    evidence: str
    detail_change: float = 0.0
    detail_icon_change: float = 0.0
    sale_change: float = 0.0
    card_change: float = 0.0
    detected_box: tuple | None = None
    cursor_checked: bool = False


class RepositoryNavigation:
    """按已发出的 F/右键追踪格子，再用画面确认动作结果。"""

    # 坐标基于 1920x1080 游戏客户区。文字和详情大图标分别比较。
    DETAIL_REGION = (1070, 770, 1700, 968)
    DETAIL_ICON_REGION = (930, 750, 1055, 890)
    # 左侧待售出金额：按 F 成功后会从 +0 变成相应金额。
    SALE_REGION = (465, 380, 545, 430)
    DETAIL_CHANGE_MIN = 2.0
    DETAIL_ICON_CHANGE_MIN = 3.0
    CARD_CHANGE_MIN = 3.0
    COLUMNS = 8
    # 平时滚动让光标停在第 4 行；到仓库最后一行时滚动到头，光标进入第 5 行。
    CURSOR_ROWS = 4

    def __init__(self, total_items: int | None = None):
        self.index = 0
        self.total_items = total_items if total_items and total_items > 0 else None
        self.previous_detail = None
        self.previous_detail_icon = None
        self.previous_sale = None
        self.previous_card = None
        self.pending_action = None

    @staticmethod
    def _crop_gray(image, region):
        h, w = image.shape[:2]
        x1, y1, x2, y2 = region
        x1, x2 = round(x1 * w / 1920), round(x2 * w / 1920)
        y1, y2 = round(y1 * h / 1080), round(y2 * h / 1080)
        return cv2.cvtColor(image[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _change(previous, current):
        if previous is None or previous.shape != current.shape:
            return 0.0
        return float(np.mean(cv2.absdiff(previous, current)))

    def expected_box(self, image):
        h, w = image.shape[:2]
        column = self.index % self.COLUMNS
        row = min(self.index // self.COLUMNS, self.CURSOR_ROWS - 1)
        if self.total_items and self.total_items > self.CURSOR_ROWS * self.COLUMNS:
            final_row_start = ((self.total_items - 1) // self.COLUMNS) * self.COLUMNS
            if self.index >= final_row_start:
                row = self.CURSOR_ROWS
        return (round((928 + 110 * column) * w / 1920),
                round((209 + 106 * row) * h / 1080),
                round(92 * w / 1920), round(94 * h / 1080))

    @staticmethod
    def _card_gray(image, box):
        x, y, w, h = box
        margin_x, margin_y = round(w * 0.13), round(h * 0.13)
        card = image[y + margin_y:y + h - margin_y,
                     x + margin_x:x + w - margin_x]
        return cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)

    @staticmethod
    def _cursor_at_expected(detected, expected):
        if detected is None:
            return False
        x, y, w, h = detected
        ex, ey, ew, eh = expected
        return (abs(x + w / 2 - ex - ew / 2) <= ew * 0.4
                and abs(y + h / 2 - ey - eh / 2) <= eh * 0.4)

    def check(self, image, detector, scale_x=1.0, scale_y=1.0):
        """先确认光标位于下一格，再确认详情已刷新到可用于 OCR。"""
        box = self.expected_box(image)
        if self.pending_action is None:
            return NavigationCheck(True, box, "首件遗物")

        detail_change = self._change(
            self.previous_detail, self._crop_gray(image, self.DETAIL_REGION))
        detail_icon_change = self._change(
            self.previous_detail_icon, self._crop_gray(image, self.DETAIL_ICON_REGION))
        sale_change = self._change(
            self.previous_sale, self._crop_gray(image, self.SALE_REGION))
        card_change = self._change(
            self.previous_card, self._card_gray(image, box))
        detected, _ = detector.detect_cursor(image, scale_x, scale_y)
        if not self._cursor_at_expected(detected, box):
            return NavigationCheck(False, box, "光标未到预计下一格", detail_change,
                                   detail_icon_change, sale_change, card_change, detected, True)
        if card_change >= self.CARD_CHANGE_MIN:
            if (detail_change < self.DETAIL_CHANGE_MIN
                    and detail_icon_change < self.DETAIL_ICON_CHANGE_MIN):
                # 光标已前进，但详情仍显示旧内容；暂不使用这帧做 OCR。
                return NavigationCheck(False, box, "详情尚未刷新", detail_change,
                                       detail_icon_change, sale_change, card_change, detected, True)
        return NavigationCheck(True, box, "光标位于预计下一格", detail_change,
                               detail_icon_change, sale_change, card_change, detected, True)

    def expect_next(self, image, action):
        """在按 F 或右键之后调用；只保存小图，不保存完整截图。"""
        if action not in ("sale", "right"):
            raise ValueError(f"未知导航动作: {action}")
        self.previous_detail = self._crop_gray(image, self.DETAIL_REGION)
        self.previous_detail_icon = self._crop_gray(image, self.DETAIL_ICON_REGION)
        self.previous_sale = self._crop_gray(image, self.SALE_REGION)
        self.previous_card = self._card_gray(image, self.expected_box(image))
        self.pending_action = action
        self.index += 1
