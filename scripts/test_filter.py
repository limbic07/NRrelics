"""
仓库筛选功能测试脚本
"""

import sys
import time
from core.automation import RepositoryFilter
from core.ocr_engine import OCREngine


def main():
    print("="*60)
    print("仓库筛选功能测试")
    print("="*60)

    # 初始化OCR引擎
    print("\n正在初始化OCR引擎...")
    ocr_engine = OCREngine()

    # 初始化筛选控制器
    print("正在初始化筛选控制器...")
    filter_controller = RepositoryFilter(ocr_engine)

    print(f"\n当前分辨率缩放因子: {filter_controller.scale_factor:.3f}")

    # 提示用户
    print("\n" + "="*60)
    print("请确保：")
    print("1. 游戏已启动并处于遗物仪式界面")
    print("2. 游戏窗口未被遮挡")
    print("="*60)

    # 询问测试模式
    print("\n请选择测试模式：")
    print("1. 普通模式 (normal)")
    print("2. 深夜模式 (deepnight)")
    print("3. 退出")

    choice = input("\n请输入选项 (1/2/3): ").strip()

    if choice == '1':
        mode = 'normal'
    elif choice == '2':
        mode = 'deepnight'
    elif choice == '3':
        print("退出测试")
        return
    else:
        print("无效选项，退出测试")
        return

    # 倒计时
    print(f"\n将在3秒后开始测试 {mode} 模式...")
    for i in range(3, 0, -1):
        print(f"{i}...")
        time.sleep(1)

    # 执行筛选
    success = filter_controller.apply_filter(mode)

    if success:
        print("\n✓ 筛选成功！")
    else:
        print("\n✗ 筛选失败！")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
        sys.exit(0)
    except Exception as e:
        print(f"\n[错误] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
