"""
仓库清理功能测试脚本
用于验证核心模块的功能
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.preset_manager import PresetManager, PRESET_TYPE_NORMAL_WHITELIST, PRESET_TYPE_DEEPNIGHT_WHITELIST


def test_preset_manager():
    """测试预设管理器"""
    print("=" * 60)
    print("测试预设管理器")
    print("=" * 60)

    # 初始化
    manager = PresetManager()

    # 测试加载词条库
    print("\n1. 测试加载词条库")
    normal_vocab = manager.load_vocabulary(PRESET_TYPE_NORMAL_WHITELIST)
    print(f"   普通模式词条库: {len(normal_vocab)}条")
    if normal_vocab:
        print(f"   示例词条: {normal_vocab[:3]}")

    deepnight_vocab = manager.load_vocabulary(PRESET_TYPE_DEEPNIGHT_WHITELIST)
    print(f"   深夜模式词条库: {len(deepnight_vocab)}条")
    if deepnight_vocab:
        print(f"   示例词条: {deepnight_vocab[:3]}")

    # 测试通用预设
    print("\n2. 测试通用预设")
    general_preset = manager.get_general_preset("normal")
    print(f"   普通通用预设: {general_preset['name']}")
    print(f"   词条数量: {len(general_preset['affixes'])}")

    # 更新通用预设
    if normal_vocab:
        test_affixes = normal_vocab[:5]
        manager.update_general_preset("normal", test_affixes)
        print(f"   更新通用预设: 添加了{len(test_affixes)}条词条")

        # 验证更新
        updated_preset = manager.get_general_preset("normal")
        print(f"   验证更新: {len(updated_preset['affixes'])}条词条")

    # 测试专用预设
    print("\n3. 测试专用预设")
    try:
        if normal_vocab:
            preset_id = manager.create_dedicated_preset(
                "normal",
                "测试专用预设1",
                normal_vocab[5:10]
            )
            print(f"   创建专用预设成功: {preset_id}")

            # 获取专用预设列表
            dedicated_presets = manager.get_dedicated_presets("normal")
            print(f"   专用预设数量: {len(dedicated_presets)}")

            # 获取激活的专用预设
            active_presets = manager.get_active_dedicated_presets("normal")
            print(f"   激活的专用预设: {len(active_presets)}")

            # 测试切换激活状态
            manager.toggle_preset_active("normal", preset_id)
            print(f"   切换预设激活状态")

            active_presets = manager.get_active_dedicated_presets("normal")
            print(f"   激活的专用预设: {len(active_presets)}")

            # 删除测试预设
            manager.delete_dedicated_preset("normal", preset_id)
            print(f"   删除测试预设")

    except Exception as e:
        print(f"   错误: {e}")

    print("\n✓ 预设管理器测试完成")


def test_ocr_engine():
    """测试OCR引擎"""
    print("\n" + "=" * 60)
    print("测试OCR引擎")
    print("=" * 60)

    try:
        from core.ocr_engine import OCREngine
        import numpy as np

        print("\n1. 初始化OCR引擎")
        engine = OCREngine()
        print("   ✓ OCR引擎初始化成功")

        # 测试词条库加载
        print("\n2. 测试词条库加载")
        success = engine.load_vocabulary("normal")
        if success:
            print("   ✓ 普通模式词条库加载成功")
        else:
            print("   ✗ 普通模式词条库加载失败")

        # 测试正面/负面判断
        print("\n3. 测试正面/负面词条判断")
        test_cases = [
            ("提升攻击力", "normal", True),
            ("降低生命力", "deepnight", False),
            ("提升攻击力", "deepnight", True),
            ("受到损伤时会累积中毒量表", "deepnight", False),
        ]

        for text, mode, expected in test_cases:
            result = engine._is_positive_affix(text, mode)
            status = "✓" if result == expected else "✗"
            print(f"   {status} {text} ({mode}): {result} (期望: {expected})")

        print("\n✓ OCR引擎测试完成")

    except Exception as e:
        print(f"\n✗ OCR引擎测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_relic_detector():
    """测试遗物检测器"""
    print("\n" + "=" * 60)
    print("测试遗物检测器")
    print("=" * 60)

    try:
        from core.relic_detector import (RelicDetector, RELIC_STATE_LIGHT,
                                        RELIC_STATE_DARK_F, RELIC_STATE_DARK_FE)

        print("\n1. 初始化遗物检测器")
        detector = RelicDetector()
        print("   ✓ 遗物检测器初始化成功")

        print("\n2. 状态常量")
        print(f"   Light: {RELIC_STATE_LIGHT}")
        print(f"   Dark-F: {RELIC_STATE_DARK_F}")
        print(f"   Dark-FE: {RELIC_STATE_DARK_FE}")

        print("\n✓ 遗物检测器测试完成")

    except Exception as e:
        print(f"\n✗ 遗物检测器测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_repo_cleaner():
    """测试清理控制器"""
    print("\n" + "=" * 60)
    print("测试清理控制器")
    print("=" * 60)

    try:
        from core.repo_cleaner import RepoCleaner
        from core.preset_manager import PresetManager
        from core.ocr_engine import OCREngine
        from core.relic_detector import RelicDetector

        print("\n1. 初始化组件")
        preset_manager = PresetManager()
        ocr_engine = OCREngine()
        relic_detector = RelicDetector()
        print("   ✓ 所有组件初始化成功")

        print("\n2. 创建清理控制器")
        cleaner = RepoCleaner(preset_manager, ocr_engine, relic_detector)
        print("   ✓ 清理控制器创建成功")

        print("\n3. 测试跳过决策逻辑")
        test_cases = [
            ("Light", "sell", False, False),
            ("F", "sell", False, True),
            ("F", "sell", True, False),
            ("Light", "favorite", False, False),
            ("F", "favorite", False, True),
        ]

        for state, mode, allow_fav, expected in test_cases:
            result = cleaner._should_skip_relic(state, mode, allow_fav)
            status = "✓" if result == expected else "✗"
            print(f"   {status} 状态:{state}, 模式:{mode}, 允许收藏:{allow_fav} -> 跳过:{result} (期望:{expected})")

        print("\n✓ 清理控制器测试完成")

    except Exception as e:
        print(f"\n✗ 清理控制器测试失败: {e}")
        import traceback
        traceback.print_exc()


def test_settings():
    """测试设置功能"""
    print("\n" + "=" * 60)
    print("测试设置功能")
    print("=" * 60)

    try:
        import json
        import os

        settings_file = "data/settings.json"

        print("\n1. 测试默认设置")
        default_settings = {
            "game_window_title": "ELDEN RING™",
            "allow_operate_favorited": False,
            "require_double_valid": True
        }
        print(f"   默认设置: {default_settings}")

        print("\n2. 测试设置保存")
        os.makedirs("data", exist_ok=True)
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(default_settings, f, ensure_ascii=False, indent=2)
        print("   ✓ 设置保存成功")

        print("\n3. 测试设置加载")
        with open(settings_file, 'r', encoding='utf-8') as f:
            loaded_settings = json.load(f)
        print(f"   加载的设置: {loaded_settings}")

        if loaded_settings == default_settings:
            print("   ✓ 设置加载验证成功")
        else:
            print("   ✗ 设置加载验证失败")

        print("\n✓ 设置功能测试完成")

    except Exception as e:
        print(f"\n✗ 设置功能测试失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """主测试函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "仓库清理功能测试" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")

    try:
        # 测试各个模块
        test_preset_manager()
        test_ocr_engine()
        test_relic_detector()
        test_repo_cleaner()
        test_settings()

        # 总结
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        print("✓ 所有核心模块测试完成")
        print("\n建议:")
        print("1. 检查 data/presets.json 文件是否正确生成")
        print("2. 检查 data/settings.json 文件是否正确生成")
        print("3. 确认词条库文件存在: data/normal.txt, data/deepnight_pos.txt 等")
        print("4. 准备图标文件: icon_cup.png, icon_bookmark.png")
        print("\n下一步: 实现UI界面 (page_repo.py)")

    except Exception as e:
        print(f"\n✗ 测试过程出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
