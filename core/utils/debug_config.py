"""
调试配置和工具
统一管理所有调试功能
"""

import time
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from .path import get_user_data_path


# ==================== 全局调试开关 ====================
DEBUG_ENABLED = True  # 改为False关闭所有调试功能


class DebugTimer:
    """精准的时间记录工具"""

    def __init__(self):
        self.timers = {}
        self.records = []

    def start(self, name: str):
        """开始计时"""
        self.timers[name] = time.time()

    def end(self, name: str) -> float:
        """结束计时，返回耗时（毫秒）"""
        if name not in self.timers:
            return 0
        elapsed = (time.time() - self.timers[name]) * 1000
        del self.timers[name]
        return elapsed

    def record(self, name: str, elapsed_ms: float):
        """记录耗时"""
        self.records.append({
            "name": name,
            "elapsed_ms": elapsed_ms,
            "timestamp": datetime.now().isoformat()
        })

    def get_summary(self) -> str:
        """获取时间统计摘要（按流程分析）"""
        if not self.records:
            return ""

        # 计算总耗时
        total_time = sum(r["elapsed_ms"] for r in self.records)

        # 生成报告
        summary = "\n" + "="*80 + "\n"
        summary += "【耗时统计分析 - 流程分解】\n"
        summary += "="*80 + "\n\n"

        # 1. 顶层流程分析
        summary += "【顶层流程】\n"
        summary += "-"*80 + "\n"

        top_level_ops = {}
        for record in self.records:
            name = record["name"]
            # 提取顶层操作（不包含"第X个遗物"的细节）
            if "个遗物" not in name:
                if name not in top_level_ops:
                    top_level_ops[name] = []
                top_level_ops[name].append(record["elapsed_ms"])

        for op_name in sorted(top_level_ops.keys()):
            times = top_level_ops[op_name]
            total = sum(times)
            count = len(times)
            avg = total / count
            percentage = (total / total_time * 100) if total_time > 0 else 0

            summary += f"{op_name}:\n"
            summary += f"  总耗时: {total:.2f}ms ({percentage:.1f}%)\n"
            summary += f"  执行次数: {count}次\n"
            summary += f"  平均耗时: {avg:.2f}ms/次\n"
            if len(times) > 1:
                summary += f"  范围: {min(times):.2f}ms ~ {max(times):.2f}ms\n"
            summary += "\n"

        # 2. 单次购买循环分析（处理10个遗物）
        summary += "【单次购买循环 - 处理10个遗物】\n"
        summary += "-"*80 + "\n"

        # 找出所有"处理10个遗物总耗时"的记录
        process_times = []
        for record in self.records:
            if record["name"] == "处理10个遗物总耗时":
                process_times.append(record["elapsed_ms"])

        if process_times:
            avg_process_time = sum(process_times) / len(process_times)
            summary += f"处理10个遗物平均耗时: {avg_process_time:.2f}ms\n"
            summary += f"  范围: {min(process_times):.2f}ms ~ {max(process_times):.2f}ms\n\n"

            # 分析单个遗物的平均耗时
            summary += "【单个遗物处理流程】\n"
            summary += "-"*80 + "\n"

            # 统计每个遗物的各个操作
            relic_ops = {}
            for record in self.records:
                name = record["name"]
                if "个遗物" in name:
                    # 提取操作类型
                    if "截图" in name:
                        op_type = "截图"
                    elif "OCR总耗时" in name:
                        op_type = "OCR识别"
                    elif "词条匹配" in name:
                        op_type = "词条匹配"
                    else:
                        continue

                    if op_type not in relic_ops:
                        relic_ops[op_type] = []
                    relic_ops[op_type].append(record["elapsed_ms"])

            # 计算单个遗物的平均耗时
            single_relic_total = 0
            for op_type in ["截图", "OCR识别", "词条匹配"]:
                if op_type in relic_ops:
                    times = relic_ops[op_type]
                    avg = sum(times) / len(times)
                    single_relic_total += avg
                    percentage = (avg / avg_process_time * 100) if avg_process_time > 0 else 0
                    summary += f"  {op_type}: {avg:.2f}ms ({percentage:.1f}%)\n"

            summary += f"  单个遗物总耗时: {single_relic_total:.2f}ms\n"
            summary += f"  10个遗物总耗时: {single_relic_total * 10:.2f}ms\n\n"

        # 3. 性能指标总结
        summary += "【性能指标总结】\n"
        summary += "-"*80 + "\n"
        summary += f"总耗时: {total_time:.2f}ms\n"

        # 计算购买循环次数
        purchase_count = 0
        for record in self.records:
            if record["name"] == "处理10个遗物总耗时":
                purchase_count += 1

        if purchase_count > 0:
            total_relics = purchase_count * 10
            avg_time_per_relic = total_time / total_relics
            summary += f"购买循环次数: {purchase_count}次\n"
            summary += f"处理遗物总数: {total_relics}个\n"
            summary += f"平均每个遗物耗时: {avg_time_per_relic:.2f}ms\n"

        summary += "="*80 + "\n"

        return summary

    def clear(self):
        """清空记录"""
        self.records.clear()
        self.timers.clear()


