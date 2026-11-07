# 留出集 v1 规则同题对照（2026-11-07）

- 题集：`backend/tests/fixtures/evaluation_routing/plan_rules_heldout_v1.json`，43 题，用户手写，frozen，content_sha256 `bbf209749a37533bfc2b683a1e4a0793e14fcf179bdaf9a51296ea1e954c083c`。
- Planner 录制：`evaluation-runs/planner/20261107-heldout-v1-record`，46 次调用，预估 $0.0278；回放 0 次调用，43 题决定和补全问题逐条一致。1 题 Planner 报错（heldout-r4-01，StructuredOutputError）。
- 规则版本 rules/2，裁决表 B2j；规则读 Planner 补全后的问题。

## 两种模式

| 模式 | 答对 | 错误反问 |
|---|---|---|
| 只用 Planner | 32/43 | 7 |
| 启用全部规则 | 31/43 | 6 |

无冲突题。23 题没有规则命中。

## 逐条规则

| 规则 | 有效样本 | 命中正确 | 只启用这一条：答对 | 错误反问 | 变化 |
|---|---|---|---|---|---|
| R2 | 10 | 7 | 30（-2） | 7 | heldout-r3-02、r3-04 改坏；r2-07 无影响 |
| R3 | 2 | 0 | 32 | 6（-1） | heldout-r4-07 无影响 |
| R4 | 3 | 3 | 33（+1） | 7 | heldout-r4-01 计为修好，但该题 Planner 报错，线上不会走到规则 |
| R5 | 5 | 5 | 32 | 7 | 无变化（Planner 在这 5 题上本来就对） |

## 观察

- 规则覆盖低：用户为 R3、R4 各写了约 5 道正例，规则实际只命中 2、3 道；R2 在 2 道用户标为 hybrid 的题上命中，说明事实提取没识别出经营指标。
- Planner 自身 7 次错误反问（r3-03、r3-05、r4-07、r5-06、r5-09、none-01、none-08），现有规则都修不了。
- 对照脚本把 Planner 报错的题也当作可被规则修好，需单独排除。
