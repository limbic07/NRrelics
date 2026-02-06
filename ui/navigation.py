# --- START OF FILE ui/navigation.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from tkinter import messagebox


class Sidebar(tb.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.main_window = master

        # --- 顶部 Logo ---
        # 如果有 logo.png 可以用 Image, 这里用文字代替
        self.lbl_logo = tb.Label(self, text="NRrelic", font=("Impact", 28), bootstyle="inverse-secondary")
        self.lbl_logo.pack(pady=(40, 5), padx=20, anchor="w")

        tb.Label(self, text="  Elden Ring Bot", font=("Helvetica", 10, "italic"), bootstyle="inverse-secondary").pack(
            pady=(0, 40), padx=20, anchor="w")

        # --- 导航按钮容器 ---
        self.btn_frame = tb.Frame(self, bootstyle="secondary")
        self.btn_frame.pack(fill=BOTH, expand=True)

        self.buttons = {}
        # 为了美观，按钮前面加了 emoji 模拟图标，实际可用 bootstrap-icons
        self._add_nav_btn("🛒 自动购买", "merchant")
        self._add_nav_btn("📦 仓库管理", "inventory")
        self._add_nav_btn("⚙️ 策略配置", "strategy")
        self._add_nav_btn("🔧 全局设置", "settings")

        # --- 底部版本号 (彩蛋入口) ---
        self.dev_clicks = 0
        self.lbl_ver = tb.Label(self, text="v2.0.0-alpha", font=("Consolas", 9), bootstyle="inverse-secondary",
                                cursor="hand2")
        self.lbl_ver.pack(side=BOTTOM, pady=20)
        self.lbl_ver.bind("<Button-1>", self._on_version_click)

    def _add_nav_btn(self, text, page_key):
        btn = tb.Button(
            self.btn_frame,
            text=f"  {text}",
            bootstyle="secondary",
            command=lambda: self.main_window.show_page(page_key),
            width=20,
            anchor="w"  # 文字左对齐
        )
        # 增加一些内边距让按钮看起来更大气
        btn.pack(pady=5, padx=15, ipady=5, fill=X)
        self.buttons[page_key] = btn

    def set_active(self, page_key):
        """ 高亮当前页面的按钮 """
        for key, btn in self.buttons.items():
            if key == page_key:
                btn.configure(bootstyle="primary")  # 选中高亮
            else:
                btn.configure(bootstyle="secondary")  # 未选中

    def _on_version_click(self, event):
        """ 开发者模式解锁彩蛋 """
        self.dev_clicks += 1
        if self.dev_clicks == 5:
            messagebox.showinfo("开发者模式", "🔓 开发者模式已解锁！\n\n现在可以在【全局设置】中访问 SL 回档功能。")
            # 通知 Settings 页面刷新显示
            settings_page = self.main_window.pages.get("settings")
            if settings_page:
                settings_page.unlock_dev_mode()
        elif self.dev_clicks < 5:
            print(f"Dev step: {self.dev_clicks}/5")