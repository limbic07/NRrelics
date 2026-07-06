"""
OCR 模型版本对比测试
本地 PP-OCRv4 vs rapidocr 内置 PP-OCRv6-small
"""

import time
import os
import sys
import numpy as np
from rapidocr import RapidOCR

# 确保能找到项目的资源文件
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
RESOURCES_DIR = os.path.join(PROJECT_ROOT, 'resources', 'models')

# 两套模型配置
V4_CONFIG = {
    'Det.model_path': os.path.join(RESOURCES_DIR, 'ch_PP-OCRv4_det_infer.onnx'),
    'Cls.model_path': os.path.join(RESOURCES_DIR, 'ch_ppocr_mobile_v2.0_cls_infer.onnx'),
    'Rec.model_path': os.path.join(RESOURCES_DIR, 'ch_PP-OCRv4_rec_infer.onnx'),
}

# v6 使用默认配置 (不传 params)


def benchmark(engine, name: str, iterations: int = 20) -> dict:
    """对引擎做 N 次推理取平均值"""
    # 创建一张模拟游戏词条区域的测试图 (暗底亮字, 约600x24像素)
    img = np.zeros((24, 600, 3), dtype=np.uint8)
    # 模拟实际使用场景：实际截图来自游戏窗口，尺寸约600x24左右
    # 这里用黑色背景 + 随机噪点模拟

    times = []
    for _ in range(iterations):
        # 每轮生成一张新图避免缓存影响
        test_img = np.random.randint(0, 30, (24, 600, 3), dtype=np.uint8)
        # 在中间位置放一些亮色像素模拟文字
        test_img[5:19, 50:550] = np.random.randint(200, 255, (14, 500, 3), dtype=np.uint8)

        start = time.perf_counter()
        result = engine(test_img, use_det=False, use_cls=False)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        times.append(elapsed)

    avg = sum(times) / len(times)
    return {
        "name": name,
        "avg_ms": round(avg, 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "iterations": iterations,
    }


def main():
    print("=" * 60)
    print("OCR 模型版本对比测试")
    print("=" * 60)

    # --- v4 测试 ---
    print("\n[1/2] 初始化 PP-OCRv4 (本地模型)...")
    t0 = time.perf_counter()
    for k, v in V4_CONFIG.items():
        exists = os.path.exists(v)
        print(f"  {k}: {v}  -> {'存在' if exists else '缺失!'}")
    eng_v4 = RapidOCR(params=V4_CONFIG)
    print(f"  初始化耗时: {(time.perf_counter() - t0) * 1000:.0f}ms")

    result_v4 = benchmark(eng_v4, "PP-OCRv4")
    print(f"  平均推理: {result_v4['avg_ms']}ms (min={result_v4['min_ms']}ms, max={result_v4['max_ms']}ms)")

    # --- v6 测试 ---
    print("\n[2/2] 初始化 PP-OCRv6-small (rapidocr 内置)...")
    t0 = time.perf_counter()
    eng_v6 = RapidOCR()  # 不传 params，使用内置 v6
    print(f"  初始化耗时: {(time.perf_counter() - t0) * 1000:.0f}ms")

    result_v6 = benchmark(eng_v6, "PP-OCRv6-small")
    print(f"  平均推理: {result_v6['avg_ms']}ms (min={result_v6['min_ms']}ms, max={result_v6['max_ms']}ms)")

    # --- 对比 ---
    print("\n" + "=" * 60)
    print("对比结果")
    print("=" * 60)
    speed_diff = result_v6['avg_ms'] - result_v4['avg_ms']
    speed_pct = (speed_diff / result_v4['avg_ms']) * 100
    print(f"  v4 平均: {result_v4['avg_ms']}ms")
    print(f"  v6 平均: {result_v6['avg_ms']}ms")
    print(f"  差异:    {speed_diff:+.2f}ms ({speed_pct:+.1f}%)")
    if result_v6['avg_ms'] > result_v4['avg_ms']:
        print(f"  v6 比 v4 慢约 {speed_pct:.0f}%")
    else:
        print(f"  v6 比 v4 快约 {-speed_pct:.0f}%")
    print()


if __name__ == "__main__":
    main()
