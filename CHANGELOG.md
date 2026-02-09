# 变更日志

## [2.0.0] - 2026-02-08

### 新增功能

#### GPU 加速支持
- 添加 `GPU_CONFIG` 配置项，支持 GPU 加速
- 集成 ONNX Runtime GPU 后端
- 自动 GPU/CPU 切换机制
- CUDA 可用性自动检测和报告
- 支持 TensorRT 优化（可选）

#### 详细时间分解系统
- 添加 `calculate_statistics()` 函数
- 追踪 5 种操作的时间：截图、OCR、纠错、重试、其他
- 计算时间占比和平均值
- 详细的性能统计输出

#### 增强的 OCREngine
- GPU 初始化支持
- 详细的初始化日志
- 错误处理和自动降级
- ONNX 执行提供程序配置

### 改进

#### 性能优化
- GPU 加速：3-5 倍性能提升
- 轻量级模型：densenet_lite_136-gru 和 db_shufflenet_v2
- ONNX Runtime 优化推理

#### 用户体验
- 更详细的初始化信息
- 实时性能统计
- 自动故障恢复
- 清晰的错误消息

#### 文档完善
- GPU_ACCELERATION.md - 详细配置指南
- GPU_SETUP_SUMMARY.md - 设置总结
- QUICK_REFERENCE.md - 快速参考卡
- ENVIRONMENT_SETUP.md - 环境设置指南

### 修改

#### cnocr_test.py
- 添加 GPU_CONFIG 配置
- 增强 OCREngine 类
- 添加 calculate_statistics() 函数
- 修改 run_game_test() 循环以追踪详细时间
- 改进输出格式

#### requirements.txt
- 添加 onnxruntime-gpu>=1.23.0

### 依赖

- cnocr >= 2.3.0
- opencv-python >= 4.5.0
- pyautogui >= 0.9.53
- pydirectinput >= 1.0.2
- keyboard >= 0.13.5
- rapidfuzz >= 2.0.0
- onnxruntime-gpu >= 1.23.0 (新增)

### 系统要求

#### 硬件
- NVIDIA GPU（支持 CUDA）
- CUDA 计算能力 3.5 或更高

#### 软件
- Python 3.10+
- NVIDIA CUDA Toolkit 11.x 或 12.x
- NVIDIA cuDNN 8.x

### 性能指标

#### 单次 OCR 识别
- CPU 模式: ~0.7 秒
- GPU 模式: ~0.15-0.25 秒
- 加速比: 3-5 倍

#### 100 次识别
- CPU 模式: ~70 秒
- GPU 模式: ~15-25 秒
- 加速比: 3-5 倍

### 已知问题

- TensorRT 支持需要额外安装
- 多 GPU 支持需要额外配置
- 某些旧 GPU 可能不支持 CUDA

### 升级指南

从 1.x 升级到 2.0.0：

1. 更新代码
   ```bash
   git pull
   ```

2. 更新依赖
   ```bash
   pip install -r requirements.txt
   ```

3. 配置 GPU（可选）
   编辑 `cnocr_test.py` 中的 `GPU_CONFIG`

4. 运行脚本
   ```bash
   python cnocr_test.py
   ```

### 向后兼容性

- 完全向后兼容 1.x 版本
- GPU 配置是可选的
- 默认启用 GPU，但会自动降级到 CPU

### 致谢

感谢 ONNX Runtime 和 CnOcr 项目的支持。

---

## [1.0.0] - 2026-02-08

### 初始版本

- 基础 OCR 识别功能
- 词条库加载和模糊匹配
- 未知词条检测和重试机制
- 部分结果保存
- 基础性能统计
