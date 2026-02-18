"""
OCR 引擎封装模块
将 cnocr_test.py 的核心 OCR 识别逻辑重构为可供 GUI 调用的类
"""

import time
import re
import os
from cnocr import CnOcr
from rapidfuzz import fuzz
import numpy as np


# ==================== 配置常量 ====================

# 断行合并字典
LINE_BREAK_DICT = {
    "【追踪者】发动技艺时，轻攻击能使出": "【追踪者】发动技艺时，轻攻击能使出缠绕火焰的追加攻击（仅限大剑）",
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
    "enabled": True,
    "similarity_threshold": 0.7,
    "max_retry": 3,
    "data_dir": "data",
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
                continue

            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    if '→' in line:
                        entry = line.split('→', 1)[1].strip()
                    else:
                        entry = line

                    # 不清洗词条，保留原始格式（包括【】等符号）
                    if entry:
                        self.vocabulary.append(entry)

# ==================== 词条纠错器 ====================

class EntryCorrector:
    """词条纠错器，使用模糊匹配修正OCR错误"""
    def __init__(self, vocabulary: list, threshold: float = 0.9):
        self.vocabulary = vocabulary
        self.threshold = threshold

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个字符串的相似度"""
        return fuzz.token_set_ratio(text1, text2) / 100.0

    def correct_entry(self, ocr_text: str) -> tuple:
        """
        纠正单个词条
        返回: (corrected_text, similarity, is_corrected)
        """
        best_match = None
        best_similarity = 0.0

        for vocab_entry in self.vocabulary:
            similarity = self._calculate_similarity(ocr_text, vocab_entry)
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = vocab_entry

        if best_similarity >= self.threshold:
            return (best_match, best_similarity, True)
        else:
            return (ocr_text, best_similarity, False)


# ==================== 文本处理函数 ====================

def postprocess_text(text: str) -> str:
    """OCR文本后处理：符号标准化和清理"""
    # 0. 全角数字 → 半角数字
    text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))

    # 0.5. 罗马数字1 → 阿拉伯数字1（因为图形相似导致的误识别）
    text = text.replace('Ⅰ', '1').replace('ⅰ', '1')

    # 1. 加号标准化：十、＋(全角)、⁺(上标) → +(半角)
    text = text.replace('十', '+').replace('＋', '+')

    # 2. 括号标准化：[](){}  → 【】
    text = text.replace('[', '【').replace(']', '】')
    text = text.replace('(', '【').replace(')', '】')
    text = text.replace('{', '【').replace('}', '】')

    # 3. 删除引号："""
    text = text.replace('"', '')
    text = text.replace('"', '').replace('"', '')

    # 4. 删除所有空格
    text = text.replace(' ', '').replace('　', '')

    # 5. 标点标准化：英文标点 → 中文标点
    text = text.replace(',', '，')
    text = text.replace(':', '：')
    text = text.replace(';', '；')

    # 6. 修正分隔符：数字1中文 → 数字|中文
    text = re.sub(r'(\+\d+)\s*1\s*([\u4e00-\u9fa5])', r'\1|\2', text)

    # 7. 删除包含※符号或"仅限能使用的武器类别"的行
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


def correct_entries_with_info(entries: list, corrector: EntryCorrector) -> list:
    """
    对词条列表进行纠错，支持动态断行合并，返回详细信息

    返回格式：
    [
        {
            "text": str,           # 纠错后的文本
            "similarity": float,   # 相似度
            "is_corrected": bool   # 是否纠正（相似度 >= 0.9）
        },
        ...
    ]
    """
    result = []
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
                merged_text, merged_similarity, merged_is_corrected = corrector.correct_entry(merged_candidate)

                # 决策：仅当合并后相似度更高时才合并
                if merged_similarity > similarity:
                    print(f"    [动态合并] {entry}")
                    print(f"             + {next_entry}")
                    print(f"             -> {merged_text} (原始: {similarity:.2%}, 合并: {merged_similarity:.2%})")
                    result.append({
                        "text": merged_text,
                        "similarity": merged_similarity,
                        "is_corrected": merged_is_corrected
                    })
                    skip_next = True
                    continue

        # 输出纠错结果
        if is_corrected:
            print(f"    [纠正] {entry} -> {corrected_text} (相似度: {similarity:.2%})")
        else:
            print(f"    [保留] {entry} (最高相似度: {similarity:.2%})")

        result.append({
            "text": corrected_text,
            "similarity": similarity,
            "is_corrected": is_corrected
        })

    return result


# ==================== OCR 引擎（单例模式） ====================

class OCREngine:
    """OCR 引擎 - 单例模式"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        print("正在加载OCR模型...")
        try:
            # 使用默认模型
            self.engine = CnOcr(det_model_name='naive_det')
            print("OCR模型加载完成")
        except Exception as e:
            print(f"[错误] OCR模型加载失败: {e}")
            raise

        # 加载词条库
        self.corrector = None
        self.current_mode = None  # 记录当前加载的词条库模式
        if CORRECTION_CONFIG["enabled"]:
            print("正在加载词条库...")
            try:
                vocab_loader = VocabularyLoader(
                    CORRECTION_CONFIG["data_dir"],
                    "normal"
                )
                self.corrector = EntryCorrector(
                    vocab_loader.vocabulary,
                    CORRECTION_CONFIG["similarity_threshold"]
                )
                self.current_mode = "normal"  # 记录当前模式
                print(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条)")
            except Exception as e:
                print(f"[警告] 词条库加载失败: {e}")
                print("将继续使用OCR结果，不进行纠错")

        self._initialized = True

    def load_vocabulary(self, relic_type: str = "normal"):
        """加载词条库"""
        try:
            vocab_loader = VocabularyLoader(
                CORRECTION_CONFIG["data_dir"],
                relic_type
            )
            self.corrector = EntryCorrector(
                vocab_loader.vocabulary,
                CORRECTION_CONFIG["similarity_threshold"]
            )
            self.current_mode = relic_type  # 更新当前模式
            print(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条)")
            return True
        except Exception as e:
            print(f"[错误] 词条库加载失败: {e}")
            return False

    def recognize(self, image: np.ndarray, enable_correction: bool = True) -> dict:
        """
        执行OCR识别

        Args:
            image: numpy 图像数组
            enable_correction: 是否进行纠错（默认True）

        Returns:
            {
                "entries": [词条列表],
                "raw_entries": [原始词条列表],
                "correction_time": 纠错耗时,
                "success": 是否成功
            }
        """
        try:
            result = self.engine.ocr(image)
            if result is None:
                return {
                    "entries": [],
                    "raw_entries": [],
                    "correction_time": 0.0,
                    "success": False
                }

            # 收集所有文本
            all_text = []
            for item in result:
                text = item.get('text', '') if isinstance(item, dict) else item['text']
                if text.strip():
                    all_text.append(text)

            combined_text = '\n'.join(all_text)
            raw_entries = split_entries(combined_text)

            # 纠错
            correction_time = 0.0
            corrected_entries = raw_entries
            if enable_correction and self.corrector and CORRECTION_CONFIG["enabled"]:
                correction_start = time.time()
                corrected_entries = correct_entries(raw_entries, self.corrector)
                correction_time = time.time() - correction_start

            return {
                "entries": corrected_entries,
                "raw_entries": raw_entries,
                "correction_time": correction_time,
                "success": True
            }

        except Exception as e:
            print(f"[错误] OCR识别失败: {e}")
            return {
                "entries": [],
                "raw_entries": [],
                "correction_time": 0.0,
                "success": False
            }

    def recognize_single_line(self, image: np.ndarray) -> tuple:
        """
        执行单行OCR识别（使用ocr_for_single_line）

        Args:
            image: numpy 图像数组

        Returns:
            (text, score) - 识别文本和置信度
        """
        try:
            result = self.engine.ocr_for_single_line(image)
            if result is None:
                return "", 0.0

            text = result.get('text', '')
            score = result.get('score', 0.0)

            # 清洗单字符"一"（空词条"-"的误识别）
            text = text.strip()
            if text == "一":
                return "", 0.0

            return text, score
        except Exception as e:
            print(f"[错误] 单行OCR识别失败: {e}")
            return "", 0.0

    def recognize_with_classification(self, image: np.ndarray, mode: str = "normal") -> dict:
        """
        执行OCR识别并分类词条（正面/负面）
        支持重试机制：如果识别不到任何词条库内的词条，最多重试3次

        Args:
            image: numpy 图像数组
            mode: 模式 ("normal" 或 "deepnight")

        Returns:
            {
                "affixes": [
                    {
                        "text": str,           # 原始文本
                        "cleaned_text": str,   # 清洗后文本
                        "is_positive": bool,   # 是否正面词条
                        "is_unknown": bool,    # 是否未知词条
                        "similarity": float,   # 相似度
                    },
                    ...
                ],
                "positive_count": int,         # 正面词条数量（只计算匹配到词条库的）
                "negative_count": int,         # 负面词条数量（只计算匹配到词条库的）
                "recognition_time": float,     # 识别耗时(ms)
                "success": bool,
                "retry_count": int             # 重试次数
            }
        """
        # 检查是否需要重新加载词条库
        if self.current_mode != mode:
            print(f"[词条库切换] {self.current_mode} -> {mode}")
            self.load_vocabulary(mode)

        max_retry = CORRECTION_CONFIG.get("max_retry", 3)

        for retry in range(max_retry):
            start_time = time.time()

            try:
                # 使用单行识别方法
                text, _ = self.recognize_single_line(image)  # 忽略置信度
                if not text:
                    if retry < max_retry - 1:
                        print(f"[重试 {retry + 1}/{max_retry}] OCR未识别到文字，重试中...")
                        time.sleep(0.3)
                        continue
                    return self._empty_classification_result()

                # 处理文本（符号标准化、分割词条）
                raw_entries = split_entries(text)

                # 先进行断行合并和纠错，获取详细信息
                corrected_info = []
                if self.corrector and CORRECTION_CONFIG["enabled"]:
                    corrected_info = correct_entries_with_info(raw_entries, self.corrector)
                else:
                    # 如果没有纠错器，直接使用原始词条
                    for entry in raw_entries:
                        corrected_info.append({
                            "text": entry,
                            "similarity": 0.0,
                            "is_corrected": False
                        })

                # 然后对纠错后的词条进行分类
                affixes = []
                positive_count = 0
                negative_count = 0

                for info in corrected_info:
                    # 只添加匹配到词条库的词条（is_corrected=True 表示相似度 >= 0.9）
                    if info["is_corrected"]:
                        is_positive = self._is_positive_affix(info["text"], mode)

                        affixes.append({
                            "text": info["text"],
                            "cleaned_text": info["text"],
                            "is_positive": is_positive,
                            "is_unknown": False,
                            "similarity": info["similarity"]
                        })

                        if is_positive:
                            positive_count += 1
                        else:
                            negative_count += 1

                recognition_time = (time.time() - start_time) * 1000  # 转换为毫秒

                # 检查是否识别到任何词条库内的词条
                if len(affixes) == 0:
                    if retry < max_retry - 1:
                        # 区分两种情况：完全没识别到文字 vs 识别到了但都是未知词条
                        if len(raw_entries) == 0:
                            print(f"[重试 {retry + 1}/{max_retry}] OCR未识别到任何文字，重试中...")
                        else:
                            print(f"[重试 {retry + 1}/{max_retry}] 识别到{len(raw_entries)}条文本，但都不匹配词条库（全未知词条），重试中...")
                        time.sleep(0.3)
                        continue
                    else:
                        if len(raw_entries) == 0:
                            print(f"[失败] 重试{max_retry}次后仍未识别到任何文字")
                        else:
                            print(f"[失败] 重试{max_retry}次后仍未识别到任何词条库内的词条（识别到{len(raw_entries)}条未知文本）")
                        return {
                            "affixes": [],
                            "positive_count": 0,
                            "negative_count": 0,
                            "recognition_time": recognition_time,
                            "success": False,
                            "retry_count": retry + 1
                        }

                return {
                    "affixes": affixes,
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "recognition_time": recognition_time,
                    "success": True,
                    "retry_count": retry + 1
                }

            except Exception as e:
                if retry < max_retry - 1:
                    print(f"[重试 {retry + 1}/{max_retry}] OCR识别失败: {e}，重试中...")
                    time.sleep(0.3)
                    continue
                else:
                    print(f"[错误] OCR识别失败: {e}")
                    return self._empty_classification_result()

        return self._empty_classification_result()

    def _empty_classification_result(self) -> dict:
        """返回空的分类结果"""
        return {
            "affixes": [],
            "positive_count": 0,
            "negative_count": 0,
            "recognition_time": 0.0,
            "success": False
        }

    def recognize_with_classification_from_lines(self, line_images: list, mode: str = "normal") -> dict:
        """
        从6行图像执行OCR识别并分类词条（正面/负面）
        支持重试机制：如果识别不到任何词条库内的词条，最多重试3次

        Args:
            line_images: 6个单行图像的列表
            mode: 模式 ("normal" 或 "deepnight")

        Returns:
            与 recognize_with_classification 相同的格式
        """
        # 检查是否需要重新加载词条库
        if self.current_mode != mode:
            print(f"[词条库切换] {self.current_mode} -> {mode}")
            self.load_vocabulary(mode)

        max_retry = CORRECTION_CONFIG.get("max_retry", 3)

        for retry in range(max_retry):
            start_time = time.time()

            try:
                # 对每行进行单行识别
                all_text = []
                for line_image in line_images:
                    text, _ = self.recognize_single_line(line_image)
                    if text:
                        all_text.append(text)

                if not all_text:
                    if retry < max_retry - 1:
                        print(f"[重试 {retry + 1}/{max_retry}] OCR未识别到任何文字，重试中...")
                        time.sleep(0.3)
                        continue
                    return self._empty_classification_result()

                # 拼接所有文本
                combined_text = '\n'.join(all_text)

                # 处理文本（符号标准化、分割词条）
                raw_entries = split_entries(combined_text)

                # 先进行断行合并和纠错，获取详细信息
                corrected_info = []
                if self.corrector and CORRECTION_CONFIG["enabled"]:
                    corrected_info = correct_entries_with_info(raw_entries, self.corrector)
                else:
                    # 如果没有纠错器，直接使用原始词条
                    for entry in raw_entries:
                        corrected_info.append({
                            "text": entry,
                            "similarity": 0.0,
                            "is_corrected": False
                        })

                # 然后对纠错后的词条进行分类
                affixes = []
                positive_count = 0
                negative_count = 0

                for info in corrected_info:
                    # 只添加匹配到词条库的词条（is_corrected=True 表示相似度 >= 0.9）
                    if info["is_corrected"]:
                        is_positive = self._is_positive_affix(info["text"], mode)

                        affixes.append({
                            "text": info["text"],
                            "cleaned_text": info["text"],
                            "is_positive": is_positive,
                            "is_unknown": False,
                            "similarity": info["similarity"]
                        })

                        if is_positive:
                            positive_count += 1
                        else:
                            negative_count += 1

                recognition_time = (time.time() - start_time) * 1000  # 转换为毫秒

                # 检查是否识别到任何词条库内的词条
                if len(affixes) == 0:
                    if retry < max_retry - 1:
                        # 区分两种情况：完全没识别到文字 vs 识别到了但都是未知词条
                        if len(raw_entries) == 0:
                            print(f"[重试 {retry + 1}/{max_retry}] OCR未识别到任何文字，重试中...")
                        else:
                            print(f"[重试 {retry + 1}/{max_retry}] 识别到{len(raw_entries)}条文本，但都不匹配词条库（全未知词条），重试中...")
                        time.sleep(0.3)
                        continue
                    else:
                        if len(raw_entries) == 0:
                            print(f"[失败] 重试{max_retry}次后仍未识别到任何文字")
                        else:
                            print(f"[失败] 重试{max_retry}次后仍未识别到任何词条库内的词条（识别到{len(raw_entries)}条未知文本）")
                        return {
                            "affixes": [],
                            "positive_count": 0,
                            "negative_count": 0,
                            "recognition_time": recognition_time,
                            "success": False,
                            "retry_count": retry + 1
                        }

                return {
                    "affixes": affixes,
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "recognition_time": recognition_time,
                    "success": True,
                    "retry_count": retry + 1
                }

            except Exception as e:
                if retry < max_retry - 1:
                    print(f"[重试 {retry + 1}/{max_retry}] OCR识别失败: {e}，重试中...")
                    time.sleep(0.3)
                    continue
                else:
                    print(f"[错误] OCR识别失败: {e}")
                    return self._empty_classification_result()

        return self._empty_classification_result()

    def _correct_and_classify(self, entry: str, mode: str) -> dict:
        """
        纠错并分类词条（正面/负面）

        Returns:
            {
                "text": str,           # 原始文本
                "cleaned_text": str,   # 清洗后文本（纠错后）
                "is_positive": bool,   # 是否正面词条
                "is_unknown": bool,    # 是否未知词条
                "similarity": float,   # 相似度
            }
        """
        # 纠错
        if self.corrector:
            corrected_text, similarity, is_corrected = self.corrector.correct_entry(entry)
        else:
            corrected_text = entry
            similarity = 0.0
            is_corrected = False

        is_unknown = not is_corrected

        # 判断正面/负面
        is_positive = self._is_positive_affix(corrected_text, mode)

        return {
            "text": entry,
            "cleaned_text": corrected_text,
            "is_positive": is_positive,
            "is_unknown": is_unknown,
            "similarity": similarity
        }

    def _is_positive_affix(self, text: str, mode: str) -> bool:
        """
        判断词条是否为正面词条

        规则：
        - 普通模式：全部为正面
        - 深夜模式：以"降低"、"减少"、"受到损伤"等开头的为负面
        """
        if mode == "normal":
            return True

        # 深夜模式：检查负面关键词
        negative_keywords = [
            "降低", "减少", "受到损伤", "持续减少", "累积",
            "闪避后", "连续闪避", "使用圣杯瓶", "血量没有全满", "濒死"
        ]

        for keyword in negative_keywords:
            if text.startswith(keyword):
                return False

        return True

    def recognize_raw(self, image: np.ndarray) -> dict:
        """
        执行OCR识别（不进行纠错，不进行词条处理）
        用于简单的文字识别场景，如界面验证
        使用单行识别方法以提高准确率

        Args:
            image: numpy 图像数组

        Returns:
            {
                "entries": [识别到的文本列表],
                "success": 是否成功
            }
        """
        try:
            # 使用单行识别方法
            result = self.engine.ocr_for_single_line(image)
            if result is None or not result:
                return {
                    "entries": [],
                    "success": False
                }

            # 提取文本
            text = result.get('text', '') if isinstance(result, dict) else result
            if text and text.strip():
                return {
                    "entries": [text.strip()],
                    "success": True
                }
            else:
                return {
                    "entries": [],
                    "success": False
                }

        except Exception as e:
            print(f"[错误] OCR识别失败: {e}")
            return {
                "entries": [],
                "success": False
            }

    def ocr(self, image) -> tuple:
        """执行OCR，返回处理后的词条列表和纠错时间"""
        result = self.engine.ocr(image)
        if result is None:
            return [], 0.0

        # 第一步：收集所有 items 的文本，拼接成一段完整的长文本
        all_text = []
        for item in result:
            text = item.get('text', '') if isinstance(item, dict) else item['text']
            if text.strip():
                all_text.append(text)

        # 用换行符拼接所有文本
        combined_text = '\n'.join(all_text)

        # 第二步：一次性处理完整的文本（这样 split_entries 才能看到所有行）
        all_raw_entries = split_entries(combined_text)

        # 第三步：对所有行进行纠错
        correction_time = 0.0
        if self.corrector and CORRECTION_CONFIG["enabled"]:
            correction_start = time.time()
            all_raw_entries = correct_entries(all_raw_entries, self.corrector)
            correction_time = time.time() - correction_start

        return all_raw_entries, correction_time
