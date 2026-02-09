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
    "similarity_threshold": 0.9,
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

    # 1. 加号标准化：十、＋(全角)、⁺(上标) → +(半角)
    text = text.replace('十', '+').replace('＋', '+')

    # 2. 括号标准化：[](){}  → 【】
    text = text.replace('[', '【').replace(']', '】')
    text = text.replace('(', '【').replace(')', '】')
    text = text.replace('{', '【').replace('}', '】')

    # 3. 删除引号：""
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
            # 使用默认配置初始化CnOcr引擎
            self.engine = CnOcr()
            print("OCR模型加载完成")
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
                    "normal"
                )
                self.corrector = EntryCorrector(
                    vocab_loader.vocabulary,
                    CORRECTION_CONFIG["similarity_threshold"]
                )
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
            print(f"词条库加载完成 (共{len(vocab_loader.vocabulary)}条)")
            return True
        except Exception as e:
            print(f"[错误] 词条库加载失败: {e}")
            return False

    def recognize(self, image: np.ndarray) -> dict:
        """
        执行OCR识别

        Args:
            image: numpy 图像数组

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
            if self.corrector and CORRECTION_CONFIG["enabled"]:
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