class AffixRecorder:
    """词条记录工具"""

    def __init__(self):
        self.correction_failed = defaultdict(lambda: {"count": 0, "is_positive": None, "raw_text": None})  # 纠错失败
        self.correction_success = defaultdict(lambda: {"count": 0, "is_positive": None})  # 纠错成功

    def record_failed(self, text: str, is_positive: bool, raw_text: str = None):
        """记录纠错失败的词条"""
        self.correction_failed[text]["count"] += 1
        self.correction_failed[text]["is_positive"] = is_positive
        # 保存原始OCR文本（第一次出现时保存）
        if self.correction_failed[text]["raw_text"] is None and raw_text:
            self.correction_failed[text]["raw_text"] = raw_text

    def record_success(self, text: str, is_positive: bool):
        """记录纠错成功的词条"""
        self.correction_success[text]["count"] += 1
        self.correction_success[text]["is_positive"] = is_positive

    def save_to_file(self, filename: str = None):
        """保存词条到文件"""
        if not filename:
            filename = f"affixes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        filepath = get_user_data_path(os.path.join("logs", filename))

        # 确保logs目录存在
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("词条记录\n")
            f.write("="*80 + "\n\n")

            # 纠错成功的词条
            if self.correction_success:
                f.write(f"纠错成功的词条 ({len(self.correction_success)}个):\n")
                f.write("-"*80 + "\n")
                for text in sorted(self.correction_success.keys()):
                    info = self.correction_success[text]
                    affix_type = "正面" if info["is_positive"] else "负面"
                    f.write(f"[纠错成功] [{affix_type}] {text} (出现{info['count']}次)\n")
                f.write("\n")

            # 纠错失败的词条
            if self.correction_failed:
                f.write(f"纠错失败的词条 ({len(self.correction_failed)}个):\n")
                f.write("-"*80 + "\n")
                for text in sorted(self.correction_failed.keys()):
                    info = self.correction_failed[text]
                    affix_type = "正面" if info["is_positive"] else "负面"
                    raw_text_str = f" (原始OCR: {info['raw_text']})" if info["raw_text"] else ""
                    f.write(f"[纠错失败] [{affix_type}] {text}{raw_text_str} (出现{info['count']}次)\n")
                f.write("\n")

            f.write("="*80 + "\n")
            f.write(f"总计: {len(self.correction_success) + len(self.correction_failed)}个不同词条\n")
            f.write(f"  纠错成功: {len(self.correction_success)}个\n")
            f.write(f"  纠错失败: {len(self.correction_failed)}个\n")

        return filepath

    def clear(self):
        """清空记录"""
        self.correction_failed.clear()
        self.correction_success.clear()


# 全局实例
debug_timer = DebugTimer()
affix_recorder = AffixRecorder()


def log_debug(message: str):
    """调试日志"""
    if DEBUG_ENABLED:
        print(f"{message}")
