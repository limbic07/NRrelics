"""页面模块 - 延迟导入以加快启动速度"""

# 不在顶层导入，避免启动时加载所有页面
# 页面将在 MainWindow._init_pages() 中按需导入

__all__ = ['ShopPage', 'RepoPage', 'SavePage', 'SettingsPage']

def __getattr__(name):
    """延迟导入页面类"""
    if name == 'ShopPage':
        from .page_shop import PageShop
        return PageShop
    elif name == 'RepoPage':
        from .page_repo import RepoPage
        return RepoPage
    elif name == 'SavePage':
        from .page_save import SavePage
        return SavePage
    elif name == 'SettingsPage':
        from .page_settings import SettingsPage
        return SettingsPage
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
