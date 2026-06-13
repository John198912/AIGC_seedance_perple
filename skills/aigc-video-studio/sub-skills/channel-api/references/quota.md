# 配额 / 限流 / 重试（quota）

> verified_at: 2026-06-01（活文档）。

## 429 限流退避

`api_adapter.py` 命中 429 → 指数退避重试（带上限）；超重试上限 → fallback 到备用通道或降级为 UI 卡，记 `rerun_history`，不阻断闭环。

## 余额 / 配额告警

- `verify_capabilities.py` 心跳检查通道可用性与余额。
- 余额低于阈值告警；配额耗尽 → 降级为 UI 卡人工执行。

## 成本守门联动

发批前 `budget_guard` 按 `min(project.per_shot_cost_cap_cny, genspec.per_shot_cost_cap_cny)` 卡单镜成本；`ai_qc_cost_cap` 卡 VLM 初筛总成本。通道单价维护在 `_shared/libs/channel-cost-map.yaml`。

## 降级链

API draft 失败/超配额 → 降分辨率（1080p→720p→480p）→ 转 UI 卡 → 文本+静帧兜底（见 state-machine 降级链）。
