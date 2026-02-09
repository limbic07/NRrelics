# NRrelic Bot v2.0.0 - 项目更新说明

## 🎨 UI 设计更新

### 采用 Windows 11 Fluent Design
- ✅ 使用 `PySide6-Fluent-Widgets` 库
- ✅ 现代化的 Fluent 风格界面
- ✅ 流畅的交互体验

### 主要改进

#### 1. **主窗口 (MainWindow)**
- 窗口大小优化：1200x750（从 1600x900 缩小）
- 最小窗口大小：1000x600
- Fluent 导航栏设计
- 自动适应内容

#### 2. **仓库清理页面 (RepoPage)**
- ✨ **新增 RelicCard 组件**：遗物卡片展示
- 网格布局（FlowLayout）自动换行
- 卡片包含：
  - 遗物名称
  - 品质标签（颜色编码）
  - 数量显示
  - 删除按钮
- 可滚动的卡片网格

#### 3. **RelicCard 组件**
```python
RelicCard(name="追踪者的秘密", quality="史诗", count=1)
```
- 固定大小：200x240px
- 品质颜色编码：
  - 普通：灰色 (#666666)
  - 稀有：蓝色 (#0066cc)
  - 史诗：紫色 (#9933ff)
  - 传说：橙色 (#ff9900)

#### 4. **其他页面**
- 商店筛选页：OCR 识别界面
- 存档管理页：存档列表管理
- 所有页面采用统一的 Fluent 设计

## ⚡ 性能优化

### 应用启动速度优化

#### 问题
- 原来应用启动时需要初始化 OCR 引擎
- OCR 模型加载耗时较长（5-10秒）
- 用户需要等待才能看到界面

#### 解决方案
- ✅ **异步初始化 OCR 引擎**
- 应用启动时立即显示 UI（<1秒）
- OCR 引擎在后台线程中初始化
- 初始化完成后自动可用

#### 实现细节
```python
# 后台线程初始化
class OCRInitializer(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def initialize(self):
        # 在后台线程中初始化 OCR
        self.ocr_engine = OCREngine()
        self.finished.emit()

# 主线程连接信号
self.ocr_initializer.finished.connect(self._on_ocr_initialized)
```

### 启动流程
1. 应用启动 (<1秒)
2. 显示主窗口和页面
3. 后台初始化 OCR 引擎 (5-10秒)
4. 初始化完成后可以使用识别功能

## 📦 依赖更新

### 新增依赖
```
PySide6-Fluent-Widgets>=0.10.0
```

### 完整依赖列表
```
# OCR 和图像处理
cnocr>=2.3.0
opencv-python>=4.5.0
numpy>=1.21.0

# GUI 框架
PySide6>=6.0.0
PySide6-Fluent-Widgets>=0.10.0

# 自动化和输入
pyautogui>=0.9.53
pydirectinput>=1.0.2
keyboard>=0.13.5

# 文本处理
rapidfuzz>=2.0.0
```

## 🚀 运行方式

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行应用
```bash
python main.py
# 或
python run.py
```

## 📁 项目结构

```
NRrelics/
├── main.py                    # 主程序入口（优化启动速度）
├── run.py                     # 快速启动脚本
├── requirements.txt           # 依赖列表
├── config/
│   └── settings.json          # 全局配置
├── core/
│   ├── ocr_engine.py          # OCR 引擎（单例模式）
│   ├── automation.py          # 键鼠操作
│   └── save_manager.py        # 存档管理
├── ui/
│   ├── main_window.py         # 主窗口（Fluent Design）
│   ├── pages/
│   │   ├── page_shop.py       # 商店筛选页
│   │   ├── page_repo.py       # 仓库清理页（网格布局）
│   │   └── page_save.py       # 存档管理页
│   └── components/
│       ├── logger_widget.py   # 日志组件
│       └── relic_card.py      # 遗物卡片组件（新增）
└── data/
    ├── normal.txt
    ├── normal_special.txt
    ├── deepnight_pos.txt
    └── deepnight_neg.txt
```

## 🎯 主要特性

### 1. 快速启动
- 应用立即显示，无需等待 OCR 初始化
- 后台异步加载 OCR 引擎

### 2. 现代化 UI
- Windows 11 Fluent Design 风格
- 响应式布局
- 流畅的交互

### 3. 遗物卡片展示
- 网格布局自动换行
- 品质颜色编码
- 可滚动查看

### 4. 优化的窗口大小
- 默认：1200x750
- 最小：1000x600
- 适应不同屏幕

## 🔧 技术栈

- **GUI 框架**：PySide6 + PySide6-Fluent-Widgets
- **OCR 引擎**：CnOcr
- **图像处理**：OpenCV
- **文本匹配**：RapidFuzz
- **自动化**：PyAutoGUI + PyDirectInput

## 📝 后续计划

- [ ] 实现商店筛选功能
- [ ] 实现仓库清理功能
- [ ] 实现存档管理功能
- [ ] 添加设置页面
- [ ] 优化 OCR 识别准确率
- [ ] 添加更多遗物类型支持

## 🐛 已知问题

- 无

## 💡 使用建议

1. 首次运行时，应用会在后台初始化 OCR 引擎
2. 初始化完成后（控制台会显示 "✓ OCR 引擎初始化完成"），可以使用识别功能
3. 如果 OCR 初始化失败，控制台会显示错误信息

---

**版本**：v2.0.0
**更新日期**：2026-02-09
**作者**：NRrelic Bot Team
