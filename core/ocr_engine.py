"""
OCR 引擎封装模块
"""

import time
import re
import os
import cv2
from rapidocr import RapidOCR
from rapidfuzz import fuzz
import numpy as np
from core.utils import get_resource_path, get_user_data_path, log_debug, DEBUG_ENABLED, debug_timer



# ==================== 配置常量 ====================


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
            # 词条库视为静态资源，使用 get_resource_path
            filepath = get_resource_path(os.path.join(self.data_dir, filename))
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
                    log_debug(f"    [动态合并] {entry}")
                    log_debug(f"             + {next_entry}")
                    log_debug(f"             -> {merged_text} (原始: {similarity:.2%}, 合并: {merged_similarity:.2%})")
                    corrected_entries.append(merged_text)
                    skip_next = True
                    continue

        # 输出纠错结果
        if is_corrected:
            pass  # 纠错成功
        else:
            pass  # 保留原文

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
                    log_debug(f"    [动态合并] {entry}")
                    log_debug(f"             + {next_entry}")
                    log_debug(f"             -> {merged_text} (原始: {similarity:.2%}, 合并: {merged_similarity:.2%})")
                    result.append({
                        "text": merged_text,
                        "similarity": merged_similarity,
                        "is_corrected": merged_is_corrected
                    })
                    skip_next = True
                    continue

        # 输出纠错结果
        if is_corrected:
            pass  # 纠错成功
        else:
            pass  # 保留原文

        result.append({
            "text": corrected_text,
            "similarity": similarity,
            "is_corrected": is_corrected
        })

    return result


# ==================== 快速空行检测 ====================

