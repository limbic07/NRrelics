# --- START OF FILE ui/pages/strategy.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ui.pages.base_page import BasePage


class StrategyPage(BasePage):
    def __init__(self, master):
        super().__init__(master, title="策略配置")

        # 提示
        tb.Label(self, text="此处将放置 V1.3 中的 AttributeSelector 和 PresetEditor 组件", bootstyle="secondary").pack(
            pady=20)

        # 模拟布局
        paned = tb.PanedWindow(self, orient=HORIZONTAL)
        paned.pack(fill=BOTH, expand=True)

        left_frame = tb.Labelframe(paned, text="预设列表", padding=10)
        paned.add(left_frame, weight=1)

        right_frame = tb.Labelframe(paned, text="词条编辑", padding=10)
        paned.add(right_frame, weight=3)

        # 占位内容
        tb.Button(left_frame, text="+ 新建预设", bootstyle="success-outline", width=100).pack(pady=5)
        tb.Treeview(left_frame).pack(fill=BOTH, expand=True)

        tb.Label(right_frame, text="词条库选择器将放在这里...").pack()