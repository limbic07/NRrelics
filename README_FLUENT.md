# NRrelic Bot v2.0.0 - 简洁 Fluent Design 框架

## 🎉 完成内容

### ✅ UI 框架重建
- 完全使用 **PySide6-Fluent-Widgets**
- **Windows 11 Fluent Design** 风格
- 简洁框架，无细化功能

### ✅ 四大板块
1. **🛍️ 商店筛选** - ShopPage
2. **📦 仓库清理** - RepoPage
3. **💾 存档管理** - SavePage
4. **⚙️ 设置** - SettingsPage

### ✅ 性能优化
- 应用启动 <1秒（UI 立即显示）
- OCR 异步后台初始化
- 不阻塞主线程

## 📁 项目结构

```
NRrelics/
├── main.py                 # 主程序入口
├── run.bat                 # Windows 启动脚本
├── run.sh                  # Linux/Mac 启动脚本
├── requirements.txt        # 依赖列表
├── config/
│   └── settings.json       # 配置文件
├── core/
│   ├── ocr_engine.py       # OCR 引擎
│   ├── automation.py       # 自动化控制
│   └── save_manager.py     # 存档管理
├── ui/
│   ├── main_window.py      # 主窗口（Fluent）
│   └── pages/
│       ├── page_shop.py    # 商店筛选页
│       ├── page_repo.py    # 仓库清理页
│       ├── page_save.py    # 存档管理页
│       └── page_settings.py # 设置页
└── data/                   # 词条库
    ├── normal.txt
    ├── normal_special.txt
    ├── deepnight_pos.txt
    └── deepnight_neg.txt
```

## 🚀 运行方式

### Windows
```bash
# 方式 1：双击运行
run.bat

# 方式 2：命令行
conda activate NRrelic
python main.py
```

### Linux/Mac
```bash
bash run.sh
# 或
conda activate NRrelic
python main.py
```

## 📊 启动流程

```
1. 应用启动 (<1秒)
   ↓
2. 显示主窗口（立即）
   ↓
3. 后台初始化 OCR (5-10秒)
   ↓
4. 控制台显示: ✓ OCR 引擎初始化完成
   ↓
5. 可以使用识别功能
```

## 🎨 界面说明

### 主窗口
- **左侧导航栏**：四个页面切换
- **右侧内容区**：页面内容显示
- **Fluent 风格**：现代化设计

### 页面
每个页面都是简洁框架：
- 页面标题
- 空白内容区域
- 可自由扩展

## 🔧 依赖

```
PySide6>=6.0.0
PySide6-Fluent-Widgets>=0.10.0
cnocr>=2.3.0
opencv-python>=4.5.0
numpy>=1.21.0
rapidfuzz>=2.0.0
pyautogui>=0.9.53
pydirectinput>=1.0.2
keyboard>=0.13.5
```

## 💡 特点

- ⚡ **极速启动**：<1秒显示 UI
- 🎨 **现代设计**：Windows 11 Fluent
- 📦 **简洁框架**：无细化功能
- 🔄 **异步初始化**：不阻塞 UI
- 🎯 **四大板块**：清晰的功能分区

## 📝 后续开发

每个页面都是空白框架，可以自由添加功能：

```python
# 在 page_shop.py 中添加功能
class ShopPage(QWidget):
    def __init__(self):
        super().__init__()
        # ... 添加你的功能
```

## ✨ 快速开始

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **运行应用**
   ```bash
   python main.py
   ```

3. **开发功能**
   - 编辑 `ui/pages/page_*.py`
   - 添加你的功能

---

**版本**: v2.0.0
**框架**: PySide6-Fluent-Widgets
**状态**: ✅ 完成
