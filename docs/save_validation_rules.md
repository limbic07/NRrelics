# 存档遗物校验规则

存档管理页的“遗物规则检查”读取 `.sl2` / `.co2` 存档。符合已知词条组合生成规则即显示为“合法遗物”。ID 一致性是独立结果，不影响合法性统计。检查只读，不参与商店筛选和仓库清理。

## 检查模式

设置页“遗物规则检查”中的“检查 ID 一致性”默认关闭，保存字段为 `check_relic_id_consistency`。每次开始验证时读取设置并固定本次模式；切换后下次验证生效，结果页显示本次使用的模式。

- **关闭（默认）：** 随机遗物按相同颜色、普通／深夜类型、大小（正面槽位数）寻找完整生成模板。任一完整模板精确匹配全部正负词条，即视为合法，不要求匹配存档中的具体 ID。正负配对、词条冲突、排列和大小限制仍检查。不会合并不同模板的词条池来放行组合。
- **开启：** 额外检查存档中具体 ID 所规定的正负词条数量和生成模板与实际词条是否对应。组合合法但 ID 不匹配的遗物显示“合法，但 ID 一致性不通过”，仍计入合法数量；ID 检查数据不足则单独显示“ID 一致性无法判定”。关闭时不产生 ID 检查结果。
- 固定／特殊遗物不参与随机模板互换，仍核对本身的固定组合。未知 ID、数据不足继续显示“无法判定”；已知非法 ID 范围和同角色唯一遗物重复检查保留。

ID 指存档当前记录的遗物模板编号，无法据此还原最初获得时的历史编号。“合法”在本功能中仅指符合当前检查规则。

## 数据来源

- `data/relic_validation/EquipParamAntique.csv`：遗物 ID、颜色、三个正面词条池和三个负面词条池。
- `data/relic_validation/AttachEffectParam.csv`：词条冲突组 `compatibilityId` 和排序值 `overrideEffectId`。
- `data/relic_validation/AttachEffectTableParam.csv`：生成池中的词条与权重。DLC 权重为 `-1` 时沿用基础权重。
- `data/relic_validation/AttachEffectName*.fmg.xml`：界面展示的中文词条名称，不参与合法性判断。

上述表格来自社区项目 [Elden-Ring-Nightreign-Save-Editor](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/tree/0d2ad1494c372098e689c23159656df70ff2d76d)，固定于提交 `0d2ad1494c372098e689c23159656df70ff2d76d`；许可见 `data/relic_validation/LICENSE-MIT.txt`。本项目的只读解析和判定实现位于 `core/relic_validation.py`，参考了该项目的 [存档结构](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/inventory_handler.py)、[遗物判定](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/relic_checker.py)和 [ID 分组](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/globals.py)。

## 基础检查与 ID 一致性开启时的判定

| 检查 | 当前规则 | 结果 |
| --- | --- | --- |
| 读取存档 | 只接受受支持的 PC BND4 结构，读取十个玩家槽位；结构损坏或版本不兼容 | 无法判定整个存档 |
| 遗物 ID | `20000–30035` 为已知非法区间；其他 ID 需在当前已知范围及表格内 | 非法区间为明确违规；不认识的 ID 为无法判定 |
| 正负词条数量 | 分别按 ID 模板统计已配置槽位；正面和负面实际数量均须相等，`-1` 表示不存在该槽位 | 多出或缺少均违反已知规则；显示应有数量和实际数量。一、二词条遗物按各自模板判断 |
| 正面词条池 | 按遗物的三个槽位尝试六种词条顺序；非空词条需位于表中有效权重非零的生成池，`-1` 槽位应为空 | 所有顺序均不匹配时明确违规 |
| 深夜正面词条 | 先按深夜 A/B/C 合并池检查，再检查指定 A/B/C 池；正面与对应负面必须使用同一种排列完成匹配 | 只匹配合并池时无法判定，不能直接认定违规 |
| 负面词条关联 | 必须附带负面效果的正面词条，其对应位置必须有负面词条；负面词条不能依附空正面位置 | 无论模板是否提供负面槽位，均独立检查；缺失、错位或无对应正面时违规 |
| 负面词条池 | 所有实际负面词条必须匹配模板指定的负面池；已配置的槽位不能当成可选项 | 不匹配时违规，不能因词条存在于全局负面池就放行 |
| 词条冲突与顺序 | 非 `-1` 的 `compatibilityId` 不应重复；正面词条按 `overrideEffectId`、词条 ID 升序 | 明确违反时违规 |
| 唯一遗物 | 同一玩家槽位内，已知唯一 ID 区间 `1000–2100`、`10000–19999` 不应重复 | 重复时违规；不同玩家槽位分别计算 |

