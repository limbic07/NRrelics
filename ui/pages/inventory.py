# --- START OF FILE ui/pages/inventory.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ui.pages.base_page import BasePage


class InventoryPage(BasePage):
    def __init__(self, master):
        super().__init__(master, title="仓库管理")

        # 1. 策略选择
        opt_frame = tb.Labelframe(self, text="清理策略", padding=20, bootstyle="warning")
        opt_frame.pack(fill=X, pady=10)

        self.strat_var = tb.StringVar(value="lock")

        # 使用卡片式单选 (自定义Frame模拟)
        rb1 = tb.Radiobutton(opt_frame, text="收藏模式 (只收藏好遗物，不出售)", variable=self.strat_var, value="lock",
                             bootstyle="warning")
        rb1.pack(anchor=W, pady=5)

        rb2 = tb.Radiobutton(opt_frame, text="售卖模式 (批量选中垃圾，一键卖出)", variable=self.strat_var, value="sell",
                             bootstyle="warning")
        rb2.pack(anchor=W, pady=5)

        tb.Separator(opt_frame).pack(fill=X, pady=10)

        self.chk_unfav = tb.BooleanVar(value=False)
        tb.Checkbutton(opt_frame, text="允许取消已有的收藏 (Unfavorite)", variable=self.chk_unfav,
                       bootstyle="danger-round-toggle").pack(anchor=W)

        # 2. 操作区
        act_frame = tb.Frame(self)
        act_frame.pack(fill=X, pady=20)

        tb.Button(act_frame, text="启动清理机器人", bootstyle="warning", width=20).pack(side=LEFT)
        tb.Button(act_frame, text="校准光标 (Debug)", bootstyle="outline-info").pack(side=LEFT, padx=20)