# OCR 自动采集与校对

采集代码接在仓库清理和商店购买的实际六行 OCR 流程中。开启后，程序每处理一件进入 OCR 的遗物，就在决定收藏、保留或售出之前保存当次截图、识别、纠错和预设匹配结果。OCR 失败也会保存。仓库中按遗物状态直接跳过、未进入 OCR 的项目没有词条样本。采集只写文件，不改变现有匹配规则或游戏操作。

## 开启

任选一种方式：

1. 直接进入“设置 → 开发者设置”，开启 **OCR 调试模式**。设置保存后，后续运行继续生效。
2. 在启动程序的同一个 PowerShell 窗口设置环境变量，本次启动生效：

```powershell
$env:NRRELIC_OCR_DIAGNOSTICS = '1'
& 'E:\DevTools\NRrelics-venv\Scripts\python.exe' main.py
```

之后照常启动仓库清理或商店购买，无需逐件按键采集。每次启动一个自动流程，会在应用目录的 `debug_ocr/collections/` 下创建独立会话目录；程序日志会显示完整路径。若要将大量截图存到其他磁盘，可在启动前设置 `$env:NRRELIC_OCR_DEBUG_DIR = 'E:\OCR-data'`。关闭开关并清除环境变量即可停止采集。

## 每次会话的文件

| 文件 | 内容 |
| --- | --- |
| `samples/<编号>/screen.png` | 仓库清理时状态检测、导航判断和六行 OCR 共用的完整游戏客户区截图。 |
| `samples/<编号>/after_f.png`、`after_f.json` | 按 F 后补拍仍无法确认下一件可安全识别时，保存最终检查画面和详情、待售出金额、遗物图标、预计格子的证据；正常移动时不写文件。 |
| `navigation/ambiguous_<编号>.png`、`.json` | 按右键后仍无法确认进入下一件时的画面、预计格子和各项证据。 |
| `samples/<编号>/line_1.png` 至 `line_6.png` | 实际送入 OCR 的六行截图。游戏只有两行文字时，其余截图仍保留以便检查。 |
| `samples/<编号>/sample.json`、`samples.jsonl` | 每次 OCR 尝试的逐行原文与分数、拼接与拆分、纠错轨迹、最终识别结果、预设匹配结果和上下文。 |
| `lines_review.csv` | 六行截图及每行原始 OCR。 |
| `raw_entries_review.csv` | 拆分或修复后的原始词条、词条库精确命中情况及最接近的三个候选。 |
| `entries_review.csv` | 每条纠错输出、来源原文编号、相似度、精确命中及最近候选。 |
| `correction_calls.csv` | 每次实际纠错调用的输入、返回值、相似度、动态阈值、是否接受、最近词条库候选及 OCR 重试编号。 |
| `manifest.json` | 工作模式、来源和词条库文件的 SHA256。 |

`entries_review.csv` 的 `source_entry_numbers` 对应 `raw_entries_review.csv` 的词条编号。合并两段原文时会列出两个编号，`raw_entry` 也会保留两段内容。`sample.json` 中有更完整的 OCR 尝试和预设匹配详情。

CSV 中的 `game_text`、`review_note` 留给后续对照截图填写。词条库候选和 `visually_blank` 只是程序估计，不能代替画面真实文字。几百件遗物可先全自动采集，再集中筛选和抽样校对。截图可能包含玩家名称、货币等画面信息；默认 `debug_ocr/` 已被 Git 忽略，处理大量遗物时需留意磁盘空间。

自动采集代码集中在 `core/ocr_diagnostics.py`；调用点均用 `OCR 自动采集调试代码` 注释标记，便于以后定位和删除。

仓库清理正常处理每件遗物只截一次全屏。导航时先按仓库格子从上到下、同一行从左到右识别真实光标，再核对它是否到了预计下一格。详情文字和大图标用于判断面板是否刷新；光标或详情不明确时立即补拍一帧，不重按 F 或右键，也没有固定等待。仍无法确认时停止，待售出遗物不会自动确认。
