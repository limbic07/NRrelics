# 存档遗物校验规则

存档管理页的“违规遗物检测”读取 `.sl2` / `.co2` 存档，逐件检查遗物 ID 和六个词条 ID（最多三个正面、三个负面）。这是只读规则检查，不是游戏官方认证，也不能判断遗物是否经过 CE 修改或是否有封禁风险。它不参与商店筛选和仓库清理；那两个功能仍按画面 OCR 与用户预设判断。

## 数据来源

- `data/relic_validation/EquipParamAntique.csv`：遗物 ID、颜色、三个正面词条池和三个负面词条池。
- `data/relic_validation/AttachEffectParam.csv`：词条冲突组 `compatibilityId` 和排序值 `overrideEffectId`。
- `data/relic_validation/AttachEffectTableParam.csv`：生成池中的词条与权重。DLC 权重为 `-1` 时沿用基础权重。
- `data/relic_validation/AttachEffectName*.fmg.xml`：界面展示的中文词条名称，不参与合法性判断。

上述表格来自社区项目 [Elden-Ring-Nightreign-Save-Editor](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/tree/0d2ad1494c372098e689c23159656df70ff2d76d)，固定于提交 `0d2ad1494c372098e689c23159656df70ff2d76d`；许可见 `data/relic_validation/LICENSE-MIT.txt`。本项目的只读解析和判定实现位于 `core/relic_validation.py`，参考了该项目的 [存档结构](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/inventory_handler.py)、[遗物判定](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/relic_checker.py)和 [ID 分组](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/globals.py)。

## 当前判定

| 检查 | 当前规则 | 结果 |
| --- | --- | --- |
| 读取存档 | 只接受受支持的 PC BND4 结构，读取十个玩家槽位；结构损坏或版本不兼容 | 无法判定整个存档 |
| 遗物 ID | `20000–30035` 为已知非法区间；其他 ID 需在当前已知范围及表格内 | 非法区间为明确违规；不认识的 ID 为无法判定 |
| 正面词条池 | 按遗物的三个槽位尝试六种词条顺序；非空词条需位于表中有效权重非零的生成池，`-1` 槽位应为空 | 所有顺序均不匹配时明确违规 |
| 深夜正面词条 | 先按深夜 A/B/C 合并池检查，再检查是否匹配该遗物指定的 A/B/C 池 | 只匹配合并池时无法判定，不能直接认定违规 |
| 负面词条 | 检查已配置的负面词条池，以及需附带负面词条的深夜正面效果 | 明确不匹配时违规；`-1` 槽位出现全局负面词条池中的效果时无法判定 |
| 词条冲突与顺序 | 非 `-1` 的 `compatibilityId` 不应重复；正面词条按 `overrideEffectId`、词条 ID 升序 | 明确违反时违规 |
| 唯一遗物 | 同一玩家槽位内，已知唯一 ID 区间 `1000–2100`、`10000–19999` 不应重复 | 重复时违规；不同玩家槽位分别计算 |

每件遗物采用“明确违规 / 无法判定 / 符合已知规则”三级结果。整个存档只要含有明确违规就显示违规；否则有无法判定就显示无法判定。界面列出前两类遗物的 ID、词条和具体原因。

## 已知边界

当前参数快照中，部分深夜遗物的额外负面词条槽位是 `-1`，实际存档却可能有全局负面词条。快照不足以解释这些组合的生成方式，故列为“无法判定”。“符合已知规则”只表示本次检查未发现矛盾，不能证明取得途径、服务器状态或存档来源。

参数是固定快照。游戏更新后出现的新遗物、新词条或新生成规则可能需要重新提取和核对参数；未知版本不应被旧规则直接判为违规。
