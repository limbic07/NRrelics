"""
游戏物品词条OCR识别工具
按F11开始识别，自动循环次数可定义，结果保存到文件
"""

import time
import re
import cv2
import numpy as np
import os
from datetime import datetime
from cnocr import CnOcr
import pyautogui
import pydirectinput
import keyboard
from rapidfuzz import fuzz

# ==================== 配置区域 ====================

# 六行单行ROI区域配置（普通模式和深夜模式通用）
# X轴范围：
x_start = 1107
x_end = 1700

# Y轴范围：这 6 行文本其实分为 3 组，组与组之间有轻微的缝隙
line_coords = [
    # 第一组
    (810, 833),  # 第 1 行
    (833, 858),  # 第 2 行

    # 第二组
    (870, 893),  # 第 3 行
    (893, 917),  # 第 4 行

    # 第三组
    (930, 954),  # 第 5 行
    (954, 978)   # 第 6 行
]

# 循环次数
LOOP_COUNT = 500


# 输出文件路径
OUTPUT_FILE = "ocr_results.txt"

# 遗物类型配置
RELIC_TYPE = "normal"  # 可选: "normal" 或 "deepnight"

# ==================== 断行字典配置说明 ====================
# LINE_BREAK_DICT 用于处理OCR识别时的断行问题
#
# 使用场景：
# 当某些词条在OCR识别时经常被断成两行，可以在这里配置合并规则
#
# 配置格式：
# {
#     "第一行的关键词": "完整的词条内容（可选，用于验证）"
# }
#
# 工作原理：
# 1. OCR识别后，在 split_entries() 中检查每一行
# 2. 如果前一行以字典中的关键词开头，则将当前行合并到前一行
# 3. 合并后的词条会在 correct_entries() 中与词条库匹配
#
# 断行合并字典
LINE_BREAK_DICT = {
    "【追踪者】发动技艺时，轻攻击能使出": "【追踪者】发动技艺时，轻攻击能使出缠绕火焰的追加攻击（仅限大剑）",  # 会将下一行合并到这一行
    "【铁之眼】技艺会附加引发异常状态中毒的效果": "【铁之眼】技艺会附加引发异常状态中毒的效果对上陷入中毒的敌人，能给予大伤害",
    "【女爵】短剑连击的最后攻击命中时，": "【女爵】短剑连击的最后攻击命中时，能对着周围的敌人，再次上演最近做过的行动",
    "【女爵】从背后使出致命一击后": "【女爵】从背后使出致命一击后自己的身影会变得难以辨识，并消除脚步声",
    "【无赖】在技艺发动期间，受到攻击时": "【无赖】在技艺发动期间，受到攻击时能提升攻击力与精力上限",
    "【复仇者】发动绝招时，能以自己的血量为代价": "【复仇者】发动绝招时，能以自己的血量为代价完全恢复周围我方人物的血量",
    "【隐士】发动绝招时": "【隐士】发动绝招时自己陷入异常状态出血，提升攻击力",
    "【执行者】提升技艺发动期间的攻击力": "【执行者】提升技艺发动期间的攻击力但攻击时会降低减伤率",
    "【执行者】在技艺发动期间": "【执行者】在技艺发动期间妖刀进入解放状态时，能恢复血量",
    "【送葬者】使用祷告将辅助效果附加在自己身上时": "【送葬者】使用祷告将辅助效果附加在自己身上时提升物理攻击力",
}

# 词条纠错配置
CORRECTION_CONFIG = {
    "enabled": True,              # 是否启用词条纠错
    "similarity_threshold": 0.85,  # 相似度阈值（60%）
    "max_retry": 3,               # 未知词条最大重试次数
    "data_dir": "data",           # 词条库目录
}


# ==================== 词条库加载器 ====================

class VocabularyLoader:
    """词条库加载器"""
    def __init__(self, data_dir: str, relic_type: str):
        self.data_dir = data_dir
        self.relic_type = relic_type
        self.vocabulary = []
        self.load_vocabulary()

    def load_vocabulary(self):
        """根据遗物类型加载对应的词条库"""
        if self.relic_type == "normal":
            files = ["normal.txt", "normal_special.txt"]
        elif self.relic_type == "deepnight":
            files = ["deepnight_pos.txt", "deepnight_neg.txt"]
        else:
            raise ValueError(f"Unknown relic type: {self.relic_type}")

        for filename in files:
            filepath = os.path.join(self.data_dir, filename)
            if not os.path.exists(filepath):
                print(f"[警告] 词条库文件不存在: {filepath}")
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:  # 跳过空行
                        continue

                    # 支持两种格式：
                    # 1. "行号→词条内容" 格式
                    # 2. 直接的词条内容
                    if '→' in line:
                        entry = line.split('→', 1)[1].strip()
                    else:
                        entry = line

                    if entry:
                        self.vocabulary.append(entry)


