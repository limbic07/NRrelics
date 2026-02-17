"""
OCR图像预处理测试脚本
用于测试不同预处理方法对OCR识别效果的影响
"""

import cv2
import numpy as np
from cnocr import CnOcr
from pathlib import Path
import time


class ImagePreprocessor:
    """图像预处理器"""

    @staticmethod
    def method_none(image):
        """无预处理"""
        return image

    @staticmethod
    def method_grayscale(image):
        """灰度化"""
        if len(image.shape) == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    @staticmethod
    def method_clahe(image):
        """CLAHE对比度增强"""
        gray = ImagePreprocessor.method_grayscale(image)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

    @staticmethod
    def method_otsu(image):
        """OTSU二值化"""
        gray = ImagePreprocessor.method_grayscale(image)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @staticmethod
    def method_adaptive(image):
        """自适应阈值二值化"""
        gray = ImagePreprocessor.method_grayscale(image)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        return binary

    @staticmethod
    def method_clahe_otsu(image):
        """CLAHE + OTSU"""
        clahe_img = ImagePreprocessor.method_clahe(image)
        _, binary = cv2.threshold(clahe_img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    @staticmethod
    def method_denoise_clahe(image):
        """去噪 + CLAHE"""
        gray = ImagePreprocessor.method_grayscale(image)
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(denoised)

    @staticmethod
    def method_morph(image):
        """形态学处理（去除背景噪声）"""
        gray = ImagePreprocessor.method_grayscale(image)
        # CLAHE增强
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        # OTSU二值化
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # 形态学开运算去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morph = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        return morph

    @staticmethod
    def method_custom(image):
        """自定义方法（针对遗物词条背景优化）"""
        gray = ImagePreprocessor.method_grayscale(image)

        # 1. 高斯模糊去噪
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # 2. CLAHE对比度增强
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)

        # 3. 自适应阈值二值化（更适合背景不均匀的情况）
        binary = cv2.adaptiveThreshold(
            enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 15, 5
        )

        # 4. 形态学闭运算（连接断裂的文字）
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        return closed


class OCRTester:
    """OCR测试器"""

    def __init__(self):
        print("正在加载OCR模型...")
        self.engine = CnOcr(det_model_name='naive_det')
        print("OCR模型加载完成\n")

        self.preprocessor = ImagePreprocessor()

        # 所有预处理方法
        self.methods = {
            "无预处理": self.preprocessor.method_none,
            "灰度化": self.preprocessor.method_grayscale,
            "CLAHE增强": self.preprocessor.method_clahe,
            "OTSU二值化": self.preprocessor.method_otsu,
            "自适应二值化": self.preprocessor.method_adaptive,
            "CLAHE+OTSU": self.preprocessor.method_clahe_otsu,
            "去噪+CLAHE": self.preprocessor.method_denoise_clahe,
            "形态学处理": self.preprocessor.method_morph,
            "自定义优化": self.preprocessor.method_custom,
        }

    def test_image(self, image_path: str, save_preprocessed: bool = True):
        """测试单张图片"""
        print(f"测试图片: {image_path}")
        print("=" * 80)

        # 读取图片
        image = cv2.imread(image_path)
        if image is None:
            print(f"[错误] 无法读取图片: {image_path}")
            return

        print(f"图片尺寸: {image.shape[1]}x{image.shape[0]}\n")

        # 创建输出目录
        output_dir = Path("output/preprocess_test")
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []

        # 测试每种预处理方法
        for method_name, method_func in self.methods.items():
            print(f"[{method_name}]")

            try:
                # 预处理
                start_time = time.time()
                processed = method_func(image)
                preprocess_time = (time.time() - start_time) * 1000

                # 保存预处理后的图片
                if save_preprocessed:
                    output_path = output_dir / f"{Path(image_path).stem}_{method_name}.png"
                    cv2.imwrite(str(output_path), processed)

                # OCR识别
                start_time = time.time()
                ocr_result = self.engine.ocr(processed)
                ocr_time = (time.time() - start_time) * 1000

                # 提取文本
                texts = [item['text'] for item in ocr_result]

                # 统计
                total_time = preprocess_time + ocr_time
                char_count = sum(len(text) for text in texts)

                print(f"  预处理耗时: {preprocess_time:.2f}ms")
                print(f"  OCR耗时: {ocr_time:.2f}ms")
                print(f"  总耗时: {total_time:.2f}ms")
                print(f"  识别到 {len(texts)} 行文本，共 {char_count} 个字符")
                print(f"  识别结果: {texts}")

                results.append({
                    "method": method_name,
                    "texts": texts,
                    "char_count": char_count,
                    "preprocess_time": preprocess_time,
                    "ocr_time": ocr_time,
                    "total_time": total_time
                })

            except Exception as e:
                print(f"  [错误] {e}")
                results.append({
                    "method": method_name,
                    "error": str(e)
                })

            print()

        # 输出对比总结
        print("=" * 80)
        print("对比总结:")
        print("-" * 80)
        print(f"{'方法':<15} {'字符数':<8} {'预处理(ms)':<12} {'OCR(ms)':<10} {'总耗时(ms)':<12}")
        print("-" * 80)

        for result in results:
            if "error" not in result:
                print(f"{result['method']:<15} {result['char_count']:<8} "
                      f"{result['preprocess_time']:<12.2f} {result['ocr_time']:<10.2f} "
                      f"{result['total_time']:<12.2f}")

        print("=" * 80)

        # 推荐最佳方法
        valid_results = [r for r in results if "error" not in r and r['char_count'] > 0]
        if valid_results:
            best_by_chars = max(valid_results, key=lambda x: x['char_count'])
            best_by_speed = min(valid_results, key=lambda x: x['total_time'])

            print(f"\n推荐方法:")
            print(f"  识别字符最多: {best_by_chars['method']} ({best_by_chars['char_count']}字符)")
            print(f"  速度最快: {best_by_speed['method']} ({best_by_speed['total_time']:.2f}ms)")

        if save_preprocessed:
            print(f"\n预处理后的图片已保存到: {output_dir}")


def main():
    """主函数"""
    print("=" * 80)
    print("OCR图像预处理测试脚本")
    print("=" * 80)
    print()

    # 创建测试器
    tester = OCRTester()

    # 测试图片路径（可以修改为你的测试图片）
    test_images = [
        "temp.png",  # 默认测试图片
        # 可以添加更多测试图片
    ]

    for image_path in test_images:
        if Path(image_path).exists():
            tester.test_image(image_path, save_preprocessed=True)
            print("\n")
        else:
            print(f"[警告] 图片不存在: {image_path}\n")

    print("测试完成！")


if __name__ == "__main__":
    main()
