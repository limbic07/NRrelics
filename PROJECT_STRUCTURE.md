# NRrelic Bot v2.0.0 - 项目初始化完成

## 📁 项目结构

```
NRrelics/
├── main.py                    # 程序入口
├── config/
│   ├── settings.json          # 全局配置
│   └── presets/               # 预设文件夹（待扩展）
├── core/                      # 后端核心模块
│   ├── __init__.py
│   ├── ocr_engine.py          # ✅ OCR 引擎（已封装）
│   ├── automation.py          # 键鼠操作控制
│   └── save_manager.py        # 存档管理
├── ui/                        # 前端界面
│   ├── __init__.py
│   ├── main_window.py         # ✅ 主窗口框架
│   ├── pages/                 # 功能页面
│   │   ├── __init__.py
│   │   ├── base_page.py       # 页面基类
│   │   ├── page_shop.py       # 商店筛选页
│   │   ├── page_repo.py       # 仓库清理页
│   │   └── page_save.py       # 存档管理页
│   └── components/            # UI 组件
│       ├── __init__.py
│       └── logger_widget.py   # 日志面板
├── utils/                     # 工具类
│   └── __init__.py
└── data/                      # 词条库（现有）
    ├── normal.txt
    ├── normal_special.txt
    ├── deepnight_pos.txt
    └── deepnight_neg.txt
```

## ✅ Phase 1 完成清单

### 1. 项目骨架搭建
- ✅ 创建完整的目录结构
- ✅ 初始化所有模块的 `__init__.py`
- ✅ 创建配置文件 `config/settings.json`

### 2. 核心引擎封装 (core/ocr_engine.py)
- ✅ 从 `cnocr_test.py` 迁移所有 OCR 逻辑
- ✅ 实现 `OCREngine` 单例模式
- ✅ 保留所有原有功能：
  - `VocabularyLoader` - 词条库加载
  - `EntryCorrector` - 词条纠错
  - `split_entries()` - 词条分割
  - `correct_entries()` - 动态断行合并
  - `postprocess_text()` - 文本后处理
- ✅ 新增 `recognize()` 方法接受图像并返回结构化数据

### 3. UI 骨架 (ui/main_window.py)
- ✅ 现代化主窗口设计
- ✅ 左侧导航栏（深色，固定宽度 200px）
- ✅ 右侧内容区（浅色，使用 QStackedWidget）
- ✅ 极简扁平化风格
- ✅ 页面切换机制

### 4. 功能页面
- ✅ `BasePage` - 页面基类
- ✅ `ShopPage` - 商店筛选页（占位符）
- ✅ `RepoPage` - 仓库清理页（占位符）
- ✅ `SavePage` - 存档管理页（占位符）

### 5. UI 组件
- ✅ `LoggerWidget` - 日志显示面板

### 6. 主程序入口 (main.py)
- ✅ `Application` 类管理应用生命周期
- ✅ 配置加载
- ✅ OCR 引擎初始化
- ✅ UI 初始化和页面注册

## 🚀 运行方式

```bash
# 安装依赖
pip install -r requirements.txt

# 运行应用
python main.py
```

## 📝 核心改动说明

### OCREngine 单例模式
```python
# 使用方式
engine = OCREngine()
engine.load_vocabulary("normal")
result = engine.recognize(image)
# result = {
#     "entries": [纠正后的词条],
#     "raw_entries": [原始词条],
#     "correction_time": 纠错耗时,
#     "success": 是否成功
# }
```

### 保留的原有逻辑
- ✅ `LINE_BREAK_DICT` - 断行字典配置
- ✅ `CORRECTION_CONFIG` - 纠错配置
- ✅ 动态断行合并算法
- ✅ 模糊匹配纠错
- ✅ 文本后处理流程

## 🔄 后续工作 (Phase 2)

1. **商店筛选页面实现**
   - 集成 OCR 引擎
   - 实时识别和筛选
   - 结果展示

2. **仓库清理页面实现**
   - 存档加载和管理
   - 批量处理

3. **存档管理页面实现**
   - 存档导入/导出
   - 版本管理

4. **日志系统完善**
   - 集成到各个页面
   - 实时输出识别过程

5. **配置管理界面**
   - 设置页面
   - 动态配置调整

## 📌 注意事项

- 原有 `cnocr_test.py` 保持不变，用于参考和测试
- 所有核心逻辑已验证且稳定
- UI 采用 PySide6 + 极简扁平化设计
- 配置通过 JSON 文件管理
- 支持多种遗物类型（normal/deepnight）

---

**项目状态**: Phase 1 完成 ✅
**下一步**: Phase 2 - 功能页面实现
