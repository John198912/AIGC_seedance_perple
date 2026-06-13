# seed 复现说明（seed）

> verified_at: 2026-06-01（活文档）。

## 基本规则

- **seed 仅 API 通道可用**；UI 通道（即梦/OpenArt/Higgsfield 网页）通常不可显式固定 seed，不保证复现。
- 同 `seed` + 同 `prompt` + 同 `references` + 同参数 → 可复现同一/近似结果。
- 即使固定 seed，模型仍可能有**轻微抖动**（"fix for reproducibility" 非逐帧严格一致）。

## TakeLog 记录

`ingest.py` 写 TakeLog（C9）时记录 `seed`（连同 `pass`/`model_version`/耗时）。重命名规约支持 `SHOT-xx-tNN_seed<seed>.<ext>`，便于回溯与复现。

## 局部重跑复现

"运镜反向"类局部重跑：复用原 seed + 仅改 `GenSpec.motion` + bump version，最大化保留其余画面一致性；记 `rerun_history`（含 `genspec_version`）。

## 用途

- 选片后若需微调，从中选 take 的 seed 出发小步迭代，避免画面大幅跳变。
- e2e/测试用确定性 mock seed，保证冒烟测试可重复。
