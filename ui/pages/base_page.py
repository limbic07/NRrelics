# --- START OF FILE ui/pages/base_page.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *


class BasePage(tb.Frame):
    def __init__(self, master, title="页面标题", **kwargs):
        super().__init__(master, **kwargs)
        # 统一背景色
        self.configure(bootstyle="default")

        # 页面标题栏
        self.header = tb.Frame(self)
        self.header.pack(fill=X, pady=(0, 20))

        # 标题文字
        tb.Label(self.header, text=title, font=("Microsoft YaHei", 24, "bold"), bootstyle="primary").pack(side=LEFT)

        # 分割线
        tb.Separator(self, orient=HORIZONTAL).pack(fill=X, pady=(10, 20))