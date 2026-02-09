import cv2
import numpy as np
import pyautogui

# 全局变量
ref_point = []
cropping = False

def shape_selection(event, x, y, flags, param):
    global ref_point, cropping
    
    # 鼠标按下，记录起始点
    if event == cv2.EVENT_LBUTTONDOWN:
        ref_point = [(x, y)]
        cropping = True

    # 鼠标松开，记录结束点
    elif event == cv2.EVENT_LBUTTONUP:
        ref_point.append((x, y))
        cropping = False
        # 画出矩形
        cv2.rectangle(image, ref_point[0], ref_point[1], (0, 255, 0), 2)
        cv2.imshow("Select ROI", image)

print(">>> 3秒后截屏...")
cv2.waitKey(3000)

# 1. 截屏
screenshot = pyautogui.screenshot()
image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
clone = image.copy()
h, w = image.shape[:2]

cv2.namedWindow("Select ROI")
cv2.setMouseCallback("Select ROI", shape_selection)

print(f">>> 屏幕分辨率: {w}x{h}")
print(">>> 请用鼠标框选你的背包区域（光标可能出现的范围）")
print(">>> 选好后按 'c' 确认并计算比例，按 'r' 重选")

while True:
    cv2.imshow("Select ROI", image)
    key = cv2.waitKey(1) & 0xFF

    # 重置
    if key == ord("r"):
        image = clone.copy()
        ref_point = []

    # 确认
    elif key == ord("c"):
        break

cv2.destroyAllWindows()

if len(ref_point) == 2:
    x1, y1 = ref_point[0]
    x2, y2 = ref_point[1]
    
    # 处理从右下往左上画的情况
    roi_x = min(x1, x2)
    roi_y = min(y1, y2)
    roi_w = abs(x1 - x2)
    roi_h = abs(y1 - y2)
    
    print("\n" + "="*50)
    print(">>> 【请复制以下配置到主程序 Config 类中】 <<<")
    print("# ROI 区域配置 (比例值，自适应不同分辨率)")
    print(f"ROI_START_X_RATIO = {roi_x / w:.4f}  # {roi_x}/{w}")
    print(f"ROI_START_Y_RATIO = {roi_y / h:.4f}  # {roi_y}/{h}")
    print(f"ROI_WIDTH_RATIO = {roi_w / w:.4f}   # {roi_w}/{w}")
    print(f"ROI_HEIGHT_RATIO = {roi_h / h:.4f}  # {roi_h}/{h}")
    print("="*50)