def is_blank_line(image: np.ndarray, variance_threshold: float = 80.0) -> bool:
    """
    用像素方差快速判断图像是否为空行（无文字）

    游戏界面暗底亮字：空行近乎纯色，方差极低；有文字的行方差明显更高。

    Args:
        image: BGR 或灰度图
        variance_threshold: 方差阈值，低于此值视为空行（默认80）

    Returns:
        True: 空行（跳过OCR）
        False: 有内容
    """
    if image is None or image.size == 0:
        return True
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    variance = float(np.var(gray))
    return variance < variance_threshold


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

        log_debug("正在加载OCR模型...")
        try:
            # 优先使用本地打包的模型，实现离线运行
            # 这里的路径对应 PyInstaller 打包时的 --add-data "resources/models;resources/models"
            det_model = get_resource_path("resources/models/ch_PP-OCRv4_det_infer.onnx")
            cls_model = get_resource_path("resources/models/ch_ppocr_mobile_v2.0_cls_infer.onnx")
            rec_model = get_resource_path("resources/models/ch_PP-OCRv4_rec_infer.onnx")
            
            # 使用 config 参数传入本地模型路径
            # RapidOCR(config={...})
            ocr_config = {}
            if os.path.exists(det_model): ocr_config['Det.model_path'] = det_model
            if os.path.exists(cls_model): ocr_config['Cls.model_path'] = cls_model
            if os.path.exists(rec_model): ocr_config['Rec.model_path'] = rec_model
            
            if ocr_config:
                log_debug(f"使用本地模型配置: {ocr_config}")
                self.engine = RapidOCR(params=ocr_config)
            else:
                log_debug("未找到完整本地模型，尝试使用默认配置（可能需要联网下载）")
                self.engine = RapidOCR()

            log_debug("OCR模型加载完成")
        except Exception as e:
            log_debug(f"[错误] OCR模型加载失败: {e}")
            raise

        # 加载词条库
        self.corrector = None
        self.current_mode = None  # 记录当前加载的词条库模式
        self.vocabulary_pos = []  # 深夜模式正面词条库
        self.vocabulary_neg = []  # 深夜模式负面词条库
        if CORRECTION_CONFIG["enabled"]:
            log_debug("正在加载词条库...")
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
                log_debug(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条)")
            except Exception as e:
                log_debug(f"[警告] 词条库加载失败: {e}")
                log_debug("将继续使用OCR结果，不进行纠错")

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

            # 深夜模式：分别保存正面和负面词条库用于分类
            if relic_type == "deepnight":
                self.vocabulary_pos = []
                self.vocabulary_neg = []

                # 加载正面词条库
                pos_filepath = get_resource_path(os.path.join(CORRECTION_CONFIG["data_dir"], "deepnight_pos.txt"))
                if os.path.exists(pos_filepath):
                    with open(pos_filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            if '→' in line:
                                entry = line.split('→', 1)[1].strip()
                            else:
                                entry = line
                            if entry:
                                self.vocabulary_pos.append(entry)

                # 加载负面词条库
                neg_filepath = get_resource_path(os.path.join(CORRECTION_CONFIG["data_dir"], "deepnight_neg.txt"))
                if os.path.exists(neg_filepath):
                    with open(neg_filepath, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            if '→' in line:
                                entry = line.split('→', 1)[1].strip()
                            else:
                                entry = line
                            if entry:
                                self.vocabulary_neg.append(entry)

                log_debug(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条, 正面{len(self.vocabulary_pos)}条, 负面{len(self.vocabulary_neg)}条)")
            else:
                log_debug(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条)")

            return True
        except Exception as e:
            log_debug(f"[错误] 词条库加载失败: {e}")
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
            result = self.engine(image, use_det=False, use_cls=False)
            if not result or not result.txts:
                return {
                    "entries": [],
                    "raw_entries": [],
                    "correction_time": 0.0,
                    "success": False
                }

            # rapidocr v3.x 返回 TextRecOutput，通过 .txts 获取文本列表
            all_text = [t for t in result.txts if t and t.strip()]

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
            log_debug(f"[错误] OCR识别失败: {e}")
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
            if is_blank_line(image):
                return "", 0.0

            result = self.engine(image, use_det=False, use_cls=False)
            if not result or not result.txts:
                return "", 0.0

            # rapidocr v3.x: txts=('text1','text2',...), scores=(0.99,...)
            text = ''.join(result.txts).strip()
            score = result.scores[0] if result.scores else 0.0

            # 清洗单字符"一"（空词条"-"的误识别）
            if text == "一":
                return "", 0.0

            return text, score
        except Exception as e:
            log_debug(f"[错误] 单行OCR识别失败: {e}")
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
            log_debug(f"[词条库切换] {self.current_mode} -> {mode}")
            self.load_vocabulary(mode)

        max_retry = CORRECTION_CONFIG.get("max_retry", 3)

        for retry in range(max_retry):
            start_time = time.time()

            try:
                # 使用单行识别方法
                text, _ = self.recognize_single_line(image)  # 忽略置信度
                if not text:
                    if retry < max_retry - 1:
                        log_debug(f"[重试 {retry + 1}/{max_retry}] OCR未识别到文字，重试中...")
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
                correction_failed_affixes = []
                positive_count = 0
                negative_count = 0

                for info in corrected_info:
                    if info["is_corrected"]:
                        # 纠错成功的词条
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
                    else:
                        # 纠错失败的词条
                        correction_failed_affixes.append({
                            "text": info["text"],
                            "similarity": info["similarity"]
                        })

                recognition_time = (time.time() - start_time) * 1000  # 转换为毫秒

                return {
                    "affixes": affixes,
                    "correction_failed_affixes": correction_failed_affixes,
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "recognition_time": recognition_time,
                    "success": True,
                    "retry_count": retry + 1
                }

            except Exception as e:
                if retry < max_retry - 1:
                    log_debug(f"[重试 {retry + 1}/{max_retry}] OCR识别失败: {e}，重试中...")
                    time.sleep(0.3)
                    continue
                else:
                    log_debug(f"[错误] OCR识别失败: {e}")
                    return self._empty_classification_result()

        return self._empty_classification_result()

    def _empty_classification_result(self) -> dict:
        """返回空的分类结果"""
        return {
            "affixes": [],
            "correction_failed_affixes": [],
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
            log_debug(f"[词条库切换] {self.current_mode} -> {mode}")
            self.load_vocabulary(mode)

        max_retry = CORRECTION_CONFIG.get("max_retry", 3)

        for retry in range(max_retry):
            start_time = time.time()

            try:
                # 对每行进行单行识别
                all_text = []
                line_ocr_start = time.time()
                for line_image in line_images:
                    text, _ = self.recognize_single_line(line_image)
                    if text:
                        all_text.append(text)
                line_ocr_time = (time.time() - line_ocr_start) * 1000

                if not all_text:
                    if retry < max_retry - 1:
                        log_debug(f"[重试 {retry + 1}/{max_retry}] OCR未识别到任何文字，重试中...")
                        time.sleep(0.3)
                        continue
                    return self._empty_classification_result()

                # 拼接所有文本
                combined_text = '\n'.join(all_text)

                # 处理文本（符号标准化、分割词条）
                split_start = time.time()
                raw_entries = split_entries(combined_text)
                split_time = (time.time() - split_start) * 1000

                # 先进行断行合并和纠错，获取详细信息
                correction_start = time.time()
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
                correction_time = (time.time() - correction_start) * 1000

                # 然后对纠错后的词条进行分类
                affixes = []
                correction_failed_affixes = []
                positive_count = 0
                negative_count = 0

                for info in corrected_info:
                    if info["is_corrected"]:
                        # 纠错成功的词条
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
                    else:
                        # 纠错失败的词条
                        correction_failed_affixes.append({
                            "text": info["text"],
                            "similarity": info["similarity"]
                        })

                recognition_time = (time.time() - start_time) * 1000  # 转换为毫秒

                return {
                    "affixes": affixes,
                    "correction_failed_affixes": correction_failed_affixes,
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "recognition_time": recognition_time,
                    "success": True,
                    "retry_count": retry + 1
                }

            except Exception as e:
                if retry < max_retry - 1:
                    log_debug(f"[重试 {retry + 1}/{max_retry}] OCR识别失败: {e}，重试中...")
                    time.sleep(0.3)
                    continue
                else:
                    log_debug(f"[错误] OCR识别失败: {e}")
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
        - 深夜模式：检查词条是否在正面词条库中
          - 如果在 deepnight_pos.txt 中 → 正面
          - 如果在 deepnight_neg.txt 中 → 负面
          - 其他情况 → 正面（默认）

        注意：此方法仅用于已经通过纠错匹配到词条库的词条
        不需要再做模糊匹配，因为纠错时已经确定了词条
        """
        if mode == "normal":
            return True

        # 深夜模式：检查词条是否在正面词条库中
        # 由于纠错时已经匹配到词条库，这里只需要精确匹配
        if hasattr(self, 'vocabulary_pos') and hasattr(self, 'vocabulary_neg'):
            if text in self.vocabulary_pos:
                return True
            if text in self.vocabulary_neg:
                return False

        # 默认为正面
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
            result = self.engine(image, use_det=False, use_cls=False)
            if not result or not result.txts:
                return {
                    "entries": [],
                    "success": False
                }

            # rapidocr v3.x: txts=('text1','text2',...), scores 分开
            text = ''.join(result.txts).strip()
            if text:
                return {
                    "entries": [text],
                    "success": True
                }
            else:
                return {
                    "entries": [],
                    "success": False
                }

        except Exception as e:
            log_debug(f"[错误] OCR识别失败: {e}")
            return {
                "entries": [],
                "success": False
            }

    def ocr(self, image) -> tuple:
        """执行OCR，返回处理后的词条列表和纠错时间"""
        result = self.engine(image, use_det=False, use_cls=False)
        if not result or not result.txts:
            return [], 0.0

        # rapidocr v3.x: txts=('text1','text2',...) 纯字符串 tuple
        all_text = [t for t in result.txts if t and t.strip()]

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
