---
name: gen-runner
description: GenSpec→任务卡批次（UI 卡+API 卡）；回收 inbox；VLM 初筛；登记 TakeLog（C9）；组织选片。
---

# SK6 · gen-runner（生成调度与回收）

> 生成闭环的执行中枢：出卡 → 生成 → 回收 → 初筛 → 选片。详见设计稿 §5 SK6 / §7.2。

## 触发 / 输入 / 输出

- 触发：G5 通过（或 premium 抽查免过）、进入 S6_GENERATION。
- 输入：`genspecs/` + 项目预算 + profile。
- 输出：`taskcards/batch-NN/`（C7 + .api.json）；`06_generations/*/takes.yaml`（C9）；选片报告。

## Gate

**G6 选片（强制，核心审美决策）**。

## 批次策略（提示词内固化）

1. **排批规则**：同平台同入口/同通道排同批；依赖卡（首帧图）排前批。
2. **render_passes 实例化**：遵 `GenSpec.render_passes[]` 按 (shot×pass) 出卡——
   draft pass 出 API 卡（720p 快档抽卡）、final pass 出 UI 卡（仅中选 take 1080p 终渲）。
3. **可实现贝叶斯停止**：按 `GenSpec.rolling`——qualified_def(vlm.pass 且 human≥4)
   + prior Beta(1,3) 共轭更新 + stop_rule（已有 1 达标且 E[p]·V_marginal<C_take，
   或超 max，或超单镜上限）；实现期可退回 `fallback_simple_rule`（N 个达标即停 + 成本上限）。
4. 发批前跑 `budget_guard`。
5. **通道执行**：UI 卡等人执行；API 卡交 `api_adapter`（retry/fallback/降级，凭证仅读 env）异步执行。

## 回收流程

"TC-xxx done" 或 API 回调 → `ingest.py` 扫 inbox（未匹配入 `_unmatched/` 不阻断）
→ 按 `SHOT-xx-tNN[_seed<seed>].{ext}` 重命名入 `takes/` → 写 TakeLog（含 pass/seed/
model_version/耗时）→ 记账（追写 events.jsonl）→ 跑 `vlm_screen.py` 协议分层抽帧
（static 单帧 / dynamic 首-中-尾）写 `scores.agent_vlm`；**auto_reject 仅 confidence>0.9
且 identity=FAIL，永不 auto_accept** → 呈导演选片（只呈现通过初筛的候选）。

## 局部重跑

"运镜反向"类反馈 → 只改 `GenSpec.motion` + bump version → 产出 rerun 卡（复用原参考与
首帧）→ 记 `rerun_history`（含 genspec_version）。

## 单写者

`takes.yaml` 唯一写者为 `ingest.py` / `vlm_screen.py`；账务只追写 `events.jsonl`（§4）。

## 脚本

- `make_taskcards.py`（遍历 render_passes 按 (shot×pass) 出 UI/API 卡 + 批次清单；
  GenSpec.continuity 在 API 卡注入 @PrevTail 尾帧参考、UI 卡注入尾帧延续段，A.4）。
- `ingest.py`（共享，含 pass + _unmatched 容错）。
- `vlm_screen.py`（共享，协议分层初筛）。
- `api_adapter.py`（共享，retry/fallback，凭证仅读 env）。
- `select_take.py`（写选片决议 + 更新 shotlist.status + git commit；防选 auto_reject 废片）。
