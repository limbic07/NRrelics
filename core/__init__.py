"""核心模块 - 延迟导入以加快启动速度"""

# 不在顶层导入 OCREngine，避免启动时加载 cnocr 等重型库
# OCREngine 将在后台线程中按需导入

__all__ = ['OCREngine']

def __getattr__(name):
    """延迟导入核心类"""
    if name == 'OCREngine':
        from .ocr_engine import OCREngine
        return OCREngine
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
