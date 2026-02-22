"""
全面的日志系统 - 支持文件日志、错误追踪、性能监控
所有日志相关功能集中在此模块
"""

import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any


def get_user_data_path(relative_path: str) -> str:
    """获取用户数据路径"""
    from .path import get_user_data_path as _get_user_data_path
    return _get_user_data_path(relative_path)


class LoggerConfig:
    """日志配置"""
    # 日志级别
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    # 日志格式
    DETAILED_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    SIMPLE_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    CONSOLE_FORMAT = '[%(levelname)s] %(message)s'

    # 日志文件配置
    LOG_DIR = "logs"
    MAX_BYTES = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5


class AppLogger:
    """应用日志管理器 - 单例模式"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if AppLogger._initialized:
            return

        self.logger = logging.getLogger("NRrelics")
        self.logger.setLevel(LoggerConfig.DEBUG)

        # 清空已有的处理器
        self.logger.handlers.clear()

        # 创建日志目录
        self.log_dir = Path(get_user_data_path(LoggerConfig.LOG_DIR))
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 1. 文件处理器 - 详细日志
        self._setup_file_handler()

        # 2. 控制台处理器 - 简化日志
        self._setup_console_handler()

        # 3. 错误日志处理器 - 单独记录错误
        self._setup_error_handler()

        AppLogger._initialized = True

    def _setup_file_handler(self):
        """设置文件处理器"""
        log_file = self.log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"

        # 使用轮转文件处理器
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file),
            maxBytes=LoggerConfig.MAX_BYTES,
            backupCount=LoggerConfig.BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(LoggerConfig.DEBUG)
        file_handler.setFormatter(logging.Formatter(LoggerConfig.DETAILED_FORMAT))
        self.logger.addHandler(file_handler)

    def _setup_console_handler(self):
        """设置控制台处理器"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LoggerConfig.INFO)
        console_handler.setFormatter(logging.Formatter(LoggerConfig.CONSOLE_FORMAT))
        self.logger.addHandler(console_handler)

    def _setup_error_handler(self):
        """设置错误日志处理器"""
        error_log_file = self.log_dir / f"error_{datetime.now().strftime('%Y%m%d')}.log"

        error_handler = logging.handlers.RotatingFileHandler(
            str(error_log_file),
            maxBytes=LoggerConfig.MAX_BYTES,
            backupCount=LoggerConfig.BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(LoggerConfig.ERROR)
        error_handler.setFormatter(logging.Formatter(LoggerConfig.DETAILED_FORMAT))
        self.logger.addHandler(error_handler)

    # ==================== 基础日志方法 ====================

    def debug(self, message: str, *args, **kwargs):
        """调试日志"""
        self.logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """信息日志"""
        self.logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """警告日志"""
        self.logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, exc_info=False, **kwargs):
        """错误日志"""
        self.logger.error(message, *args, exc_info=exc_info, **kwargs)

    def critical(self, message: str, *args, exc_info=False, **kwargs):
        """严重错误日志"""
        self.logger.critical(message, *args, exc_info=exc_info, **kwargs)

    def exception(self, message: str = "异常发生"):
        """异常日志 - 自动包含堆栈跟踪"""
        self.logger.exception(message)

    # ==================== 业务日志方法 ====================

    def log_exception(self, exc: Exception, context: str = ""):
        """记录异常详情"""
        error_msg = f"异常: {type(exc).__name__}"
        if context:
            error_msg = f"{context} - {error_msg}"
        error_msg += f"\n详情: {str(exc)}"
        error_msg += f"\n堆栈:\n{traceback.format_exc()}"
        self.logger.error(error_msg)

    def log_performance(self, operation: str, duration_ms: float, success: bool = True):
        """记录性能信息"""
        status = "成功" if success else "失败"
        self.logger.info(f"[性能] {operation}: {duration_ms:.2f}ms ({status})")

    # ==================== OCR 相关日志 ====================

    def log_ocr_start(self, mode: str):
        """OCR开始"""
        self.logger.info(f"[OCR] 开始识别 (模式: {mode})")

    def log_ocr_result(self, entries: list, positive_count: int, negative_count: int, duration_ms: float):
        """记录OCR结果"""
        self.logger.info(
            f"[OCR] 识别完成 - 词条数: {len(entries)}, 正面: {positive_count}, 负面: {negative_count}, 耗时: {duration_ms:.2f}ms"
        )

    def log_ocr_error(self, error: str, retry_count: int = 0):
        """OCR错误"""
        msg = f"[OCR] 识别失败: {error}"
        if retry_count > 0:
            msg += f" (重试 {retry_count})"
        self.logger.warning(msg)

    def log_vocabulary_loaded(self, mode: str, total: int, pos: int = 0, neg: int = 0):
        """词条库加载"""
        if mode == "deepnight":
            self.logger.info(f"[词条库] 加载完成 (模式: {mode}, 总计: {total}, 正面: {pos}, 负面: {neg})")
        else:
            self.logger.info(f"[词条库] 加载完成 (模式: {mode}, 总计: {total})")

    # ==================== 遗物检测相关日志 ====================

    def log_relic_detected(self, state: str, position: int = 0):
        """遗物检测"""
        self.logger.debug(f"[遗物检测] 状态: {state}, 位置: {position}")

    def log_matching_result(self, relic_state: str, qualified: bool, affixes: list, preset_name: str = ""):
        """记录匹配结果"""
        status = "合格" if qualified else "不合格"
        affix_str = ", ".join([a.get("text", "") for a in affixes[:3]])
        if len(affixes) > 3:
            affix_str += f", ... (共{len(affixes)}条)"
        msg = f"[匹配] 状态: {relic_state}, 结果: {status}, 词条: {affix_str}"
        if preset_name:
            msg += f", 预设: {preset_name}"
        self.logger.info(msg)

    # ==================== 操作相关日志 ====================

    def log_action(self, action: str, details: str = ""):
        """记录执行的操作"""
        msg = f"[操作] {action}"
        if details:
            msg += f" - {details}"
        self.logger.info(msg)

    def log_action_error(self, action: str, error: str):
        """操作失败"""
        self.logger.error(f"[操作失败] {action}: {error}")

    def log_sell(self, count: int, total: int = 0):
        """记录售出"""
        msg = f"[售出] 已标记 {count} 件遗物"
        if total > 0:
            msg += f" (总计: {total})"
        self.logger.info(msg)

    def log_favorite(self, count: int, total: int = 0):
        """记录收藏"""
        msg = f"[收藏] 已标记 {count} 件遗物"
        if total > 0:
            msg += f" (总计: {total})"
        self.logger.info(msg)

    def log_skip(self, reason: str, count: int = 1):
        """记录跳过"""
        self.logger.debug(f"[跳过] {reason} (数量: {count})")

    # ==================== 自动化相关日志 ====================

    def log_window_detected(self, window_title: str, resolution: tuple = None):
        """窗口检测"""
        msg = f"[窗口] 检测到: {window_title}"
        if resolution:
            msg += f" (分辨率: {resolution[0]}x{resolution[1]})"
        self.logger.info(msg)

    def log_window_error(self, error: str):
        """窗口错误"""
        self.logger.error(f"[窗口] 错误: {error}")

    def log_automation_start(self, operation: str, mode: str = ""):
        """自动化开始"""
        msg = f"[自动化] 开始 {operation}"
        if mode:
            msg += f" (模式: {mode})"
        self.logger.info(msg)

    def log_automation_stop(self, operation: str, reason: str = ""):
        """自动化停止"""
        msg = f"[自动化] 停止 {operation}"
        if reason:
            msg += f" (原因: {reason})"
        self.logger.info(msg)

    def log_automation_error(self, operation: str, error: str):
        """自动化错误"""
        self.logger.error(f"[自动化] {operation} 失败: {error}")

    # ==================== 预设相关日志 ====================

    def log_preset_loaded(self, preset_name: str, affix_count: int):
        """预设加载"""
        self.logger.info(f"[预设] 加载: {preset_name} (词条数: {affix_count})")

    def log_preset_saved(self, preset_name: str):
        """预设保存"""
        self.logger.info(f"[预设] 保存: {preset_name}")

    def log_preset_deleted(self, preset_name: str):
        """预设删除"""
        self.logger.info(f"[预设] 删除: {preset_name}")

    def log_preset_error(self, operation: str, error: str):
        """预设操作错误"""
        self.logger.error(f"[预设] {operation} 失败: {error}")

    # ==================== 存档相关日志 ====================

    def log_save_backup(self, steam_id: str, backup_name: str):
        """存档备份"""
        self.logger.info(f"[存档] 备份: {steam_id} -> {backup_name}")

    def log_save_restore(self, steam_id: str, backup_name: str):
        """存档恢复"""
        self.logger.info(f"[存档] 恢复: {steam_id} <- {backup_name}")

    def log_save_error(self, operation: str, error: str):
        """存档操作错误"""
        self.logger.error(f"[存档] {operation} 失败: {error}")

    # ==================== 统计相关日志 ====================

    def log_session_start(self, session_type: str):
        """会话开始"""
        self.logger.info(f"[会话] 开始 - {session_type}")

    def log_session_end(self, session_type: str, stats: Dict[str, Any]):
        """会话结束"""
        stats_str = ", ".join([f"{k}: {v}" for k, v in stats.items()])
        self.logger.info(f"[会话] 结束 - {session_type} ({stats_str})")

    def log_session_error(self, session_type: str, error: str):
        """会话错误"""
        self.logger.error(f"[会话] {session_type} 异常: {error}")

    # ==================== 文件操作相关日志 ====================

    def log_file_operation(self, operation: str, filepath: str, success: bool = True):
        """文件操作"""
        status = "成功" if success else "失败"
        self.logger.info(f"[文件] {operation}: {filepath} ({status})")

    def log_file_error(self, operation: str, filepath: str, error: str):
        """文件操作错误"""
        self.logger.error(f"[文件] {operation} 失败: {filepath} - {error}")

    # ==================== 配置相关日志 ====================

    def log_config_loaded(self, config_name: str):
        """配置加载"""
        self.logger.info(f"[配置] 加载: {config_name}")

    def log_config_saved(self, config_name: str):
        """配置保存"""
        self.logger.info(f"[配置] 保存: {config_name}")

    def log_config_error(self, operation: str, error: str):
        """配置操作错误"""
        self.logger.error(f"[配置] {operation} 失败: {error}")

    # ==================== 工具方法 ====================

    def get_log_file_path(self) -> str:
        """获取当前日志文件路径"""
        return str(self.log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log")

    def get_error_log_file_path(self) -> str:
        """获取错误日志文件路径"""
        return str(self.log_dir / f"error_{datetime.now().strftime('%Y%m%d')}.log")

    def get_log_directory(self) -> str:
        """获取日志目录"""
        return str(self.log_dir)

    def get_recent_logs(self, lines: int = 100) -> list:
        """获取最近的日志"""
        log_file = self.get_log_file_path()
        if not os.path.exists(log_file):
            return []

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                return all_lines[-lines:] if len(all_lines) > lines else all_lines
        except Exception as e:
            self.logger.error(f"读取日志失败: {e}")
            return []


# 全局日志实例
logger = AppLogger()


def get_logger(name: str = "NRrelics") -> logging.Logger:
    """获取日志记录器"""
    return logging.getLogger(name)
