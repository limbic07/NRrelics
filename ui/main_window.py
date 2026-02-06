# --- START OF FILE ui/main_window.py ---
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ui.navigation import Sidebar
from ui.pages.merchant import MerchantPage
from ui.pages.inventory import InventoryPage
from ui.pages.strategy import StrategyPage
from ui.pages.settings import SettingsPage


class MainWindow(tb.Window):
    def __init__(self):
        super().__init__(themename="cosmo")  # 推荐主题
        self.title("NRrelic Bot V2.0")
        self.geometry("1200x800")

        # 初始化布局
        self._init_layout()

        # 默认显示第一页
        self.show_page("merchant")

    def _init_layout(self):
        # 1. 侧边栏 (Left)
        self.sidebar = Sidebar(self, width=220, bootstyle="secondary")
        self.sidebar.pack(side=LEFT, fill=Y)

        # 2. 内容区 (Right)
        # 使用一个 Frame 作为容器
        self.content_area = tb.Frame(self, bootstyle="bg")
        self.content_area.pack(side=LEFT, fill=BOTH, expand=True, padx=20, pady=20)

        # 初始化所有页面
        self.pages = {}
        # 注意：这里我们把 self (MainWindow) 传给 page，方便页面访问主窗口数据
        self.pages["merchant"] = MerchantPage(self.content_area)
        self.pages["inventory"] = InventoryPage(self.content_area)
        self.pages["strategy"] = StrategyPage(self.content_area)
        self.pages["settings"] = SettingsPage(self.content_area)

        # 堆叠页面 (Grid 布局让它们重叠在同一个位置)
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        # 配置 Content Area 的 Grid 权重，让页面填满
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

    def show_page(self, page_name):
        """ 切换页面显示 """
        if page_name in self.pages:
            self.pages[page_name].tkraise()
            # 更新侧边栏选中状态
            self.sidebar.set_active(page_name)