# ==================== 词条纠错器 ====================

class EntryCorrector:
    """词条纠错器，使用模糊匹配修正OCR错误"""
    def __init__(self, vocabulary: list, threshold: float = 0.8):
        self.vocabulary = vocabulary
        self.threshold = threshold

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个字符串的相似度
        使用 rapidfuzz 的 token_set_ratio 算法
        """
        return fuzz.token_set_ratio(text1, text2) / 100.0

    def correct_entry(self, ocr_text: str) -> tuple:
        """
        纠正单个词条
        计算与所有词条的相似度，选择最相似的
        返回: (corrected_text, similarity, is_corrected)
        """
        best_match = None
        best_similarity = 0.0

        # 计算与所有词条的相似度，找出最相似的
        for vocab_entry in self.vocabulary:
            similarity = self._calculate_similarity(ocr_text, vocab_entry)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = vocab_entry

        # 只有最相似的词条超过阈值才纠正
        if best_similarity >= self.threshold:
            return (best_match, best_similarity, True)
        else:
            return (ocr_text, best_similarity, False)


# ==================== 文本处理函数 ====================

def postprocess_text(text: str) -> str:
    """OCR文本后处理：符号标准化和清理"""
    # 0. 全角数字 → 半角数字
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))

    # 1. OCR常见误识别修正（字母 → 数字）
    # 词条库不包含英文字母，所以将常见误识别的字母转换为数字
    text = text.replace('I', '1')  # 大写I → 1
    text = text.replace('l', '1')  # 小写l → 1
    text = text.replace('O', '0')  # 大写O → 0
    text = text.replace('o', '0')  # 小写o → 0
    text = text.replace('S', '5')  # 大写S → 5
    text = text.replace('s', '5')  # 小写s → 5
    text = text.replace('B', '8')  # 大写B → 8
    text = text.replace('Z', '2')  # 大写Z → 2
    text = text.replace('z', '2')  # 小写z → 2

    # 1.5. 罗马数字 → 阿拉伯数字
    text = text.replace('Ⅰ', '1')  # 罗马数字Ⅰ → 1
    text = text.replace('Ⅱ', '2')  # 罗马数字Ⅱ → 2
    text = text.replace('Ⅲ', '3')  # 罗马数字Ⅲ → 3
    text = text.replace('Ⅳ', '4')  # 罗马数字Ⅳ → 4
    text = text.replace('Ⅴ', '5')  # 罗马数字Ⅴ → 5

    # 2. 加号标准化：十、＋(全角)、⁺(上标) → +(半角)
    text = text.replace('十', '+').replace('＋', '+')

    # 3. 括号标准化：[](){}  → 【】
    text = text.replace('[', '【').replace(']', '】')
    text = text.replace('(', '【').replace(')', '】')
    text = text.replace('{', '【').replace('}', '】')

    # 4. 删除引号：""
    text = text.replace('"', '').replace('"', '')

    # 5. 删除所有空格
    text = text.replace(' ', '').replace('　', '')

    # 6. 标点标准化：英文标点 → 中文标点
    text = text.replace(',', '，')
    text = text.replace(':', '：')
    text = text.replace(';', '；')

    # 7. 修正分隔符：数字1中文 → 数字|中文
    text = re.sub(r'(\+\d+)\s*1\s*([\u4e00-\u9fa5])', r'\1|\2', text)

    # 8. 删除包含※符号或"仅限能使用的武器类别"的行
    lines = text.split('\n')
    filtered_lines = []
    for line in lines:
        if '※' not in line and '仅限能使用的' not in line and '武器类别' not in line:
            filtered_lines.append(line)
    text = '\n'.join(filtered_lines)

    return text


def split_entries(text: str) -> list:
    """将文本按词条分割"""
    text = postprocess_text(text)

    # 按 | 分割词条
    entries = text.split('|')

    # 处理分行问题：将每一行作为单独的词条
    processed_entries = []
    for entry in entries:
        lines = entry.split('\n')
        for line in lines:
            line = line.strip()
            if line:  # 只添加非空行
                processed_entries.append(line)

    return processed_entries


def correct_entries(entries: list, corrector: EntryCorrector) -> list:
    """
    对词条列表进行纠错，支持动态断行合并

    逻辑：
    1. 对于未被纠正的词条，尝试与下一行合并
    2. 清洗规则：删除下一行的前导噪声（如'万'、'了'、'可'、'"'、空格）
    3. 计算相似度：对比原始行和合并行与词条库的匹配分数
    4. 决策：仅当 Score(合并) > Score(原始) 时才合并
    """
    corrected_entries = []
    skip_next = False

    # 定义需要清洗的前导噪声字符
    NOISE_CHARS = {'万', '了', '可', '"', '"', ''', ''', ' ', '　'}

    def clean_leading_noise(text: str) -> str:
        """清洗文本前导的噪声字符"""
        i = 0
        while i < len(text) and text[i] in NOISE_CHARS:
            i += 1
        return text[i:]

    for i, entry in enumerate(entries):
        if skip_next:
            skip_next = False
            continue

        # 获取当前行的相似度信息
        corrected_text, similarity, is_corrected = corrector.correct_entry(entry)

        # 检查是否需要尝试合并：当前行未被纠正且存在下一行
        should_try_merge = (
            not is_corrected and  # 当前行未被纠正
            i + 1 < len(entries)  # 存在下一行
        )

        if should_try_merge:
            next_entry = entries[i + 1]

            # 清洗下一行的前导噪声
            cleaned_next = clean_leading_noise(next_entry)

            if cleaned_next:  # 清洗后仍有内容
                # 创建候选合并字符串
                merged_candidate = entry + cleaned_next

                # 计算合并后的相似度
                merged_text, merged_similarity, _ = corrector.correct_entry(merged_candidate)

                # 决策：仅当合并后相似度更高时才合并
                if merged_similarity > similarity:
                    print(f"    [动态合并] {entry}")
                    print(f"             + {next_entry}")
                    print(f"             -> {merged_text} (原始: {similarity:.2%}, 合并: {merged_similarity:.2%})")
                    corrected_entries.append(merged_text)
                    skip_next = True
                    continue

        # 输出纠错结果
        if is_corrected:
            print(f"    [纠正] {entry} -> {corrected_text} (相似度: {similarity:.2%})")
        else:
            print(f"    [保留] {entry} (最高相似度: {similarity:.2%})")

        corrected_entries.append(corrected_text)

    return corrected_entries


# ==================== 图像处理函数 ====================

def capture_line_rois() -> list:
    """截取屏幕单行ROI区域（6行通用）"""
    screenshot = pyautogui.screenshot()
    image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    line_images = []
    for y_start, y_end in line_coords:
        line_image = image[y_start:y_end, x_start:x_end]
        line_images.append(line_image)

    return line_images


# ==================== OCR引擎 ====================

class OCREngine:
    """CnOCR引擎封装"""
    def __init__(self, relic_type: str):
        print("正在加载OCR模型...")
        self.relic_type = relic_type

        try:
            # 使用默认模型
            self.engine = CnOcr()
            print(f"OCR模型加载完成 ({relic_type}模式)")

        except Exception as e:
            print(f"[错误] OCR模型加载失败: {e}")
            raise

        # 加载词条库
        self.corrector = None
        if CORRECTION_CONFIG["enabled"]:
            print("正在加载词条库...")
            try:
                vocab_loader = VocabularyLoader(
                    CORRECTION_CONFIG["data_dir"],
                    relic_type
                )
                self.corrector = EntryCorrector(
                    vocab_loader.vocabulary,
                    CORRECTION_CONFIG["similarity_threshold"]
                )
                print(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条)")
            except Exception as e:
                print(f"[警告] 词条库加载失败: {e}")
                print("将继续使用OCR结果，不进行纠错")


    def ocr_single_line(self, image) -> tuple:
        """执行单行OCR识别（深夜模式）"""
        result = self.engine.ocr_for_single_line(image)
        if result is None:
            return "", 0.0

        # ocr_for_single_line 返回字典格式
        text = result.get('text', '')
        score = result.get('score', 0.0)

        # 清洗单字符"一"（空词条"-"的误识别）
        text = text.strip()
        if text == "一":
            return "", 0.0

        return text, score


    def ocr_multi_line(self, images) -> tuple:
        """执行多行OCR识别（普通模式），对6行分别使用单行识别"""
        if not isinstance(images, list):
            # 如果不是列表，转换为列表
            images = [images]

        all_text = []
        all_scores = []
        for line_image in images:
            text, score = self.ocr_single_line(line_image)
            if text:
                all_text.append(text)
                all_scores.append(score)

        # 拼接所有文本
        combined_text = '\n'.join(all_text)

        # 处理完整的文本（符号标准化、分割词条）
        all_raw_entries = split_entries(combined_text)

        # 对所有行进行纠错
        correction_time = 0.0
        if self.corrector and CORRECTION_CONFIG["enabled"]:
            correction_start = time.time()
            all_raw_entries = correct_entries(all_raw_entries, self.corrector)
            correction_time = time.time() - correction_start

        return all_raw_entries, correction_time, all_scores


    def ocr(self, image_or_images) -> tuple:
        """执行OCR，根据模式自动选择单行或多行识别"""
        if self.relic_type == "deepnight":
            # 深夜模式：单行识别
            if isinstance(image_or_images, list):
                # 多个单行图像
                all_text = []
                all_scores = []
                for line_image in image_or_images:
                    text, score = self.ocr_single_line(line_image)
                    if text:
                        all_text.append(text)
                        all_scores.append(score)

                # 拼接所有文本
                combined_text = '\n'.join(all_text)

                # 处理完整的文本（符号标准化、分割词条）
                all_entries = split_entries(combined_text)

                # 对所有行进行纠错（包括动态断行合并）
                correction_time = 0.0
                if self.corrector and CORRECTION_CONFIG["enabled"]:
                    correction_start = time.time()
                    all_entries = correct_entries(all_entries, self.corrector)
                    correction_time = time.time() - correction_start

                return all_entries, correction_time, all_scores
            else:
                # 单个图像
                text, score = self.ocr_single_line(image_or_images)
                if text:
                    # 处理文本
                    entries = split_entries(text)
                    # 纠错
                    correction_time = 0.0
                    if self.corrector and CORRECTION_CONFIG["enabled"]:
                        correction_start = time.time()
                        entries = correct_entries(entries, self.corrector)
                        correction_time = time.time() - correction_start
                    return entries, correction_time, [score]
                else:
                    return [], 0.0, []
        else:
            # 普通模式：多行识别
            return self.ocr_multi_line(image_or_images)


# ==================== 主程序 ====================

def calculate_statistics(all_results: list) -> dict:
    """
    计算详细的统计信息
    返回: 包含各种统计数据的字典
    """
    if not all_results:
        return {}

    # 提取所有时间数据
    capture_times = [r['times']['capture'] for r in all_results]
    ocr_times = [r['times']['ocr'] for r in all_results]
    correction_times = [r['times']['correction'] for r in all_results]
    retry_times = [r['times']['retry'] for r in all_results]
    other_times = [r['times']['other'] for r in all_results]
    total_times = [r['times']['total'] for r in all_results]

    # 计算总和
    total_capture = sum(capture_times)
    total_ocr = sum(ocr_times)
    total_correction = sum(correction_times)
    total_retry = sum(retry_times)
    total_other = sum(other_times)
    total_all = sum(total_times)

    # 计算平均值
    avg_capture = total_capture / len(all_results)
    avg_ocr = total_ocr / len(all_results)
    avg_correction = total_correction / len(all_results)
    avg_retry = total_retry / len(all_results)
    avg_other = total_other / len(all_results)
    avg_total = total_all / len(all_results)

    # 计算占比
    percentage_capture = (total_capture / total_all * 100) if total_all > 0 else 0
    percentage_ocr = (total_ocr / total_all * 100) if total_all > 0 else 0
    percentage_correction = (total_correction / total_all * 100) if total_all > 0 else 0
    percentage_retry = (total_retry / total_all * 100) if total_all > 0 else 0
    percentage_other = (total_other / total_all * 100) if total_all > 0 else 0

    # 统计重试次数
    total_retries = sum(r['retry_count'] for r in all_results)
    items_with_retry = sum(1 for r in all_results if r['retry_count'] > 0)

    return {
        "totals": {
            "capture": total_capture,
            "ocr": total_ocr,
            "correction": total_correction,
            "retry": total_retry,
            "other": total_other,
            "all": total_all
        },
        "averages": {
            "capture": avg_capture,
            "ocr": avg_ocr,
            "correction": avg_correction,
            "retry": avg_retry,
            "other": avg_other,
            "total": avg_total
        },
        "percentages": {
            "capture": percentage_capture,
            "ocr": percentage_ocr,
            "correction": percentage_correction,
            "retry": percentage_retry,
            "other": percentage_other
        },
        "retry_stats": {
            "total_retries": total_retries,
            "items_with_retry": items_with_retry
        }
    }


def save_partial_results(results: list, output_file: str):
    """保存部分识别结果"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"游戏物品词条OCR识别结果（部分）\n")
        f.write(f"{'=' * 50}\n")
        f.write(f"识别次数: {len(results)}\n")
        f.write(f"{'=' * 50}\n\n")

        for result in results:
            f.write(f"[{result['index']}] ({result['time']:.3f}秒)\n")
            for entry in result['entries']:
                f.write(f"  {entry}\n")
            f.write("\n")


