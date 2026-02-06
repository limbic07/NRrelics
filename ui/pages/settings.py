# --- START OF FILE ui/pages/settings.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ui.pages.base_page import BasePage


class SettingsPage(BasePage):
    def __init__(self, master):
        super().__init__(master, title="全局设置")

        # 1. 常规设置
        lf_common = tb.Labelframe(self, text="常规选项", padding=15)
        lf_common.pack(fill=X, pady=10)

        tb.Checkbutton(lf_common, text="启动时自动加载上次配置", bootstyle="round-toggle").pack(anchor=W, pady=5)
        tb.Checkbutton(lf_common, text="操作完成后播放提示音", bootstyle="round-toggle").pack(anchor=W, pady=5)

        # 2. 开发者选项 (默认隐藏)
        # 我们先创建它，但不 pack
        self.lf_dev = tb.Labelframe(self, text="🔧 开发者选项 (Dev Mode)", padding=15, bootstyle="danger")

        # 开发者功能内容
        row1 = tb.Frame(self.lf_dev)
        row1.pack(fill=X, pady=5)
        tb.Label(row1, text="存档管理 (SL):", width=15, font=("bold", 10)).pack(side=LEFT)
        tb.Checkbutton(row1, text="启用自动回档 (Save Scumming)", bootstyle="danger-round-toggle").pack(side=LEFT)

        row2 = tb.Frame(self.lf_dev)
        row2.pack(fill=X, pady=5)
        tb.Label(row2, text="调试工具:", width=15, font=("bold", 10)).pack(side=LEFT)
        tb.Button(row2, text="打开实时视觉窗口", bootstyle="outline-danger", width=20).pack(side=LEFT, padx=5)

        # 3. 关于信息
        lf_about = tb.Labelframe(self, text="关于", padding=15)
        lf_about.pack(fill=X, pady=10)

        tb.Label(lf_about, text="NRrelic Bot V2.0", font=("Helvetica", 12, "bold")).pack(anchor=W)
        tb.Label(lf_about, text="Based on RapidOCR & OpenCV").pack(anchor=W)
        tb.Label(lf_about, text="Designed for Elden Ring: Nightreign").pack(anchor=W)

    def unlock_dev_mode(self):
        """ 由 Navigation 调用，显示开发者选项 """
        # 将开发者选项插入到关于信息之前
        self.lf_dev.pack(fill=X, pady=10, before=self.children[list(self.children.keys())[-1]])