组合合法性采用“不合法 / 无法判定 / 合法”三级结果。未知词条不会掩盖已经能够确认的组合规则矛盾。整个存档的合法性仅汇总组合结果。界面列出组合不合法、组合无法判定，以及 ID 一致性不通过或无法判定的遗物，分别展示原因。开关无论开关，随机遗物的组合合法性均按上文的完整组合匹配判断。

## 2026-10-05 资料核实与修正

本次通过 GitHub 查询确认，数据来源仓库当前提交仍为 `0d2ad1494c372098e689c23159656df70ff2d76d`；本地三份 CSV 与该提交的数据在统一换行后逐字一致。这次修正规则实现，不替换参数表。

1. **ID 与负面数量必须匹配。** 上游维护者在 [#115 的回复](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/issues/115#issuecomment-4038811653)中明确指出，ID `2003322` 没有负面槽位；在 [#129 的回复](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/issues/129#issuecomment-4181043087)中再次说明，界面看起来正常的组合也可能与 Item ID 的负面数量不符。[#55 的具体案例](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/issues/55#issuecomment-3707857057)使用了 `2003202`，与本地出现的情况相同。因此撤销此前将额外负面槽位 `-1` 解释成“资料缺失”的处理。
2. **必须附带负面效果要独立检查。** [上游校验实现](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/blob/0d2ad1494c372098e689c23159656df70ff2d76d/src/relic_checker.py)检查必须附带负面效果及数量。[Reliquary 的独立数据](https://github.com/ParaphrazeTutorials/nightreign-data-tools/blob/dafcb2de9837b58cef64960b672d21e3841b0abe/Data/reliquary.json)有 497 项，其 49 项 `CurseRequired=1` 与本地生成池推导一致。修复了仅在模板存在负面槽位时才检查缺失负面效果的漏洞。
3. **正负词条成对排列。** [上游对错位问题的修复说明](https://github.com/alfizari/Elden-Ring-Nightreign-Save-Editor/issues/55#issuecomment-3707907773)确认负面效果应留在其对应正面效果的位置。精确池检查现在也按同一组正负配对完成六种排列校验，避免分别匹配成功却实际无法配对。
4. **权重使用当前参数字段定义。** [Smithbox 的定义](https://github.com/vawser/Smithbox/blob/cbd477a8fd6d436b3e011c8548e1de8fd8876918/src/Smithbox.Data/Assets/PARAM/NR/Defs/AttachEffectTableParam.xml)区分基础 `u16` 权重和 DLC `s16` 权重。本地 CSV 已采用该格式，不混用网上旧导出文件的负数权重解释。

Reliquary 用于交叉核实词条组合与负面需求，不足以独自证明存档 Item ID 正确。上游对深夜池同时提供合并校验与精确校验，故“数量、配对正确但仅合并池通过”的结果仍保留为无法判定。

## 已知边界

“符合已知规则”只表示本次检查未发现矛盾，不能证明取得途径、服务器状态或存档来源。校验报告中出现 ID 与词条不匹配，也不能单凭这一项判断遗物是如何获得的。

参数是固定快照。游戏更新后出现的新遗物、新词条或新生成规则可能需要重新提取和核对参数；未知版本不应被旧规则直接判为违规。
