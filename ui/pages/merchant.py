# --- START OF FILE ui/pages/merchant.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ui.pages.base_page import BasePage


class MerchantPage(BasePage):
    def __init__(self, master):
        super().__init__(master, title="自动购买")

        # 1. 控制卡片
        ctrl_frame = tb.Labelframe(self, text="控制台", padding=20, bootstyle="primary")
        ctrl_frame.pack(fill=X, pady=10)

        # 状态指示
        self.status_lbl = tb.Label(ctrl_frame, text="● 已停止", font=("Helvetica", 14), bootstyle="danger")
        self.status_lbl.pack(side=LEFT, padx=20)

        # 按钮组
        btn_group = tb.Frame(ctrl_frame)
        btn_group.pack(side=RIGHT)

        tb.Button(btn_group, text="▶ 开始挂机", bootstyle="success", width=15).pack(side=LEFT, padx=5)
        tb.Button(btn_group, text="⏹ 停止 (F11)", bootstyle="danger", width=15, state="disabled").pack(side=LEFT,
                                                                                                       padx=5)

        # 2. 实时日志
        log_frame = tb.Labelframe(self, text="运行日志", padding=10, bootstyle="info")
        log_frame.pack(fill=BOTH, expand=True, pady=10)

        self.log_text = tb.Text(log_frame, height=10, state="normal")
        self.log_text.pack(fill=BOTH, expand=True)
        self.log_text.insert(END, "系统就绪... 等待指令。\n")