def save_unknown_entries(unknown_entries: list, output_file: str):
    """单独保存未知词条"""
    if not unknown_entries:
        return

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"未知词条记录\n")
        f.write(f"{'=' * 70}\n")
        f.write(f"总计: {len(unknown_entries)}条未知词条\n")
        f.write(f"{'=' * 70}\n\n")

        for unknown in unknown_entries:
            f.write(f"[{unknown['index']}] {unknown['entry']}\n")
            f.write(f"    相似度: {unknown['similarity']:.2%}\n\n")

        # 去重统计
        f.write(f"{'=' * 70}\n")
        f.write("去重统计:\n")
        f.write(f"{'=' * 70}\n")
        unique_unknown = {}
        for unknown in unknown_entries:
            entry = unknown['entry']
            if entry not in unique_unknown:
                unique_unknown[entry] = {
                    'count': 0,
                    'similarity': unknown['similarity']
                }
            unique_unknown[entry]['count'] += 1

        for entry in sorted(unique_unknown.keys()):
            info = unique_unknown[entry]
            f.write(f"  {entry}\n")
            f.write(f"    出现次数: {info['count']}, 最高相似度: {info['similarity']:.2%}\n")


def run_game_test():
    """运行游戏内OCR测试"""
    print("=" * 50)
    print("游戏物品词条OCR识别工具")
    print("=" * 50)
    print(f"模式: {RELIC_TYPE}模式 (6行单行识别)")
    print(f"识别区域: X({x_start}-{x_end}), 6行")
    print(f"循环次数: {LOOP_COUNT}")
    print(f"输出文件: {OUTPUT_FILE}")
    print("-" * 50)
    print("按 F11 开始识别测试")
    print("按 ESC 随时停止")
    print("-" * 50)

    # 初始化OCR引擎
    engine = OCREngine(RELIC_TYPE)

    # 等待F11开始
    print("\n等待按下 F11 开始...")
    keyboard.wait('f11')
    print("开始识别!\n")

    # 存储所有结果
    all_results = []
    unknown_entries = []  # 记录未知词条
    start_time = datetime.now()

    for i in range(LOOP_COUNT):
        # 检查是否按下ESC退出
        if keyboard.is_pressed('esc'):
            print("\n检测到ESC，停止测试")
            break

        item_start_time = time.time()  # 单个物品开始时间
        print(f"[{i+1}/{LOOP_COUNT}] 识别中...")

        # 1. 截图时间
        capture_start = time.time()
        images = capture_line_rois()  # 统一使用6行ROI截图
        capture_time = time.time() - capture_start

        # 2. OCR时间（包含纠错）
        ocr_start = time.time()
        entries, correction_time, scores = engine.ocr(images)
        ocr_time = time.time() - ocr_start

        # 输出识别结果和置信度
        if entries:
            print(f"  识别到 {len(entries)} 条词条:")
            for idx, (entry, score) in enumerate(zip(entries, scores), 1):
                print(f"    [{idx}] {entry} (置信度: {score:.2%})")

        # 3. 重试时间
        retry_start = time.time()
        retry_count = 0

        # 检查是否有未知词条或空白词条（仅在启用纠错时检查）
        has_unknown = False
        known_count = 0  # 已知词条数量
        if engine.corrector and CORRECTION_CONFIG["enabled"]:
            for entry in entries:
                # 检查是否为空白词条
                if not entry.strip():
                    has_unknown = True
                    unknown_entries.append({
                        "index": i + 1,
                        "entry": "[空白词条]",
                        "similarity": 0.0
                    })
                    continue

                # 检查是否为未知词条
                _, similarity, is_corrected = engine.corrector.correct_entry(entry)
                if is_corrected:
                    known_count += 1  # 统计已知词条
                else:
                    has_unknown = True
                    unknown_entries.append({
                        "index": i + 1,
                        "entry": entry,
                        "similarity": similarity
                    })

            # 只有当全部都是未知词条或空白时才重试（known_count == 0）
            if has_unknown and known_count == 0:
                print(f"  [警告] 全部为未知词条或空白词条，准备重试...")
                while retry_count < CORRECTION_CONFIG["max_retry"]:
                    print(f"  [重试] {retry_count + 1}/{CORRECTION_CONFIG['max_retry']}")
                    time.sleep(0.5)

                    # 重新截图识别（统一使用6行ROI）
                    images = capture_line_rois()
                    entries, correction_time_retry, scores = engine.ocr(images)
                    correction_time += correction_time_retry

                    # 再次检查
                    has_unknown = False
                    known_count = 0
                    for entry in entries:
                        # 检查是否为空白词条
                        if not entry.strip():
                            has_unknown = True
                            continue

                        # 检查是否为未知词条
                        _, similarity, is_corrected = engine.corrector.correct_entry(entry)
                        if is_corrected:
                            known_count += 1
                        else:
                            has_unknown = True

                    # 只要有至少1条已知词条，就算成功
                    if known_count > 0:
                        print(f"  [成功] 重试后识别到 {known_count} 条已知词条")
                        # 输出重试后的结果
                        if entries:
                            print(f"  重试后识别到 {len(entries)} 条词条:")
                            for idx, (entry, score) in enumerate(zip(entries, scores), 1):
                                print(f"    [{idx}] {entry} (置信度: {score:.2%})")
                        break

                    retry_count += 1

                # 3次重试后仍全部为未知词条，记录并继续
                if has_unknown and known_count == 0:
                    print("\n" + "=" * 50)
                    print("[调试] 全部为未知词条，已记录，继续识别...")
                    print("=" * 50)
                    print("最近的未知词条:")
                    for unknown in unknown_entries[-5:]:  # 显示最后5个
                        print(f"  [{unknown['index']}] {unknown['entry']} (相似度: {unknown['similarity']:.2%})")
                    print("=" * 50 + "\n")

        retry_time = time.time() - retry_start

        # 4. 其他操作时间（按键）
        other_start = time.time()
        if i < LOOP_COUNT - 1:  # 最后一次不需要按键
            pydirectinput.press('right')
            time.sleep(0.2)  # 等待游戏响应
        other_time = time.time() - other_start

        # 5. 单个物品总时间
        total_item_time = time.time() - item_start_time

        # 记录结果
        result = {
            "index": i + 1,
            "times": {
                "capture": capture_time,
                "ocr": ocr_time,
                "correction": correction_time,
                "retry": retry_time,
                "other": other_time,
                "total": total_item_time
            },
            "entries": entries,
            "retry_count": retry_count
        }
        all_results.append(result)

        # 显示结果
        print(f"  截图: {capture_time:.3f}s | OCR: {ocr_time:.3f}s | 纠错: {correction_time:.3f}s | 总计: {total_item_time:.3f}s")
        if retry_count > 0:
            print(f"  重试: {retry_count}次 ({retry_time:.3f}s)")
        for entry in entries:
            print(f"    • {entry}")

    # 计算统计信息
    total_entries = sum(len(r['entries']) for r in all_results)
    stats = calculate_statistics(all_results)

    # 保存结果到文件
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"游戏物品词条OCR识别结果\n")
        f.write(f"{'=' * 70}\n")
        f.write(f"测试时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"识别次数: {len(all_results)}\n")
        f.write(f"总耗时: {stats['totals']['all']:.1f}秒\n")
        f.write(f"平均每个物品: {stats['averages']['total']:.3f}秒\n")
        f.write(f"总词条数: {total_entries}\n")
        f.write(f"\n时间分解:\n")
        f.write(f"  截图时间:   {stats['totals']['capture']:.2f}s ({stats['percentages']['capture']:.1f}%)\n")
        f.write(f"  OCR时间:    {stats['totals']['ocr']:.2f}s ({stats['percentages']['ocr']:.1f}%)\n")
        f.write(f"  纠错时间:   {stats['totals']['correction']:.2f}s ({stats['percentages']['correction']:.1f}%)\n")
        f.write(f"  重试时间:   {stats['totals']['retry']:.2f}s ({stats['percentages']['retry']:.1f}%)\n")
        f.write(f"  其他操作:   {stats['totals']['other']:.2f}s ({stats['percentages']['other']:.1f}%)\n")
        f.write(f"\n重试统计:\n")
        f.write(f"  总重试次数: {stats['retry_stats']['total_retries']}\n")
        f.write(f"  需要重试的物品: {stats['retry_stats']['items_with_retry']}\n")
        f.write(f"{'=' * 70}\n\n")

        # 详细结果
        for result in all_results:
            times = result['times']
            f.write(f"[{result['index']}] 总计: {times['total']:.3f}s ")
            f.write(f"(截图: {times['capture']:.3f}s, OCR: {times['ocr']:.3f}s, ")
            f.write(f"纠错: {times['correction']:.3f}s")
            if result['retry_count'] > 0:
                f.write(f", 重试: {times['retry']:.3f}s x{result['retry_count']}")
            f.write(f")\n")
            for entry in result['entries']:
                f.write(f"  {entry}\n")
            f.write("\n")

        # 汇总所有词条（去重）
        f.write(f"{'=' * 70}\n")
        f.write("所有词条汇总（去重）:\n")
        f.write(f"{'=' * 70}\n")
        unique_entries = set()
        for result in all_results:
            unique_entries.update(result['entries'])
        for entry in sorted(unique_entries):
            f.write(f"  {entry}\n")

    # 控制台输出统计信息
    print("\n" + "=" * 70)
    print("性能统计")
    print("=" * 70)
    print(f"识别次数: {len(all_results)}")
    print(f"总耗时: {stats['totals']['all']:.1f}秒")
    print(f"平均每个物品: {stats['averages']['total']:.3f}秒")
    print(f"\n时间分解:")
    print(f"  截图时间:   {stats['totals']['capture']:.2f}s ({stats['percentages']['capture']:.1f}%)")
    print(f"  OCR时间:    {stats['totals']['ocr']:.2f}s ({stats['percentages']['ocr']:.1f}%)")
    print(f"  纠错时间:   {stats['totals']['correction']:.2f}s ({stats['percentages']['correction']:.1f}%)")
    print(f"  重试时间:   {stats['totals']['retry']:.2f}s ({stats['percentages']['retry']:.1f}%)")
    print(f"  其他操作:   {stats['totals']['other']:.2f}s ({stats['percentages']['other']:.1f}%)")
    print(f"\n平均时间:")
    print(f"  截图: {stats['averages']['capture']:.3f}s")
    print(f"  OCR:  {stats['averages']['ocr']:.3f}s")
    print(f"  纠错: {stats['averages']['correction']:.3f}s")
    print(f"  重试: {stats['averages']['retry']:.3f}s")
    print(f"  其他: {stats['averages']['other']:.3f}s")
    print(f"\n重试统计:")
    print(f"  总重试次数: {stats['retry_stats']['total_retries']}")
    print(f"  需要重试的物品: {stats['retry_stats']['items_with_retry']}")
    print(f"总词条数: {total_entries}")
    print(f"结果已保存到: {OUTPUT_FILE}")

    # ==================== 调试代码开始 ====================
    # 单独保存未知词条
    unknown_file = OUTPUT_FILE.replace('.txt', '_unknown.txt')
    save_unknown_entries(unknown_entries, unknown_file)
    print(f"未知词条已保存到: {unknown_file}")
    print(f"未知词条总数: {len(unknown_entries)}")
    # ==================== 调试代码结束 ====================

    print("=" * 70)


if __name__ == "__main__":
    run_game_test()
